"""Fase 0: modello dati, coda di lavoro, ruolo ristretto per la raccolta."""

from alembic import op

from core.models import Base

revision = "0001"
down_revision = None

# Il ruolo `raccolta` non ha alcun privilegio sulle tabelle: può solo eseguire
# queste due funzioni. La password si imposta fuori dalle migrazioni (make init).
FUNZIONI = r"""
CREATE OR REPLACE FUNCTION lavoro_prendi(p_tipi text[], p_lavoratore text, p_secondi integer DEFAULT 300)
RETURNS TABLE (id bigint, tipo text, carico jsonb, tentativi integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    scelto bigint;
BEGIN
    -- I lavori presi e mai chiusi tornano disponibili alla scadenza.
    UPDATE lavoro l SET stato = CASE WHEN l.tentativi >= l.max_tentativi THEN 'fallito' ELSE 'in_attesa' END,
           errore = CASE WHEN l.tentativi >= l.max_tentativi THEN 'Scaduto senza risposta dal contenitore di raccolta' ELSE l.errore END,
           chiuso_il = CASE WHEN l.tentativi >= l.max_tentativi THEN clock_timestamp() ELSE NULL END
     WHERE l.coda = 'raccolta' AND l.stato = 'in_corso' AND l.scade_il < clock_timestamp();

    SELECT l.id INTO scelto FROM lavoro l
     WHERE l.coda = 'raccolta' AND l.stato = 'in_attesa'
       AND l.tipo = ANY (p_tipi) AND l.disponibile_dal <= clock_timestamp()
     ORDER BY l.id FOR UPDATE SKIP LOCKED LIMIT 1;
    IF scelto IS NULL THEN
        RETURN;
    END IF;
    RETURN QUERY
    UPDATE lavoro l SET stato = 'in_corso', tentativi = l.tentativi + 1,
           preso_da = left(p_lavoratore, 80), preso_il = clock_timestamp(),
           scade_il = clock_timestamp() + make_interval(secs => greatest(30, least(p_secondi, 3600)))
     WHERE l.id = scelto
    RETURNING l.id, l.tipo::text, l.carico, l.tentativi;
END $$;

CREATE OR REPLACE FUNCTION lavoro_chiudi(p_id bigint, p_lavoratore text, p_riuscito boolean, p_risultato jsonb, p_errore text DEFAULT NULL)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    r lavoro%ROWTYPE;
BEGIN
    SELECT * INTO r FROM lavoro l
     WHERE l.id = p_id AND l.coda = 'raccolta' AND l.stato = 'in_corso' AND l.preso_da = left(p_lavoratore, 80)
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF p_riuscito THEN
        UPDATE lavoro SET stato = 'completato', risultato = coalesce(p_risultato, '{}'::jsonb),
               errore = NULL, chiuso_il = clock_timestamp() WHERE id = p_id;
        IF r.successivo IS NOT NULL THEN
            INSERT INTO lavoro (coda, tipo, carico, stato, tentativi, max_tentativi, disponibile_dal,
                                risultato, origine_id, sito_id, creato_da, creato_il)
            VALUES ('interna', r.successivo, jsonb_build_object('lavoro_origine', p_id), 'in_attesa', 0, 3,
                    clock_timestamp(), '{}'::jsonb, p_id, r.sito_id, r.creato_da, clock_timestamp());
        END IF;
    ELSIF r.tentativi >= r.max_tentativi THEN
        UPDATE lavoro SET stato = 'fallito', errore = left(p_errore, 4000), chiuso_il = clock_timestamp() WHERE id = p_id;
    ELSE
        UPDATE lavoro SET stato = 'in_attesa', errore = left(p_errore, 4000),
               disponibile_dal = clock_timestamp() + make_interval(secs => 30 * r.tentativi) WHERE id = p_id;
    END IF;
    RETURN true;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'raccolta') THEN
        CREATE ROLE raccolta NOLOGIN;
    END IF;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM raccolta;
REVOKE ALL ON FUNCTION lavoro_prendi(text[], text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION lavoro_chiudi(bigint, text, boolean, jsonb, text) FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO raccolta;
GRANT EXECUTE ON FUNCTION lavoro_prendi(text[], text, integer) TO raccolta;
GRANT EXECUTE ON FUNCTION lavoro_chiudi(bigint, text, boolean, jsonb, text) TO raccolta;
"""

TABELLE_FASE0 = [
    "utente",
    "sessione_utente",
    "sonda",
    "elemento_grezzo",
    "media",
    "estrazione",
    "entita",
    "legame_entita",
    "menzione_entita",
    "sito",
    "snapshot",
    "indicatore",
    "punteggio",
    "revisione",
    "lavoro",
    "adm_caricamento",
    "adm_concessionario",
    "adm_sito_inibito",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in TABELLE_FASE0]
    Base.metadata.create_all(bind, tables=tables)
    op.execute(FUNZIONI)
    op.execute(
        "INSERT INTO sonda (nome, tipo, configurazione, cursore, stato, creato_il) VALUES "
        "('manuale', 'manuale', '{}', '{}', 'attiva', now()), ('adm', 'adm', '{}', '{}', 'attiva', now())"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS lavoro_chiudi(bigint, text, boolean, jsonb, text)")
    op.execute("DROP FUNCTION IF EXISTS lavoro_prendi(text[], text, integer)")
    bind = op.get_bind()
    Base.metadata.drop_all(bind, tables=[Base.metadata.tables[n] for n in reversed(TABELLE_FASE0)])
