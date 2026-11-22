"""Area pagamenti: bonifico UE, fornitori terzi, criptovalute, conto offshore."""

from __future__ import annotations

from collectors import terms
from collectors.base import ASSENTE, ND, PRESENTE, Indicator, Page, evidence, find_terms
from collectors.pages import page_kind
from extractors.entities import extract

NOME = "pagamenti"
VERSIONE = "1"
AREA = "Pagamenti"


def _ind(code: str, value: str, certainty: float, ev: dict | None = None) -> Indicator:
    return Indicator(code, value, certainty, NOME, VERSIONE, ev or {}, AREA)


METHODS_LIST = [
    "visa",
    "mastercard",
    "maestro",
    "carta di credito",
    "credit card",
    "bonifico",
    "bank transfer",
    "paypal",
    "skrill",
    "neteller",
    "bitcoin",
    "apple pay",
    "google pay",
    "postepay",
    "paysafecard",
]
DEPOSIT_TERMS = ["deposito", "deposit", "prelievo", "withdraw", "ricarica", "top up", "versamento"]


def _payment_page_read(pages: list[Page]) -> Page | None:
    """La pagina dei metodi di pagamento letta per davvero.

    Deve essere una pagina secondaria (arrivata da un link "pagamenti" della home),
    parlare di depositi o prelievi, elencare almeno due metodi e non essere un modulo
    di accesso. Altrimenti l'assenza di un metodo non si può affermare.
    """
    for p in pages:
        if not (p.readable and p.secondary and page_kind(p) == "pagamenti"):
            continue
        if any("password" in (t + n).lower() for f in p.parsed.forms for t, n in f["inputs"]):
            continue
        if not find_terms(p, DEPOSIT_TERMS):
            continue
        listed = sum(1 for m in METHODS_LIST if find_terms(p, [m]))
        if listed >= 2:
            return p
    return None


def collect(pages: list[Page]) -> list[Indicator]:
    out: list[Indicator] = []
    cashier = _payment_page_read(pages)
    entities = [(p, e) for p in pages if p.readable for e in extract(p.text)]

    # Bonifico da conto UE
    hit = None
    for p, e in entities:
        if e.kind == "iban" and e.value[:2] in terms.EU_IBAN:
            hit = (p, f"IBAN {e.value[:4]}… ({e.value[:2]})")
            break
    if hit is None:
        for p in pages:
            found = find_terms(p, terms.BANK_TRANSFER) if p.readable else None
            if found:
                hit = (p, found[1])
                break
    if hit:
        out.append(_ind("pagamento_conto_ue", PRESENTE, 0.7, evidence(hit[0], hit[1])))
    elif cashier:
        out.append(
            _ind(
                "pagamento_conto_ue",
                ASSENTE,
                0.6,
                evidence(cashier, "Pagina dei pagamenti letta: nessun bonifico o IBAN"),
            )
        )
    else:
        out.append(_ind("pagamento_conto_ue", ND, 0.0, {"motivo": "Pagina dei pagamenti non letta"}))

    # Fornitori terzi: nel testo o tra i domini contattati
    hit = None
    for p in pages:
        if not p.readable:
            continue
        found = find_terms(p, terms.THIRD_PARTY)
        if found:
            hit = (p, found[1], found[0])
            break
        host = next(
            (h for h in p.all_hosts if any(h == t or h.endswith("." + t) for t in terms.THIRD_PARTY_HOSTS)),
            None,
        )
        if host:
            hit = (p, f"La pagina carica risorse da {host}", host)
            break
    if hit:
        out.append(_ind("pagamento_terze_parti", PRESENTE, 0.8, evidence(hit[0], hit[1], fornitore=hit[2])))
    elif cashier:
        out.append(
            _ind(
                "pagamento_terze_parti",
                ASSENTE,
                0.6,
                evidence(cashier, "Pagina dei pagamenti letta: nessun fornitore terzo"),
            )
        )
    else:
        out.append(_ind("pagamento_terze_parti", ND, 0.0, {"motivo": "Pagina dei pagamenti non letta"}))

    # Criptovalute: indirizzi di portafoglio o nomi di valute
    hit = None
    wallet = next(((p, e) for p, e in entities if e.kind.startswith("portafoglio_")), None)
    if wallet:
        hit = (wallet[0], f"Indirizzo {wallet[1].kind.split('_')[1].upper()} {wallet[1].value}", 0.9)
    else:
        for p in pages:
            found = find_terms(p, terms.CRYPTO) if p.readable else None
            if found:
                hit = (p, found[1], 0.75)
                break
    if hit:
        out.append(_ind("pagamento_criptovalute", PRESENTE, hit[2], evidence(hit[0], hit[1])))
    elif cashier:
        out.append(
            _ind(
                "pagamento_criptovalute",
                ASSENTE,
                0.6,
                evidence(cashier, "Pagina dei pagamenti letta: nessuna criptovaluta"),
            )
        )
    else:
        out.append(_ind("pagamento_criptovalute", ND, 0.0, {"motivo": "Pagina dei pagamenti non letta"}))

    # Conto offshore: IBAN di un paese offshore o dichiarazione esplicita
    hit = None
    for p, e in entities:
        if e.kind == "iban" and e.value[:2] in terms.OFFSHORE_IBAN:
            hit = (p, f"IBAN del paese {e.value[:2]}: {e.value[:4]}…")
            break
    if hit is None:
        for p in pages:
            found = find_terms(p, terms.OFFSHORE_TEXT) if p.readable else None
            if found:
                hit = (p, found[1])
                break
    if hit:
        out.append(_ind("pagamento_offshore", PRESENTE, 0.8, evidence(hit[0], hit[1])))
    else:
        # Le coordinate bancarie compaiono solo nelle istruzioni di deposito, dopo l'accesso:
        # dall'esterno la loro assenza non si può affermare.
        out.append(
            _ind(
                "pagamento_offshore", ND, 0.0, {"motivo": "Coordinate di deposito non visibili senza accesso"}
            )
        )
    return out
