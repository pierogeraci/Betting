"""Associazione di un sito a una legal entity: candidati ordinati per punteggio, l'analista conferma.

Solo persone giuridiche. Le fonti sono i dati dichiarati dal sito, gli elenchi ADM,
i registri pubblici di società e di licenze caricati dall'analista e i domini gemelli.
"""

from __future__ import annotations

import csv
import io
import math
import re
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.models import (
    ElementoGrezzo,
    Entita,
    Indicatore,
    LegalEntity,
    LegameEntita,
    LegameSito,
    MenzioneEntita,
    RegistroVoce,
    Sito,
)
from core.storage import archive_bytes, sha256_hex

SUFFIXES = r"\b(s\.?p\.?a|s\.?r\.?l\.?s?|ltd|limited|n\.?v|b\.?v|gmbh|llc|s\.?a|inc|o[uü]|sia|plc|s\.?l|corp|company|co)\b\.?"
MATCH_THRESHOLD = 0.85


def normalize_company(name: str) -> str:
    text = (name or "").lower()
    text = re.sub(SUFFIXES, " ", text)
    text = re.sub(r"[^a-z0-9àèéìòù ]+", " ", text)
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    a, b = normalize_company(a), normalize_company(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    tokens_a, tokens_b = set(a.split()), set(b.split())
    jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    return round(max(SequenceMatcher(None, a, b).ratio(), jaccard), 3)


COLUMNS = ("nome", "paese", "numero", "stato")
LEGAL_FORM = re.compile(
    SUFFIXES + r"|\b(società|societa|company|corporation|holding|group|gaming|entertainment)\b", re.I
)


def load_registry(
    session: Session, kind: str, data: bytes, source: str, user_id: int | None = None
) -> tuple[int, list[str]]:
    """Carica un registro di società o di licenze: CSV con colonne nome, paese, numero, stato.

    Si conservano solo queste quattro colonne e solo le voci con una forma giuridica:
    amministratori, soci, codici fiscali o ditte individuali non entrano nel sistema.
    Nell'archivio grezzo va la versione ripulita del file, con il suo hash, non l'originale.
    """
    if kind not in {"societa", "licenze"}:
        raise ValueError("Registro sconosciuto.")
    text = data.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.count(";") > text.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fields = {f.strip().lower() for f in reader.fieldnames or []}
    if "nome" not in fields:
        raise ValueError("Il file deve avere almeno la colonna «nome» (facoltative: paese, numero, stato).")
    kept, errors = [], []
    ignored = sorted(fields - set(COLUMNS))
    if ignored:
        errors.append(f"Colonne ignorate e non conservate: {', '.join(ignored[:10])}")
    for n, raw in enumerate(reader, start=2):
        row = {
            k.strip().lower(): (v or "").strip() for k, v in raw.items() if k and k.strip().lower() in COLUMNS
        }
        if not row.get("nome"):
            errors.append(f"Riga {n}: nome mancante")
            continue
        if not LEGAL_FORM.search(row["nome"]):
            errors.append(f"Riga {n}: senza forma giuridica, scartata (solo persone giuridiche)")
            continue
        kept.append([row.get(c, "")[:300] for c in COLUMNS])
    clean = io.StringIO()
    writer = csv.writer(clean, delimiter=";")
    writer.writerow(COLUMNS)
    writer.writerows(kept)
    cleaned = clean.getvalue().encode("utf-8")
    digest, key = archive_bytes(cleaned, "text/csv")
    element = session.execute(
        select(ElementoGrezzo).where(
            ElementoGrezzo.fonte == f"registro:{kind}", ElementoGrezzo.sha256 == digest
        )
    ).scalar_one_or_none()
    if element is not None:
        return 0, ["Questo registro è già stato caricato."]
    element = ElementoGrezzo(
        fonte=f"registro:{kind}",
        tipo="registro",
        riferimento=source[:300],
        oggetto_chiave=key,
        sha256=digest,
        inserito_da=user_id,
        metadati={"voci": len(kept), "sha256_file_originale": sha256_hex(data)},
    )
    session.add(element)
    session.flush()
    for name, country, number, state in kept:
        session.add(
            RegistroVoce(
                registro=kind,
                fonte=source[:200],
                nome=name,
                nome_normalizzato=normalize_company(name)[:300],
                paese=country[:60],
                numero=number[:80],
                stato=state[:60],
                dettagli={},
                elemento_grezzo_id=element.id,
            )
        )
    session.flush()
    return len(kept), errors


def _latest(session: Session, site_id: int) -> dict[str, Indicatore]:
    out: dict[str, Indicatore] = {}
    for ind in session.execute(
        select(Indicatore)
        .where(Indicatore.sito_id == site_id)
        .order_by(Indicatore.rilevato_il.desc(), Indicatore.id.desc())
    ).scalars():
        out.setdefault(ind.codice, ind)
    return out


def candidates(session: Session, site: Sito) -> list[dict[str, Any]]:
    inds = _latest(session, site.id)
    found: dict[str, dict[str, Any]] = {}

    def add(
        name: str,
        weight: float,
        evidence: str,
        country: str = "",
        number: str = "",
        voce: RegistroVoce | None = None,
    ) -> None:
        key = normalize_company(name)
        if not key:
            return
        item = found.setdefault(
            key,
            {
                "nome": name,
                "paese": country,
                "numero": number,
                "evidenze": [],
                "peso": 0.0,
                "registro_voce_id": None,
            },
        )
        item["peso"] += weight
        item["evidenze"].append({"peso": round(weight, 2), "evidenza": evidence})
        item["paese"] = item["paese"] or country
        item["numero"] = item["numero"] or number
        if voce is not None and item["registro_voce_id"] is None:
            item["registro_voce_id"] = voce.id
            item["nome"] = voce.nome

    declared = inds.get("ragione_sociale_dichiarata")
    declared_name = (
        declared.evidenza.get("valore") if declared is not None and declared.valore == "presente" else None
    )
    if declared_name:
        add(declared_name, 0.35, f"Ragione sociale dichiarata sul sito: «{declared_name}»")
        for voce in session.execute(select(RegistroVoce).where(RegistroVoce.registro == "societa")).scalars():
            score = similarity(declared_name, voce.nome)
            if score >= MATCH_THRESHOLD:
                add(
                    voce.nome,
                    0.3 * score,
                    f"Nel registro {voce.fonte}: «{voce.nome}» ({voce.paese or 'paese n.d.'}), somiglianza {score:.0%}",
                    voce.paese,
                    voce.numero,
                    voce,
                )
    number_ind = inds.get("partita_iva_dichiarata")
    number = (
        str(number_ind.evidenza.get("valore", ""))
        if number_ind is not None and number_ind.valore == "presente"
        else ""
    )
    if number:
        digits = re.sub(r"\W", "", number).lower()
        for voce in session.execute(select(RegistroVoce).where(RegistroVoce.numero != "")).scalars():
            if re.sub(r"\W", "", voce.numero).lower() == digits:
                add(
                    voce.nome,
                    0.4,
                    f"Numero dichiarato {number} uguale a quello del registro {voce.fonte}",
                    voce.paese,
                    voce.numero,
                    voce,
                )
    licence_numbers = set()
    licence = inds.get("licenza_estera_dichiarata")
    if licence is not None and licence.valore == "presente":
        from extractors.entities import extract

        licence_numbers = {
            e.value.lower()
            for e in extract(licence.evidenza.get("estratto", ""))
            if e.kind.startswith("licenza_")
        }
    for value in licence_numbers:
        for voce in session.execute(select(RegistroVoce).where(RegistroVoce.registro == "licenze")).scalars():
            if voce.numero and voce.numero.lower() == value:
                add(
                    voce.nome,
                    0.45,
                    f"Licenza {value.upper()} dichiarata dal sito: titolare nel registro {voce.fonte}{' (' + voce.stato + ')' if voce.stato else ''}",
                    voce.paese,
                    voce.numero,
                    voce,
                )
    adm_ind = inds.get("dominio_concessionario_adm")
    if adm_ind is not None and adm_ind.valore == "presente" and adm_ind.evidenza.get("ragione_sociale"):
        add(
            adm_ind.evidenza["ragione_sociale"],
            0.6 * float(adm_ind.certezza),
            f"Concessionario ADM n. {adm_ind.evidenza.get('numero_concessione')} (elenco versione {adm_ind.evidenza.get('versione_elenco')})",
            "Italia",
        )
    twins = (
        session.execute(
            select(LegameSito).where(
                or_(LegameSito.sito_a == site.id, LegameSito.sito_b == site.id), LegameSito.forza >= 0.5
            )
        )
        .scalars()
        .all()
    )
    for link in twins:
        other = link.sito_b if link.sito_a == site.id else link.sito_a
        for le in session.execute(
            select(LegalEntity).where(LegalEntity.sito_id == other, LegalEntity.stato == "confermata")
        ).scalars():
            dom = session.get(Sito, other).dominio
            add(
                le.nome,
                0.25 * float(link.forza),
                f"Confermata per il gemello {dom} ({link.motivo})",
                le.paese,
                le.numero,
            )
    out = []
    for item in found.values():
        item["punteggio"] = round(1 - math.exp(-2 * item.pop("peso")), 3)
        out.append(item)
    return sorted(out, key=lambda c: -c["punteggio"])


def confirm(
    session: Session, site: Sito, candidate: dict[str, Any], user_id: int | None, accept: bool, note: str = ""
) -> LegalEntity:
    row = LegalEntity(
        sito_id=site.id,
        nome=candidate["nome"][:300],
        paese=(candidate.get("paese") or "")[:60],
        numero=(candidate.get("numero") or "")[:80],
        punteggio=candidate.get("punteggio", 0),
        evidenze=candidate.get("evidenze", []),
        registro_voce_id=candidate.get("registro_voce_id"),
        stato="confermata" if accept else "respinta",
        confermata_da=user_id,
        note=note[:2000],
    )
    session.add(row)
    session.flush()
    return row


def graph(session: Session, site: Sito, limit: int = 40) -> dict[str, Any]:
    """Grafo attorno al sito: entità collegate, domini gemelli, legal entity confermate."""
    domain = session.execute(
        select(Entita).where(Entita.tipo == "dominio", Entita.valore == site.dominio)
    ).scalar_one_or_none()
    nodes = [{"id": "sito", "etichetta": site.dominio, "tipo": "sito"}]
    edges = []
    if domain is not None:
        rows = session.execute(
            select(LegameEntita, Entita)
            .join(Entita, Entita.id == LegameEntita.a_entita_id)
            .where(LegameEntita.da_entita_id == domain.id)
            .limit(limit)
        ).all()
        for link, ent in rows:
            nid = f"e{ent.id}"
            nodes.append({"id": nid, "etichetta": ent.valore[:40], "tipo": ent.tipo})
            edges.append({"da": "sito", "a": nid, "tipo": link.tipo})
            shared = (
                session.execute(
                    select(LegameEntita.da_entita_id)
                    .where(LegameEntita.a_entita_id == ent.id, LegameEntita.da_entita_id != domain.id)
                    .limit(5)
                )
                .scalars()
                .all()
            )
            for other in shared:
                other_ent = session.get(Entita, other)
                oid = f"e{other}"
                if not any(n["id"] == oid for n in nodes):
                    nodes.append({"id": oid, "etichetta": other_ent.valore[:40], "tipo": "dominio_collegato"})
                edges.append({"da": oid, "a": nid, "tipo": "condivide"})
        mentions = (
            session.execute(
                select(ElementoGrezzo.fonte)
                .join(MenzioneEntita, MenzioneEntita.elemento_grezzo_id == ElementoGrezzo.id)
                .where(MenzioneEntita.entita_id == domain.id)
            )
            .scalars()
            .all()
        )
        for source in sorted(set(mentions)):
            nid = f"f{source}"
            nodes.append({"id": nid, "etichetta": f"{source} ({mentions.count(source)})", "tipo": "fonte"})
            edges.append({"da": nid, "a": "sito", "tipo": "cita"})
    for le in session.execute(
        select(LegalEntity).where(LegalEntity.sito_id == site.id, LegalEntity.stato == "confermata")
    ).scalars():
        nodes.append({"id": f"l{le.id}", "etichetta": le.nome[:40], "tipo": "legal_entity"})
        edges.append({"da": "sito", "a": f"l{le.id}", "tipo": "gestito_da"})
    for link in session.execute(
        select(LegameSito).where(or_(LegameSito.sito_a == site.id, LegameSito.sito_b == site.id))
    ).scalars():
        other = session.get(Sito, link.sito_b if link.sito_a == site.id else link.sito_a)
        nid = f"s{other.id}"
        if not any(n["id"] == nid for n in nodes):
            nodes.append(
                {"id": nid, "etichetta": other.dominio, "tipo": "gemello", "url": f"/siti/{other.id}"}
            )
        edges.append({"da": "sito", "a": nid, "tipo": link.motivo})
    return layout({"nodi": nodes[:80], "archi": edges[:160]})


def layout(g: dict[str, Any]) -> dict[str, Any]:
    """Disposizione radiale: il sito al centro, i nodi in cerchi per tipo."""
    rings = {"sito": 0, "legal_entity": 1, "gemello": 1, "fonte": 1}
    others = [n for n in g["nodi"] if n["tipo"] not in rings]
    first = [n for n in g["nodi"] if rings.get(n["tipo"]) == 1]
    for i, node in enumerate(first):
        angle = 2 * math.pi * i / max(len(first), 1)
        node["x"], node["y"] = 50 + 22 * math.cos(angle), 50 + 22 * math.sin(angle)
    for i, node in enumerate(others):
        angle = 2 * math.pi * i / max(len(others), 1) + 0.3
        node["x"], node["y"] = 50 + 42 * math.cos(angle), 50 + 42 * math.sin(angle)
    for node in g["nodi"]:
        if node["tipo"] == "sito":
            node["x"], node["y"] = 50, 50
    pos = {n["id"]: (n["x"], n["y"]) for n in g["nodi"]}
    g["archi"] = [
        e | {"x1": pos[e["da"]][0], "y1": pos[e["da"]][1], "x2": pos[e["a"]][0], "y2": pos[e["a"]][1]}
        for e in g["archi"]
        if e["da"] in pos and e["a"] in pos
    ]
    return g


def registry_digest(kind: str, source: str) -> str:
    return sha256_hex(f"{kind}|{source}".encode())
