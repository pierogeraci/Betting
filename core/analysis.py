"""Fase 3 lato interno: analisi del testo, classificatore, argomenti, valutazione."""

from __future__ import annotations

import random
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core import discovery, llm
from core.keywords import active_keywords
from core.models import (
    ElementoGrezzo,
    EmojiSignificato,
    Estrazione,
    Etichetta,
    Media,
    Modello,
    Valutazione,
    utcnow,
)
from core.storage import archive_bytes, read_archive
from extractors.classifier import Classifier, Example, TrainingDataError, metrics
from extractors.entities import extract
from extractors.text import VERSION as TEXT_VERSION
from extractors.text import analyse

THRESHOLD = 0.5
TEXT_KINDS = ("ocr", "trascrizione", "qr", "traduzione")


def element_text(session: Session, element: ElementoGrezzo) -> str:
    """Testo dell'elemento più tutto ciò che è stato estratto dai suoi file."""
    parts = [element.contenuto or ""]
    if element.tipo == "url":
        parts = []
    rows = session.execute(
        select(Estrazione)
        .where(Estrazione.elemento_grezzo_id == element.id, Estrazione.tipo.in_(TEXT_KINDS))
        .order_by(Estrazione.tipo, Estrazione.tempo_inizio_ms.nullsfirst())
    ).scalars()
    parts += [r.testo for r in rows if r.testo]
    return "\n".join(p for p in parts if p).strip()


def emoji_dictionary(session: Session) -> dict[tuple[str, str], str]:
    return {
        (e.carattere, e.piattaforma): e.significato
        for e in session.execute(select(EmojiSignificato)).scalars()
    }


def active_classifier(session: Session) -> tuple[Classifier | None, Modello | None]:
    row = session.execute(
        select(Modello)
        .where(Modello.nome == "classificatore", Modello.attivo.is_(True))
        .order_by(Modello.addestrato_il.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None or not row.chiave:
        return None, None
    try:
        return Classifier.loads(read_archive(row.chiave)), row
    except Exception:  # noqa: BLE001 - un modello illeggibile non ferma l'analisi
        return None, row


def analyse_element(session: Session, element: ElementoGrezzo) -> dict[str, Any]:
    text = element_text(session, element)
    if not text:
        return {"saltato": "nessun testo"}
    platform = element.fonte.split(":")[0] if element.fonte in {"telegram", "web", "tor"} else None
    result = analyse(text, platform, emoji_dictionary(session))
    classifier, model_row = active_classifier(session)
    if classifier is not None:
        probability = classifier.predict_proba([text])[0]
        result["classificazione"] = {
            "pubblicita_gioco": probability >= THRESHOLD,
            "probabilita": round(probability, 3),
            "modello": model_row.versione,
        }
    else:
        result["classificazione"] = None
    fields = llm.extract_fields(text) if llm.available() else None
    if fields:
        result["campi_modello"] = fields
    session.execute(
        update(Estrazione)
        .where(Estrazione.elemento_grezzo_id == element.id, Estrazione.tipo == "analisi")
        .values(metadati=Estrazione.metadati.op("||")({"sostituita": True}))
    )
    session.add(
        Estrazione(
            elemento_grezzo_id=element.id,
            tipo="analisi",
            testo=result["testo_normalizzato"],
            modello="regole" + ("+" + model_row.versione if model_row else ""),
            versione_modello=TEXT_VERSION,
            metadati={k: v for k, v in result.items() if k != "testo_normalizzato"},
        )
    )
    for item in result["emoji"]:
        if item["nel_dizionario"]:
            session.execute(
                update(EmojiSignificato)
                .where(EmojiSignificato.carattere == item["emoji"])
                .values(occorrenze=EmojiSignificato.occorrenze + item["volte"])
            )
    # Il testo estratto dai file (OCR, audio, QR) può portare a siti nuovi: stesso percorso delle sonde.
    extracted = "\n".join(
        r.testo
        for r in session.execute(
            select(Estrazione).where(
                Estrazione.elemento_grezzo_id == element.id, Estrazione.tipo.in_(TEXT_KINDS)
            )
        ).scalars()
    )
    stats = discovery.RunStats()
    if extracted:
        is_gambling = bool(result["classificazione"] and result["classificazione"]["pubblicita_gioco"])
        discovery.process_text(
            session,
            element,
            extracted,
            stats,
            keywords=active_keywords(session),
            source_label=f"{element.fonte.split(':')[0]}:media",
            max_new_sites=10,
            platform=platform,
            require_keyword=not is_gambling,
        )
    session.flush()
    return {
        "lingua": result["lingua"],
        "entita": len(result["entita"]),
        "emoji": len(result["emoji"]),
        "classificazione": result["classificazione"],
        "siti_nuovi": stats.new_sites,
    }


def labelled_examples(session: Session) -> list[tuple[Etichetta, ElementoGrezzo, str]]:
    rows = session.execute(
        select(Etichetta, ElementoGrezzo).join(
            ElementoGrezzo, ElementoGrezzo.id == Etichetta.elemento_grezzo_id
        )
    ).all()
    return [(label, element, element_text(session, element)) for label, element in rows]


def train_classifier(session: Session, user_id: int | None = None, seed: int = 0) -> dict[str, Any]:
    data = [
        (lab, el, txt)
        for lab, el, txt in labelled_examples(session)
        if lab.pubblicita_gioco is not None and txt
    ]
    examples = [Example(txt, bool(lab.pubblicita_gioco), el.fonte) for lab, el, txt in data]
    allowed = [e for e in examples if e.source.split(":")[0] != "telegram"]
    # Valutazione: 25% degli esempi non Telegram tenuti da parte; gli esempi Telegram solo in valutazione.
    rng = random.Random(seed)
    shuffled = allowed[:]
    rng.shuffle(shuffled)
    cut = max(1, len(shuffled) // 4)
    held_out, train_part = shuffled[:cut], shuffled[cut:]
    test = held_out + [e for e in examples if e.source.split(":")[0] == "telegram"]
    try:
        held_model = Classifier().train(train_part)
        predictions = [p >= THRESHOLD for p in held_model.predict_proba([e.text for e in test])]
        measured = metrics([e.label for e in test], predictions)
    except TrainingDataError as exc:
        return {"errore": str(exc), "esempi": len(allowed)}
    final = Classifier().train(allowed)
    _, key = archive_bytes(final.dumps())
    session.execute(update(Modello).where(Modello.nome == "classificatore").values(attivo=False))
    session.add(
        Modello(
            nome="classificatore",
            versione=final.version,
            chiave=key,
            addestrato_da=user_id,
            metriche=measured
            | {
                "esempi_addestramento": final.trained_on,
                "esempi_valutazione": len(test),
                "telegram_esclusi": len(examples) - len(allowed),
                "motore": final.engine,
            },
        )
    )
    errors = [
        {"testo": e.text[:200], "atteso": e.label, "ottenuto": p}
        for e, p in zip(test, predictions, strict=True)
        if e.label != p
    ][:10]
    session.add(
        Valutazione(
            ambito="classificatore", versione=final.version, esempi=len(test), misure=measured, errori=errors
        )
    )
    session.flush()
    return {"versione": final.version, **measured}


def evaluate_entities(session: Session) -> dict[str, Any]:
    """Precisione e richiamo dell'estrazione delle entità sulle etichette dell'analista."""
    expected_total = found_total = correct = 0
    errors = []
    for label, element, text in labelled_examples(session):
        expected = {
            (e["tipo"], e["valore"].lower())
            for e in (label.entita or {}).get("attese", [])
            if e.get("tipo") and e.get("valore")
        }
        if not expected and not (label.entita or {}).get("verificate"):
            continue
        found = {
            (e.kind, e.value.lower())
            for e in extract(text)
            if e.kind in {k for k, _ in expected} | {"url", "dominio"}
        }
        expected_total += len(expected)
        found_total += len(found)
        correct += len(expected & found)
        for miss in sorted(expected - found)[:2]:
            errors.append({"elemento": element.id, "atteso": f"{miss[0]}: {miss[1]}", "ottenuto": "mancante"})
        for extra in sorted(found - expected)[:2]:
            errors.append(
                {"elemento": element.id, "atteso": "nessuno", "ottenuto": f"{extra[0]}: {extra[1]}"}
            )
    precision = correct / found_total if found_total else 0.0
    recall = correct / expected_total if expected_total else 0.0
    measured = {
        "precisione": round(precision, 3),
        "richiamo": round(recall, 3),
        "attese": expected_total,
        "trovate": found_total,
        "corrette": correct,
    }
    session.add(
        Valutazione(
            ambito="entita", versione="regole-1", esempi=expected_total, misure=measured, errori=errors[:10]
        )
    )
    session.flush()
    return measured


def compute_topics(session: Session, limit: int = 2000) -> dict[str, Any]:
    from extractors.topics import topics

    elements = (
        session.execute(
            select(ElementoGrezzo)
            .where(
                ElementoGrezzo.fonte.in_(["telegram", "web", "tor", "manuale"]),
                ElementoGrezzo.contenuto.isnot(None),
            )
            .order_by(ElementoGrezzo.raccolto_il.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    texts = [e.contenuto for e in elements]
    found = topics(texts)
    for t in found:
        t["esempi"] = [
            {"id": elements[i].id, "riferimento": elements[i].riferimento[:120]}
            for i in t["esempi"]
            if i < len(elements)
        ]
    session.execute(update(Modello).where(Modello.nome == "argomenti").values(attivo=False))
    session.add(
        Modello(
            nome="argomenti",
            versione=f"lda-{len(texts)}-{utcnow():%Y%m%d%H%M}",
            metriche={"argomenti": found, "documenti": len(texts)},
        )
    )
    session.flush()
    return {"argomenti": len(found), "documenti": len(texts)}


def media_without_extraction(session: Session) -> list[Media]:
    done = select(Estrazione.media_id).where(Estrazione.media_id.isnot(None))
    return (
        session.execute(
            select(Media).where(Media.tipo.in_(["immagine", "video", "audio"]), Media.id.not_in(done))
        )
        .scalars()
        .all()
    )


def label_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(ElementoGrezzo.fonte, func.count())
        .join(Etichetta, Etichetta.elemento_grezzo_id == ElementoGrezzo.id)
        .group_by(ElementoGrezzo.fonte)
    ).all()
    return {f: c for f, c in rows}
