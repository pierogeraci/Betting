"""Profilazione di un sito: dalle pagine archiviate agli indicatori, al punteggio, ai gemelli."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

import collectors
from collectors.base import Page
from core import queue
from core.bets import observed_bets
from core.domains import registrable_domain
from core.intake import get_or_create_entity, link_entities
from core.models import (
    ElementoGrezzo,
    Indicatore,
    Lavoro,
    LegameSito,
    Puntata,
    Punteggio,
    Revisione,
    Sito,
    Snapshot,
    utcnow,
)
from core.storage import read_archive
from scoring.config import load_rules
from scoring.trust_index import Bet, compute

PAGES_MAX_AGE_DAYS = 30
VULN_CODES = list(load_rules()["vulnerabilita"]["voci"])


def traffic_hosts(har: bytes) -> list[str]:
    try:
        entries = json.loads(har)["log"]["entries"]
    except (ValueError, KeyError, TypeError):
        return []
    return sorted(
        {(urlsplit(str(e.get("request", {}).get("url", ""))).hostname or "").lower() for e in entries[:3000]}
        - {""}
    )


def latest_network(session: Session, domain: str) -> dict[str, Any]:
    element = session.execute(
        select(ElementoGrezzo)
        .where(ElementoGrezzo.fonte == "rete", ElementoGrezzo.riferimento == domain)
        .order_by(ElementoGrezzo.raccolto_il.desc())
        .limit(1)
    ).scalar_one_or_none()
    if element is None or not element.contenuto:
        return {}
    try:
        return json.loads(element.contenuto)
    except ValueError:
        return {}


def site_pages(session: Session, site: Sito) -> list[Page]:
    """Ultimo snapshot per ciascun URL del sito, la home per prima."""
    since = utcnow() - timedelta(days=PAGES_MAX_AGE_DAYS)
    snaps = (
        session.execute(
            select(Snapshot)
            .where(Snapshot.sito_id == site.id, Snapshot.raccolto_il >= since)
            .order_by(Snapshot.raccolto_il.desc())
        )
        .scalars()
        .all()
    )
    latest: dict[str, Snapshot] = {}
    for snap in snaps:
        latest.setdefault(snap.url_richiesto, snap)
    ordered = sorted(
        latest.values(), key=lambda s: (bool(s.metadati.get("secondaria")), -s.raccolto_il.timestamp())
    )
    network = latest_network(session, site.dominio)
    pages: list[Page] = []
    for snap in ordered:
        html = read_archive(snap.html_chiave).decode("utf-8", "replace") if snap.html_chiave else ""
        hosts = traffic_hosts(read_archive(snap.traffico_chiave)) if snap.traffico_chiave else []
        extra = {
            "icona_sha256": snap.metadati.get("icona_sha256"),
            "secondaria": bool(snap.metadati.get("secondaria")),
        }
        if not pages:
            extra["rete"] = network
        pages.append(
            Page(
                url=snap.url_finale or snap.url_richiesto,
                html=html,
                snapshot_id=snap.id,
                status=snap.stato,
                traffic_hosts=hosts,
                title=snap.titolo or "",
                extra=extra,
            )
        )
    return pages


def iban_fingerprint(iban: str) -> str:
    """Un IBAN può essere di una persona: si conservano paese e banca, più un'impronta per i confronti."""
    import hashlib

    clean = iban.replace(" ", "").upper()
    return f"{clean[:2]}…{clean[4:9]} #{hashlib.sha256(clean.encode()).hexdigest()[:16]}"


ENTITY_FROM_INDICATOR = {
    "ragione_sociale_dichiarata": ("societa", "valore"),
    "partita_iva_dichiarata": ("partita_iva", "valore"),
    "numero_concessione_dichiarato": ("concessione_adm", "numero"),
}


def _register_entities(session: Session, site: Sito, rows: list[dict[str, Any]], pages: list[Page]) -> None:
    domain = get_or_create_entity(session, "dominio", site.dominio)
    for row in rows:
        if row["valore"] != "presente":
            continue
        ev = row["evidenza"]
        if row["codice"] in ENTITY_FROM_INDICATOR:
            kind, key = ENTITY_FROM_INDICATOR[row["codice"]]
            if ev.get(key):
                link_entities(
                    session, domain, get_or_create_entity(session, kind, str(ev[key])[:200]), "dichiara"
                )
        elif row["codice"] == "licenza_estera_dichiarata":
            for name in ev.get("licenze", []):
                link_entities(session, domain, get_or_create_entity(session, "licenza", name), "dichiara")
        elif row["codice"] == "identificativi_tracciamento":
            for kind, values in ev.get("identificativi", {}).items():
                for value in values:
                    link_entities(
                        session,
                        domain,
                        get_or_create_entity(session, "tracciamento", f"{kind}:{value}"),
                        "usa",
                    )
        elif row["codice"] == "pagamento_terze_parti" and ev.get("fornitore"):
            link_entities(
                session,
                domain,
                get_or_create_entity(session, "fornitore_pagamento", ev["fornitore"]),
                "accetta",
            )
    from extractors.entities import extract

    for page in pages:
        if page.readable:
            for e in extract(page.text):
                if e.kind.startswith("portafoglio_"):
                    link_entities(session, domain, get_or_create_entity(session, e.kind, e.value), "pubblica")
                elif e.kind == "iban":
                    link_entities(
                        session,
                        domain,
                        get_or_create_entity(session, "iban", iban_fingerprint(e.value)),
                        "pubblica",
                    )


def _store_observed_bets(session: Session, site: Sito, pages: list[Page]) -> int:
    count = 0
    for page in pages:
        if page.status != "riuscito" or page.snapshot_id is None:
            continue
        if session.execute(
            select(Puntata.id).where(Puntata.snapshot_id == page.snapshot_id).limit(1)
        ).first():
            continue
        snap_time = session.get(Snapshot, page.snapshot_id).raccolto_il
        for row in observed_bets(page):
            session.add(
                Puntata(
                    sito_id=site.id,
                    tipo_gioco=row.game,
                    importo_puntato=row.stake,
                    importo_vinto=row.won,
                    valuta=row.currency,
                    momento=snap_time,
                    fonte="osservata",
                    snapshot_id=page.snapshot_id,
                )
            )
            count += 1
    return count


def _open_review(session: Session, site: Sito, kind: str, reason: str) -> None:
    exists = session.execute(
        select(Revisione.id).where(
            Revisione.sito_id == site.id, Revisione.tipo == kind, Revisione.stato != "chiusa"
        )
    ).first()
    if not exists:
        session.add(Revisione(tipo=kind, sito_id=site.id, motivo=reason))


def latest_indicators(session: Session, site_id: int) -> dict[str, Indicatore]:
    out: dict[str, Indicatore] = {}
    for ind in session.execute(
        select(Indicatore)
        .where(Indicatore.sito_id == site_id)
        .order_by(Indicatore.rilevato_il.desc(), Indicatore.id.desc())
    ).scalars():
        out.setdefault(ind.codice, ind)
    return out


def score_site(session: Session, site: Sito) -> list[Punteggio]:
    """Nuovi punteggi per la piattaforma e per ogni tipo di gioco con dati di puntata. Lo storico resta."""
    rules = load_rules()
    inds = latest_indicators(session, site.id)
    vuln = {
        c: {"valore": i.valore, "certezza": float(i.certezza), "evidenza": i.evidenza}
        for c, i in inds.items()
        if c in VULN_CODES
    }
    adm_flag = (
        any(
            inds.get(c) is not None and inds[c].valore == "presente"
            for c in ("logo_adm_esposto", "numero_concessione_dichiarato")
        )
        and site.esito_adm != "concessionario"
    )
    bets = session.execute(select(Puntata).where(Puntata.sito_id == site.id)).scalars().all()
    scopes: dict[str, list[Bet]] = {"piattaforma": []}
    for b in bets:
        bet = Bet(float(b.importo_puntato), float(b.importo_vinto), b.valuta, b.momento, b.tipo_gioco)
        scopes["piattaforma"].append(bet)
        if b.tipo_gioco:
            scopes.setdefault(f"gioco:{b.tipo_gioco}", []).append(bet)
    results = []
    for scope, scope_bets in scopes.items():
        res = compute(
            vuln, scope_bets, adm_outcome=site.esito_adm, adm_without_title=adm_flag, scope=scope, rules=rules
        )
        detail = res.detail()
        detail["indicatori_usati"] = {c: inds[c].id for c in vuln}
        row = Punteggio(
            sito_id=site.id,
            ambito=scope,
            vulnerabilita=res.vulnerability.score,
            livello_vulnerabilita=res.vulnerability.level,
            minaccia=res.threat.score,
            livello_minaccia=res.threat.level,
            trust_index=res.value,
            classe_rischio=res.risk_class,
            copertura=res.vulnerability.coverage,
            versione_regole=rules["version"],
            dettaglio=detail,
        )
        session.add(row)
        results.append(row)
    platform = results[0].dettaglio
    if adm_flag:
        _open_review(
            session,
            site,
            "adm_senza_titolo",
            "Il sito espone logo o numero di concessione ADM ma non compare nell'elenco dei concessionari: segnalazione immediata.",
        )
    if platform["esclusione"] and platform["esclusione"].startswith("Copertura"):
        _open_review(session, site, "copertura_bassa", platform["esclusione"])
    session.flush()
    return results


# --- Domini gemelli -----------------------------------------------------------------

TWIN_SIGNALS = {
    "identificativi_tracciamento": "tracciamento",
    "icona_sito": "icona",
    "impronta_html": "struttura_html",
    "dati_rete": "ip",
}


def _signals(ind: Indicatore) -> list[str]:
    ev = ind.evidenza or {}
    if ind.codice == "identificativi_tracciamento":
        return [f"{k}:{v}" for k, values in ev.get("identificativi", {}).items() for v in values]
    if ind.codice == "icona_sito":
        return [ev["hash"]] if ev.get("hash") else []
    if ind.codice == "dati_rete":
        cert = (ev.get("certificato") or {}).get("impronta_sha256")
        return ([f"cert:{cert}"] if cert else []) + [f"ip:{ip}" for ip in list(ev.get("ip", []))[:5]]
    if ind.codice == "impronta_html":
        return [ev["impronta"]] if ev.get("impronta") else []
    return []


def update_twins(session: Session, site: Sito) -> int:
    """Collega il sito ai siti che condividono identificativi, icona, IP o struttura HTML."""
    from collectors.infrastruttura import simhash_distance

    mine = latest_indicators(session, site.id)
    added = 0
    for code, reason in TWIN_SIGNALS.items():
        ind = mine.get(code)
        if ind is None or ind.valore != "presente":
            continue
        values = _signals(ind)
        if not values:
            continue
        others = (
            session.execute(
                select(Indicatore)
                .where(
                    Indicatore.codice == code, Indicatore.valore == "presente", Indicatore.sito_id != site.id
                )
                .order_by(Indicatore.rilevato_il.desc())
            )
            .scalars()
            .all()
        )
        seen_sites: set[int] = set()
        for other in others:
            if other.sito_id in seen_sites:
                continue
            seen_sites.add(other.sito_id)
            theirs = _signals(other)
            if code == "impronta_html":
                shared = [values[0]] if theirs and simhash_distance(values[0], theirs[0]) <= 3 else []
            else:
                shared = sorted(set(values) & set(theirs))
            for value in shared:
                # Stesso IP: indizio debole (hosting condiviso). Struttura HTML: indizio medio.
                strength = 0.4 if value.startswith("ip:") else 0.5 if code == "impronta_html" else 1.0
                a, b = sorted((site.id, other.sito_id))
                exists = session.execute(
                    select(LegameSito.id).where(
                        LegameSito.sito_a == a,
                        LegameSito.sito_b == b,
                        LegameSito.motivo == reason,
                        LegameSito.valore == value[:500],
                    )
                ).first()
                if not exists:
                    session.add(
                        LegameSito(sito_a=a, sito_b=b, motivo=reason, valore=value[:500], forza=strength)
                    )
                    added += 1
    session.flush()
    _regroup(session)
    return added


def _regroup(session: Session) -> None:
    """Gruppi di siti collegati da legami forti (forza ≥ 0.5), con union-find."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in session.execute(
        select(LegameSito.sito_a, LegameSito.sito_b).where(LegameSito.forza >= 0.5)
    ).all():
        parent[find(a)] = find(b)
    members: dict[int, list[int]] = {}
    for node in list(parent):
        members.setdefault(find(node), []).append(node)
    session.execute(Sito.__table__.update().where(Sito.gruppo.isnot(None)).values(gruppo=None))
    for nodes in members.values():
        session.execute(Sito.__table__.update().where(Sito.id.in_(nodes)).values(gruppo=min(nodes)))


def twins_of(session: Session, site_id: int) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(LegameSito)
            .where(or_(LegameSito.sito_a == site_id, LegameSito.sito_b == site_id))
            .order_by(LegameSito.forza.desc())
        )
        .scalars()
        .all()
    )
    by_site: dict[int, dict[str, Any]] = {}
    for row in rows:
        other = row.sito_b if row.sito_a == site_id else row.sito_a
        item = by_site.setdefault(other, {"sito": session.get(Sito, other), "motivi": []})
        item["motivi"].append({"motivo": row.motivo, "valore": row.valore, "forza": float(row.forza)})
    return list(by_site.values())


# --- Passo completo ------------------------------------------------------------------


def profile_site(session: Session, site: Sito) -> dict[str, Any]:
    pages = site_pages(session, site)
    if not pages:
        return {"saltato": "nessuno snapshot"}
    rows: list[dict[str, Any]] = []
    for module in collectors.ALL:
        for ind in module.collect(pages):
            row = ind.as_row()
            if row["evidenza"].get("snapshot_id") is None and pages:
                snapshot_id = pages[0].snapshot_id
            else:
                snapshot_id = row["evidenza"].get("snapshot_id")
            session.add(Indicatore(sito_id=site.id, snapshot_id=snapshot_id, **row))
            rows.append(row)
    session.flush()
    _register_entities(session, site, rows, pages)
    bets = _store_observed_bets(session, site, pages)
    scores = score_site(session, site)
    twins = update_twins(session, site)
    platform = scores[0]
    return {
        "indicatori": len(rows),
        "pagine": len(pages),
        "puntate_osservate": bets,
        "nuovi_legami": twins,
        "classe": platform.classe_rischio,
        "vulnerabilita": float(platform.vulnerabilita or 0),
    }


def request_profile(session: Session, site: Sito, user_id: int | None = None) -> Lavoro | None:
    pending = session.execute(
        select(Lavoro.id).where(
            Lavoro.tipo == "profila", Lavoro.sito_id == site.id, Lavoro.stato.in_(["in_attesa", "in_corso"])
        )
    ).first()
    if pending:
        return None
    return queue.enqueue(
        session,
        queue=queue.INTERNAL,
        kind="profila",
        payload={"sito_id": site.id},
        site_id=site.id,
        user_id=user_id,
    )


def request_secondary_pages(
    session: Session, site: Sito, snapshot: Snapshot, user_id: int | None = None
) -> int:
    """Dalla home appena letta, chiede lo snapshot delle pagine pubbliche utili alla profilazione."""
    from collectors.pages import links_to_profile
    from core.intake import request_snapshot

    if snapshot.stato != "riuscito" or snapshot.metadati.get("secondaria") or not snapshot.html_chiave:
        return 0
    page = Page(
        url=snapshot.url_finale or snapshot.url_richiesto,
        html=read_archive(snapshot.html_chiave).decode("utf-8", "replace"),
    )
    since = utcnow() - timedelta(days=7)
    done = set(
        session.execute(
            select(Snapshot.url_richiesto).where(Snapshot.sito_id == site.id, Snapshot.raccolto_il >= since)
        ).scalars()
    )
    count = 0
    for url in links_to_profile(page):
        if url in done or registrable_domain(urlsplit(url).hostname or "") != site.dominio:
            continue
        request_snapshot(session, site, url, user_id, secondary=True)
        count += 1
    return count


def request_network(session: Session, site: Sito, user_id: int | None = None) -> Lavoro | None:
    since = utcnow() - timedelta(days=7)
    recent = session.execute(
        select(func.count())
        .select_from(ElementoGrezzo)
        .where(
            ElementoGrezzo.fonte == "rete",
            ElementoGrezzo.riferimento == site.dominio,
            ElementoGrezzo.raccolto_il >= since,
        )
    ).scalar()
    pending = session.execute(
        select(Lavoro.id).where(
            Lavoro.tipo == "rete", Lavoro.sito_id == site.id, Lavoro.stato.in_(["in_attesa", "in_corso"])
        )
    ).first()
    if recent or pending or site.dominio.endswith(".onion"):
        return None
    return queue.enqueue(
        session,
        queue=queue.COLLECT,
        kind="rete",
        payload={"dominio": site.dominio},
        next_kind="acquisisci_rete",
        site_id=site.id,
        user_id=user_id,
        max_attempts=2,
    )


def clear_bets(session: Session, site_id: int, source: str) -> int:
    return session.execute(
        delete(Puntata).where(Puntata.sito_id == site_id, Puntata.fonte == source)
    ).rowcount
