"""Elenchi ADM: lettura dei file, caricamento versionato e confronto dei domini.

La legalità si decide solo qui, per confronto con gli elenchi: non si deduce dal
testo del sito.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import timedelta
from html.parser import HTMLParser
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core import queue
from core.config import get_settings
from core.domains import find_domain, parent_domains, registrable_domain, strip_www
from core.models import (
    AdmCaricamento,
    AdmConcessionario,
    AdmSitoInibito,
    ElementoGrezzo,
    Indicatore,
    Sito,
    Snapshot,
    Sonda,
    utcnow,
)
from core.storage import archive_bytes, sha256_hex

CONCESSIONARI = "concessionari"
INIBITI = "siti_inibiti"
ELENCHI = (CONCESSIONARI, INIBITI)
ETICHETTE = {CONCESSIONARI: "Concessionari", INIBITI: "Siti inibiti"}

COLLECTOR = "elenchi_adm"
COLLECTOR_VERSION = "1"
CODES = {CONCESSIONARI: "dominio_concessionario_adm", INIBITI: "dominio_inibito_adm"}


class UnsupportedList(ValueError):
    """File che non si riesce a leggere. Il messaggio è per l'analista."""


@dataclass
class ParsedRow:
    line: int
    domain: str
    raw: str
    license_number: str = ""
    company: str = ""


@dataclass
class ParsedList:
    rows: list[ParsedRow] = field(default_factory=list)
    total_lines: int = 0
    discarded: int = 0


def _decode(data: bytes) -> str:
    if data[:4] == b"%PDF":
        raise UnsupportedList("Il file è un PDF: serve un file di testo, CSV o HTML.")
    if data[:2] == b"PK":
        raise UnsupportedList("Il file è un foglio di calcolo o un archivio: esportalo in CSV.")
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = data.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" not in text:
            return text
    raise UnsupportedList("Codifica del file non riconosciuta.")


class _TableRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href") or ""
            if href.startswith("http"):
                self._cell.append(" " + href + " ")

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _rows_from_text(text: str) -> list[list[str]]:
    """Righe e celle, da tabella HTML oppure da testo o CSV."""
    if re.search(r"(?i)<\s*(table|html|tr)\b", text[:20000]):
        parser = _TableRows()
        parser.feed(text)
        if parser.rows:
            return parser.rows
        text = re.sub(r"(?s)<[^>]+>", "\n", text)
    lines = [line for line in text.splitlines() if line.strip()]
    sample = "\n".join(lines[:50])
    delimiter = max(";\t,|", key=sample.count)
    if sample.count(delimiter) < max(1, len(lines[:50]) // 2):
        return [[line.strip()] for line in lines]
    return [
        [c.strip() for c in row] for row in csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    ]


_LICENSE_RE = re.compile(r"\b(\d{4,6})\b")


def _header_map(cells: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, cell in enumerate(cells):
        low = cell.lower()
        if "numero" not in found and re.search(r"concession|codice|n\.|numero", low):
            found["numero"] = index
        elif "societa" not in found and re.search(
            r"ragione|denominazione|societ|concessionario|operatore", low
        ):
            found["societa"] = index
        elif "dominio" not in found and re.search(r"sito|dominio|url|indirizzo web|www", low):
            found["dominio"] = index
    return found


def parse_list(kind: str, data: bytes) -> ParsedList:
    """Legge un elenco ADM. Tollerante sul formato; le righe senza dominio sono scartate e contate."""
    if kind not in ELENCHI:
        raise UnsupportedList("Elenco sconosciuto.")
    rows = _rows_from_text(_decode(data))
    out = ParsedList(total_lines=len(rows))
    header: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for number, cells in enumerate(rows, start=1):
        raw = " | ".join(cells)[:1000]
        if number <= 5 and not header and find_domain(raw) is None:
            header = _header_map(cells)
            out.discarded += 1
            continue
        domain_cells = [cells[header["dominio"]]] if header.get("dominio", 99) < len(cells) else cells
        domains: list[str] = []
        for cell in domain_cells:
            for token in re.split(r"[\s,;]+", cell):
                host = find_domain(token) if token else None
                if host and strip_www(host) not in domains:
                    domains.append(strip_www(host))
        if not domains:
            out.discarded += 1
            continue
        license_number, company = "", ""
        if kind == CONCESSIONARI:
            if header.get("numero", 99) < len(cells):
                match = _LICENSE_RE.search(cells[header["numero"]])
                license_number = match.group(1) if match else cells[header["numero"]][:40]
            if header.get("societa", 99) < len(cells):
                company = cells[header["societa"]]
            if not license_number or not company:
                for cell in cells:
                    if find_domain(cell):
                        continue
                    if not license_number and _LICENSE_RE.fullmatch(cell.strip()):
                        license_number = cell.strip()
                    elif not company and len(cell) > 3 and re.search(r"[A-Za-z]{3}", cell):
                        company = cell
        for domain in domains:
            if (domain, license_number) in seen:
                continue
            seen.add((domain, license_number))
            out.rows.append(ParsedRow(number, domain, raw, license_number[:40], company[:500]))
    return out


def current_load(session: Session, kind: str) -> AdmCaricamento | None:
    return session.execute(
        select(AdmCaricamento)
        .where(AdmCaricamento.elenco == kind, AdmCaricamento.stato == "attivo")
        .order_by(AdmCaricamento.versione.desc())
        .limit(1)
    ).scalar_one_or_none()


def is_stale(load: AdmCaricamento | None) -> bool:
    if load is None:
        return True
    return load.verificato_il < utcnow() - timedelta(days=get_settings().adm_max_age_days)


def load_list(
    session: Session,
    kind: str,
    data: bytes,
    *,
    filename: str = "",
    source_url: str | None = None,
    user_id: int | None = None,
) -> tuple[AdmCaricamento, bool]:
    """Carica una nuova versione dell'elenco. Restituisce (caricamento, nuovo).

    Se il file è identico alla versione attiva non si crea nulla: si aggiorna solo
    la data di verifica.
    """
    digest = sha256_hex(data)
    current = current_load(session, kind)
    if current is not None and current.sha256 == digest:
        current.verificato_il = utcnow()
        session.flush()
        return current, False
    parsed = parse_list(kind, data)
    if not parsed.rows:
        raise UnsupportedList("Nel file non ho trovato alcun dominio.")
    _, key = archive_bytes(data)
    fonte = f"adm:{kind}"
    element = session.execute(
        select(ElementoGrezzo).where(ElementoGrezzo.fonte == fonte, ElementoGrezzo.sha256 == digest)
    ).scalar_one_or_none()
    if element is None:
        probe = session.execute(select(Sonda).where(Sonda.nome == "adm")).scalar_one_or_none()
        element = ElementoGrezzo(
            sonda_id=probe.id if probe else None,
            fonte=fonte,
            tipo="elenco",
            riferimento=source_url or filename,
            oggetto_chiave=key,
            sha256=digest,
            inserito_da=user_id,
            metadati={"nome_file": filename, "dimensione": len(data)},
        )
        session.add(element)
        session.flush()
    version = (
        session.execute(
            select(func.max(AdmCaricamento.versione)).where(AdmCaricamento.elenco == kind)
        ).scalar()
        or 0
    ) + 1
    note = ""
    if current is not None and len(parsed.rows) < current.righe_valide * 0.5:
        note = (
            f"Attenzione: {len(parsed.rows)} righe valide contro le {current.righe_valide} della versione "
            f"precedente. Controlla che il file sia completo."
        )
    session.execute(
        update(AdmCaricamento)
        .where(AdmCaricamento.elenco == kind, AdmCaricamento.stato == "attivo")
        .values(stato="sostituito")
    )
    load = AdmCaricamento(
        elenco=kind,
        versione=version,
        fonte_url=source_url,
        nome_file=filename[:255],
        sha256=digest,
        elemento_grezzo_id=element.id,
        righe_totali=parsed.total_lines,
        righe_valide=len(parsed.rows),
        righe_scartate=parsed.discarded,
        caricato_da=user_id,
        note=note,
    )
    session.add(load)
    session.flush()
    if kind == CONCESSIONARI:
        session.bulk_insert_mappings(
            AdmConcessionario,
            [
                {
                    "caricamento_id": load.id,
                    "numero_concessione": r.license_number,
                    "ragione_sociale": r.company,
                    "dominio": r.domain,
                    "dominio_registrabile": registrable_domain(r.domain),
                    "riga": r.line,
                    "riga_originale": r.raw,
                }
                for r in parsed.rows
            ],
        )
    else:
        session.bulk_insert_mappings(
            AdmSitoInibito,
            [
                {
                    "caricamento_id": load.id,
                    "dominio": r.domain,
                    "dominio_registrabile": registrable_domain(r.domain),
                    "riga": r.line,
                    "riga_originale": r.raw,
                }
                for r in parsed.rows
            ],
        )
    queue.enqueue(
        session, queue=queue.INTERNAL, kind="confronto_adm_tutti", payload={"elenco": kind}, user_id=user_id
    )
    session.flush()
    return load, True


@dataclass
class ListResult:
    kind: str
    value: str
    certainty: float
    evidence: dict[str, Any]


def _lookup(session: Session, kind: str, load: AdmCaricamento, host: str) -> tuple[Any, float, str] | None:
    model = AdmConcessionario if kind == CONCESSIONARI else AdmSitoInibito
    host = strip_www(host)
    parents = parent_domains(host)
    rows = (
        session.execute(select(model).where(model.caricamento_id == load.id, model.dominio.in_(parents)))
        .scalars()
        .all()
    )
    if rows:
        exact = [r for r in rows if r.dominio == host]
        if exact:
            return exact[0], 1.0, "dominio identico"
        return rows[0], 0.9, "l'elenco contiene il dominio padre"
    row = session.execute(
        select(model)
        .where(model.caricamento_id == load.id, model.dominio_registrabile == registrable_domain(host))
        .limit(1)
    ).scalar_one_or_none()
    if row is not None:
        return row, 0.6, "l'elenco contiene un altro sottodominio dello stesso dominio"
    return None


def compare_hosts(session: Session, hosts: list[str]) -> dict[str, ListResult]:
    """Confronta gli host con i due elenchi attivi.

    `assente` significa che l'elenco è stato letto per intero e il dominio non c'è;
    se l'elenco non è caricato il valore è `non_determinabile`.
    """
    results: dict[str, ListResult] = {}
    clean = list(dict.fromkeys(strip_www(h) for h in hosts if h))
    for kind in ELENCHI:
        load = current_load(session, kind)
        if load is None:
            results[kind] = ListResult(
                kind, "non_determinabile", 0.0, {"motivo": "Elenco ADM non caricato", "domini": clean}
            )
            continue
        base = {
            "elenco": kind,
            "versione_elenco": load.versione,
            "caricamento_id": load.id,
            "elenco_sha256": load.sha256,
            "elenco_verificato_il": load.verificato_il.isoformat(),
            "domini": clean,
        }
        best: tuple[Any, float, str, str] | None = None
        for host in clean:
            hit = _lookup(session, kind, load, host)
            if hit and (best is None or hit[1] > best[1]):
                best = (*hit, host)
        if best is None:
            results[kind] = ListResult(
                kind, "assente", 1.0, base | {"estratto": "Nessuna riga corrispondente"}
            )
            continue
        row, certainty, how, host = best
        evidence = base | {
            "dominio_confrontato": host,
            "dominio_in_elenco": row.dominio,
            "corrispondenza": how,
            "riga": row.riga,
            "estratto": row.riga_originale[:300],
        }
        if kind == CONCESSIONARI:
            evidence |= {"numero_concessione": row.numero_concessione, "ragione_sociale": row.ragione_sociale}
        results[kind] = ListResult(kind, "presente", certainty, evidence)
    return results


def summarize(results: dict[str, ListResult]) -> str:
    conc, inib = results[CONCESSIONARI], results[INIBITI]
    if conc.value == "presente" and conc.certainty >= 0.9:
        return "concessionario"
    if inib.value == "presente":
        return "inibito"
    if conc.value == "presente":
        return "concessionario"
    if conc.value == "assente" and inib.value == "assente":
        return "non_in_elenco"
    return "non_determinabile"


def site_hosts(session: Session, site: Sito) -> list[str]:
    hosts = [site.dominio]
    snap = session.execute(
        select(Snapshot).where(Snapshot.sito_id == site.id).order_by(Snapshot.raccolto_il.desc()).limit(1)
    ).scalar_one_or_none()
    if snap is not None:
        from urllib.parse import urlsplit

        for value in (urlsplit(snap.url_richiesto).hostname, snap.dominio_finale):
            if value and value not in hosts:
                hosts.append(value)
    return hosts


def compare_site(session: Session, site: Sito, snapshot_id: int | None = None) -> dict[str, ListResult]:
    """Confronta un sito con gli elenchi e scrive i due indicatori con la loro evidenza."""
    results = compare_hosts(session, site_hosts(session, site))
    for kind, result in results.items():
        session.add(
            Indicatore(
                sito_id=site.id,
                snapshot_id=snapshot_id,
                codice=CODES[kind],
                valore=result.value,
                evidenza=result.evidence,
                certezza=result.certainty,
                collettore=COLLECTOR,
                versione_collettore=COLLECTOR_VERSION,
            )
        )
    site.esito_adm = summarize(results)
    session.flush()
    return results
