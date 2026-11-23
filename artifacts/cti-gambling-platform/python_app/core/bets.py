"""Dati di puntata: lettura dei riquadri pubblici "ultime puntate" e caricamento da file.

Si conservano solo importi, esito, valuta, momento e tipo di gioco. Nomi utente,
avatar o altri dati del giocatore che i riquadri mostrano non vengono letti.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from collectors.base import Page

AMOUNT_RE = re.compile(
    r"([€$£]|EUR|USD|GBP|BTC|ETH|USDT|LTC)?\s*(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,8})|\d+(?:[.,]\d{1,8})?)\s*([€$£]|EUR|USD|GBP|BTC|ETH|USDT|LTC)?",
    re.I,
)
SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
STAKE_HEAD = re.compile(r"(?i)\b(bet|stake|puntata|importo puntato|wager|giocata|amount)\b")
PLAYER_HEAD = re.compile(r"(?i)player|gamer|user|utente|giocatore|nick|name|nome|account")
WIN_HEAD = re.compile(r"(?i)\b(win|payout|vincita|vinto|profit|vincite|prize)\b")


@dataclass
class BetRow:
    stake: float
    won: float
    currency: str
    at: datetime | None = None
    game: str | None = None


def parse_amount(text: str) -> tuple[float, str] | None:
    m = AMOUNT_RE.search(text or "")
    if not m:
        return None
    raw = m.group(2).replace(" ", "")
    if "," in raw and "." in raw:
        raw = (
            raw.replace(".", "").replace(",", ".")
            if raw.rfind(",") > raw.rfind(".")
            else raw.replace(",", "")
        )
    elif "," in raw:
        raw = raw.replace(",", ".") if len(raw.split(",")[-1]) != 3 else raw.replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    unit = (m.group(1) or m.group(3) or "EUR").upper()
    return value, SYMBOLS.get(unit, unit)


class _Tables:
    def __init__(self, html: str) -> None:
        from html.parser import HTMLParser

        self.tables: list[list[list[str]]] = []
        outer = self

        class P(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.row = None
                self.cell = None

            def handle_starttag(self, tag, attrs):
                if tag == "table":
                    outer.tables.append([])
                elif tag == "tr" and outer.tables:
                    self.row = []
                elif tag in {"td", "th"} and self.row is not None:
                    self.cell = []

            def handle_endtag(self, tag):
                if tag in {"td", "th"} and self.cell is not None and self.row is not None:
                    self.row.append(" ".join("".join(self.cell).split()))
                    self.cell = None
                elif tag == "tr" and self.row is not None and outer.tables:
                    outer.tables[-1].append(self.row)
                    self.row = None

            def handle_data(self, data):
                if self.cell is not None:
                    self.cell.append(data)

        try:
            P().feed(html or "")
        except Exception:  # noqa: BLE001, S110 - HTML malformato: si usa quel che si è letto
            pass


def observed_bets(page: Page) -> list[BetRow]:
    """Puntate dai riquadri pubblici: tabelle con una colonna di puntata e una di vincita."""
    rows: list[BetRow] = []
    for table in _Tables(page.html).tables:
        if len(table) < 3:
            continue
        header = table[0]
        stake_col = next(
            (i for i, h in enumerate(header) if STAKE_HEAD.search(h) and not WIN_HEAD.search(h)), None
        )
        win_col = next((i for i, h in enumerate(header) if WIN_HEAD.search(h)), None)
        if stake_col is None or win_col is None:
            continue
        # Colonna del gioco: parola intera, mai un'intestazione che indica il giocatore.
        game_col = next(
            (
                i
                for i, h in enumerate(header)
                if re.search(r"(?i)\b(game|gioco|slot|evento|event)\b", h) and not PLAYER_HEAD.search(h)
            ),
            None,
        )
        for row in table[1:]:
            if len(row) <= max(stake_col, win_col):
                continue
            stake = parse_amount(row[stake_col])
            won = parse_amount(row[win_col])
            if stake is None:
                continue
            won_value = 0.0 if won is None or row[win_col].strip() in {"-", "0", "—"} else won[0]
            rows.append(
                BetRow(
                    stake[0],
                    won_value,
                    stake[1],
                    None,
                    row[game_col][:40] if game_col is not None and game_col < len(row) else None,
                )
            )
    return rows


REQUIRED = {"importo_puntato", "importo_vinto"}


def parse_upload(data: bytes) -> tuple[list[BetRow], list[str]]:
    """CSV caricato dall'analista: importo_puntato, importo_vinto, valuta, momento, tipo_gioco."""
    text = data.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.count(";") > text.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fields = {f.strip().lower() for f in (reader.fieldnames or [])}
    if not REQUIRED <= fields:
        raise ValueError(
            "Il file deve avere le colonne importo_puntato e importo_vinto (facoltative: valuta, momento, tipo_gioco)."
        )
    rows, errors = [], []
    for n, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        stake = parse_amount(row.get("importo_puntato", ""))
        won = parse_amount(row.get("importo_vinto", "")) or (0.0, "EUR")
        if stake is None:
            errors.append(f"Riga {n}: importo puntato non leggibile")
            continue
        at = None
        if row.get("momento"):
            try:
                at = datetime.fromisoformat(row["momento"].replace("Z", "+00:00"))
                at = at if at.tzinfo else at.replace(tzinfo=UTC)
            except ValueError:
                errors.append(f"Riga {n}: data non leggibile, usa il formato 2026-11-01T10:30:00")
                continue
        currency = (row.get("valuta") or stake[1] or "EUR").upper()
        rows.append(BetRow(stake[0], won[0], currency, at, (row.get("tipo_gioco") or None)))
        if len(rows) > 100_000:
            raise ValueError("Al massimo 100.000 righe per file.")
    return rows, errors
