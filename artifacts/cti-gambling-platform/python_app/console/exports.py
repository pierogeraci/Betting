"""Esportazione in Excel delle evidenze e delle valutazioni del portale."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import (
    Avviso,
    Canale,
    ElementoGrezzo,
    Entita,
    EventoSportivo,
    Estrazione,
    Indicatore,
    LegalEntity,
    Puntata,
    Punteggio,
    Revisione,
    Sito,
)

MAX_TESTO_CELLA = 32_767


def _cell(value: Any) -> Any:
    """Normalizza i valori e neutralizza formule importate come testo."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, str):
        if len(value) > MAX_TESTO_CELLA:
            value = value[: MAX_TESTO_CELLA - 60] + " [contenuto ridotto: consultare l'archivio originale]"
        if value.startswith(("=", "+", "-", "@")):
            value = "'" + value
    return value


def build_xlsx(
    sheets: dict[str, tuple[list[str], list[list[Any]]]],
    *,
    generated_at: datetime | None = None,
) -> bytes:
    """Crea un workbook leggibile e sicuro a partire da fogli già preparati."""
    generated_at = generated_at or datetime.now(UTC)
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.title = "Estrazione CTI"
    workbook.properties.subject = "Evidenze, siti e valutazioni CTI"
    workbook.properties.creator = "Softstrategy · CTI"
    workbook.properties.created = generated_at.replace(tzinfo=None)

    for name, (headers, rows) in sheets.items():
        sheet = workbook.create_sheet(name[:31])
        sheet.append([_cell(header) for header in headers])
        for row in rows:
            sheet.append([_cell(value) for value in row])
        sheet.freeze_panes = "A2"
        if headers:
            sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="163B3A")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.row_dimensions[1].height = 30
        for column in sheet.columns:
            column_letter = column[0].column_letter
            sample = [str(cell.value or "") for cell in column[:40]]
            width = min(max(14, max((len(value) for value in sample), default=0) + 2), 44)
            sheet.column_dimensions[column_letter].width = width
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=False)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def create_cti_export(db: Session, *, generated_at: datetime | None = None) -> bytes:
    """Estrae in un unico workbook i dati consultabili nell'applicazione."""
    generated_at = generated_at or datetime.now(UTC)
    sites = db.execute(select(Sito).order_by(Sito.id)).scalars().all()
    scores = db.execute(select(Punteggio).order_by(Punteggio.sito_id, Punteggio.calcolato_il)).scalars().all()
    indicators = db.execute(select(Indicatore).order_by(Indicatore.sito_id, Indicatore.codice)).scalars().all()
    bets = db.execute(select(Puntata).order_by(Puntata.sito_id, Puntata.momento)).scalars().all()
    evidence = db.execute(select(ElementoGrezzo).order_by(ElementoGrezzo.raccolto_il)).scalars().all()
    extractions = db.execute(select(Estrazione).order_by(Estrazione.creato_il)).scalars().all()
    entities = db.execute(select(Entita).order_by(Entita.tipo, Entita.valore)).scalars().all()
    legal_entities = db.execute(select(LegalEntity).order_by(LegalEntity.sito_id, LegalEntity.nome)).scalars().all()
    events = db.execute(select(EventoSportivo).order_by(EventoSportivo.inizio, EventoSportivo.nome)).scalars().all()
    channels = db.execute(select(Canale).order_by(Canale.piattaforma, Canale.titolo)).scalars().all()
    alerts = db.execute(select(Avviso).order_by(Avviso.creato_il.desc())).scalars().all()
    reviews = db.execute(select(Revisione).order_by(Revisione.creata_il.desc())).scalars().all()

    domain_by_id = {site.id: site.dominio for site in sites}
    vulnerability_rows: list[list[Any]] = []
    threat_rows: list[list[Any]] = []
    for score in scores:
        detail = score.dettaglio or {}
        vulnerability = detail.get("vulnerabilita") or {}
        for item in vulnerability.get("voci") or []:
            evidence_detail = item.get("evidenza") or {}
            vulnerability_rows.append(
                [
                    domain_by_id.get(score.sito_id, score.sito_id),
                    score.ambito,
                    score.versione_regole,
                    item.get("codice"),
                    item.get("nome"),
                    item.get("peso"),
                    item.get("valore"),
                    evidence_detail.get("estratto") or evidence_detail.get("motivo"),
                    evidence_detail.get("url"),
                ]
            )
        threat = detail.get("minaccia") or {}
        for variable in threat.get("variabili") or []:
            threat_rows.append(
                [
                    domain_by_id.get(score.sito_id, score.sito_id),
                    score.ambito,
                    score.versione_regole,
                    variable.get("codice"),
                    variable.get("nome"),
                    variable.get("formula"),
                    variable.get("valore"),
                    variable.get("soglie"),
                    variable.get("voto"),
                    variable.get("livello"),
                ]
            )

    sheets: dict[str, tuple[list[str], list[list[Any]]]] = {
        "Riepilogo": (
            ["Voce", "Valore"],
            [
                ["Generato il", generated_at],
                ["Siti", len(sites)],
                ["Punteggi Trust Index", len(scores)],
                ["Indicatori", len(indicators)],
                ["Puntate", len(bets)],
                ["Evidenze", len(evidence)],
                ["Estrazioni", len(extractions)],
                ["Entità", len(entities)],
                ["Entità legali", len(legal_entities)],
                ["Eventi sportivi", len(events)],
                ["Canali", len(channels)],
                ["Avvisi", len(alerts)],
                ["Revisioni", len(reviews)],
                ["Profili scommettitori reali", "Non inclusi: il modulo anomalie usa esclusivamente dati sintetici."],
            ],
        ),
        "Siti": (
            ["ID", "Dominio", "Esito ADM", "Fonte di scoperta", "Primo avvistamento", "Ultimo snapshot"],
            [
                [s.id, s.dominio, s.esito_adm, s.fonte_scoperta, s.primo_avvistamento, s.ultimo_snapshot_il]
                for s in sites
            ],
        ),
        "Trust Index": (
            [
                "ID sito",
                "Dominio",
                "Ambito",
                "Vulnerabilità",
                "Livello vulnerabilità",
                "Minaccia",
                "Livello minaccia",
                "Trust Index",
                "Classe di rischio",
                "Copertura",
                "Versione regole",
                "Calcolato il",
            ],
            [
                [
                    p.sito_id,
                    domain_by_id.get(p.sito_id),
                    p.ambito,
                    p.vulnerabilita,
                    p.livello_vulnerabilita,
                    p.minaccia,
                    p.livello_minaccia,
                    p.trust_index,
                    p.classe_rischio,
                    p.copertura,
                    p.versione_regole,
                    p.calcolato_il,
                ]
                for p in scores
            ],
        ),
        "Vulnerabilità": (
            [
                "Dominio",
                "Ambito",
                "Versione regole",
                "Codice",
                "Indicatore",
                "Peso",
                "Rilevazione",
                "Prova o nota",
                "URL della prova",
            ],
            vulnerability_rows,
        ),
        "Minaccia": (
            [
                "Dominio",
                "Ambito",
                "Versione regole",
                "Codice",
                "Variabile",
                "Formula",
                "Valore",
                "Soglie",
                "Voto",
                "Livello",
            ],
            threat_rows,
        ),
        "Indicatori": (
            ["ID sito", "Dominio", "Codice", "Valore", "Certezza", "Collettore", "Versione", "Evidenza", "Rilevato il"],
            [
                [
                    i.sito_id,
                    domain_by_id.get(i.sito_id),
                    i.codice,
                    i.valore,
                    i.certezza,
                    i.collettore,
                    i.versione_collettore,
                    i.evidenza,
                    i.rilevato_il,
                ]
                for i in indicators
            ],
        ),
        "Puntate": (
            ["ID sito", "Dominio", "Tipo di gioco", "Importo puntato", "Importo vinto", "Valuta", "Momento", "Fonte"],
            [
                [
                    b.sito_id,
                    domain_by_id.get(b.sito_id),
                    b.tipo_gioco,
                    b.importo_puntato,
                    b.importo_vinto,
                    b.valuta,
                    b.momento,
                    b.fonte,
                ]
                for b in bets
            ],
        ),
        "Evidenze": (
            ["ID", "Fonte", "Tipo", "Riferimento", "Contenuto", "SHA-256", "Raccolto il", "Metadati"],
            [
                [
                    e.id,
                    e.fonte,
                    e.tipo,
                    e.riferimento,
                    e.contenuto,
                    e.sha256,
                    e.raccolto_il,
                    e.metadati,
                ]
                for e in evidence
            ],
        ),
        "Estrazioni": (
            ["ID", "ID evidenza", "ID media", "Tipo", "Testo", "Da (ms)", "A (ms)", "Modello", "Versione", "Creato il"],
            [
                [
                    e.id,
                    e.elemento_grezzo_id,
                    e.media_id,
                    e.tipo,
                    e.testo,
                    e.tempo_inizio_ms,
                    e.tempo_fine_ms,
                    e.modello,
                    e.versione_modello,
                    e.creato_il,
                ]
                for e in extractions
            ],
        ),
        "Entità": (
            ["ID", "Tipo", "Valore", "Creata il"],
            [[e.id, e.tipo, e.valore, e.creato_il] for e in entities],
        ),
        "Entità legali": (
            ["ID sito", "Dominio", "Società", "Paese", "Numero", "Stato", "Punteggio", "Evidenze", "Note", "Creata il"],
            [
                [
                    e.sito_id,
                    domain_by_id.get(e.sito_id),
                    e.nome,
                    e.paese,
                    e.numero,
                    e.stato,
                    e.punteggio,
                    e.evidenze,
                    e.note,
                    e.creato_il,
                ]
                for e in legal_entities
            ],
        ),
        "Eventi sportivi": (
            ["ID", "Evento", "Sport", "Competizione", "Inizio", "Rating", "Dettaglio", "Creato il"],
            [
                [e.id, e.nome, e.sport, e.competizione, e.inizio, e.rating, e.dettaglio, e.creato_il]
                for e in events
            ],
        ),
        "Canali": (
            ["ID", "Piattaforma", "Identificativo", "Titolo", "Stato approvazione", "Motivo", "Creato il"],
            [
                [c.id, c.piattaforma, c.identificativo, c.titolo, c.stato, c.motivo, c.creato_il]
                for c in channels
            ],
        ),
        "Avvisi": (
            ["ID", "Tipo", "Titolo", "Testo", "ID sito", "ID evidenza", "Letto", "Creato il"],
            [
                [a.id, a.tipo, a.titolo, a.testo, a.sito_id, a.elemento_grezzo_id, a.letto, a.creato_il]
                for a in alerts
            ],
        ),
        "Revisioni": (
            ["ID", "Tipo", "Stato", "ID sito", "ID snapshot", "Motivo", "Esito"],
            [[r.id, r.tipo, r.stato, r.sito_id, r.snapshot_id, r.motivo, r.esito] for r in reviews],
        ),
        "Metodo": (
            ["Voce", "Valore"],
            [
                ["Fonte dei pesi", "Matrice Excel v0.5"],
                ["Formula Trust Index", "(Vulnerabilità + Minaccia) / 2"],
                ["Esempio di verifica - Vulnerabilità", 11.5],
                ["Esempio di verifica - Minaccia", 6],
                ["Esempio di verifica - Indice", 8.75],
                ["Esempio di verifica - Rischio", "alto"],
                ["Nota esempio", "Scenario sintetico di test; non rappresenta un sito reale."],
                ["Limite", "Pesi e soglie v0.5 da validare sul campione dell'analista."],
                ["Anomalie sui conti", "Solo dati sintetici."],
                ["Associazione a legal entity", "Proposta soggetta a conferma dell'analista."],
            ],
        ),
    }
    return build_xlsx(sheets, generated_at=generated_at)


def workbook_contains_expected_v05_example(payload: bytes) -> bool:
    """Controllo di regressione sul caso numerico approvato."""
    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    rows = list(workbook["Metodo"].iter_rows(values_only=True))
    return (
        ("Esempio di verifica - Vulnerabilità", 11.5) in rows
        and ("Esempio di verifica - Minaccia", 6) in rows
        and ("Esempio di verifica - Indice", 8.75) in rows
        and ("Esempio di verifica - Rischio", "alto") in rows
    )
