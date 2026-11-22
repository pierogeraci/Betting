"""Anomalie sui conti di gioco, solo su dati sintetici (vincolo 5).

I conti e i movimenti sono generati qui, con anomalie inserite e note: così si può
misurare quante ne trova il modulo. I dati reali di un operatore non entrano nel
prototipo. Le variabili sono quelle della relazione tecnica:
importi erogati rispetto ai puntati, concentrazione di vincite o perdite nel tempo,
frequenza delle ricariche, strumenti e valute (anche crypto), conti sospesi con
movimenti rilevanti, sessioni di gioco.
Regole esplicite più un modello di anomalia; ogni segnalazione dice quale indicatore l'ha generata.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Any

PATTERNS = (
    "riciclaggio_ricariche",
    "vincite_concentrate",
    "crypto_e_prelievi",
    "conto_sospeso_attivo",
    "erogato_su_puntato",
)


@dataclass
class Account:
    code: str
    status: str = "attivo"
    deposits: list[tuple[int, float, str, str]] = field(
        default_factory=list
    )  # (ora, importo, strumento, valuta)
    bets: list[tuple[int, float, float]] = field(default_factory=list)  # (ora, puntato, vinto)
    withdrawals: list[tuple[int, float]] = field(default_factory=list)
    injected: str | None = None


def generate(
    n_accounts: int = 300, anomaly_rate: float = 0.06, seed: int = 7, days: int = 30
) -> list[Account]:
    """Popolazione sintetica: conti ordinari più una quota con uno dei cinque schemi anomali."""
    rng = random.Random(seed)  # noqa: S311 - dati sintetici ripetibili
    hours = days * 24
    accounts = []
    for i in range(n_accounts):
        acc = Account(f"SINT-{i:05d}")
        for _ in range(rng.randint(1, 6)):
            acc.deposits.append(
                (
                    rng.randrange(hours),
                    round(rng.uniform(10, 150), 2),
                    rng.choice(["carta", "carta", "bonifico", "portafoglio"]),
                    "EUR",
                )
            )
        for _ in range(rng.randint(5, 80)):
            stake = round(rng.uniform(1, 30), 2)
            acc.bets.append(
                (
                    rng.randrange(hours),
                    stake,
                    round(stake * rng.uniform(1.5, 3), 2) if rng.random() < 0.42 else 0.0,
                )
            )
        if rng.random() < 0.3:
            acc.withdrawals.append((rng.randrange(hours), round(rng.uniform(10, 120), 2)))
        if rng.random() < anomaly_rate:
            acc.injected = rng.choice(PATTERNS)
            _inject(acc, acc.injected, rng, hours)
        accounts.append(acc)
    return accounts


def _inject(acc: Account, pattern: str, rng: random.Random, hours: int) -> None:
    t = rng.randrange(hours - 30)
    if pattern == "riciclaggio_ricariche":
        acc.deposits += [
            (t + k, 480.0, rng.choice(["voucher", "portafoglio"]), "EUR") for k in range(rng.randint(12, 20))
        ]
        acc.bets += [(t + k, 5.0, 4.5) for k in range(4)]
        acc.withdrawals.append((t + 25, 5500.0))
    elif pattern == "vincite_concentrate":
        acc.bets += [(t + k % 3, 50.0, 400.0) for k in range(15)]
    elif pattern == "crypto_e_prelievi":
        acc.deposits += [(t + k, 900.0, "crypto", rng.choice(["USDT", "BTC"])) for k in range(6)]
        acc.withdrawals += [(t + 10, 2500.0), (t + 12, 2500.0)]
    elif pattern == "conto_sospeso_attivo":
        acc.status = "sospeso"
        acc.deposits.append((t, 2000.0, "bonifico", "EUR"))
        acc.withdrawals.append((t + 2, 1900.0))
    elif pattern == "erogato_su_puntato":
        acc.bets += [(t + k, 20.0, 160.0) for k in range(10)]
        acc.withdrawals.append((t + 15, 1400.0))


def features(acc: Account) -> dict[str, float]:
    staked = sum(b[1] for b in acc.bets) or 1e-9
    won = sum(b[2] for b in acc.bets)
    deposited = sum(d[1] for d in acc.deposits)
    withdrawn = sum(w[1] for w in acc.withdrawals)
    wins_by_window: dict[int, int] = {}
    for hour, _, w in acc.bets:
        if w > 0:
            wins_by_window[hour // 6] = wins_by_window.get(hour // 6, 0) + 1
    day_counts: dict[int, int] = {}
    for hour, *_ in acc.deposits:
        day_counts[hour // 24] = day_counts.get(hour // 24, 0) + 1
    return {
        "erogato_su_puntato": won / staked,
        "vincite_max_6h": max(wins_by_window.values(), default=0),
        "ricariche_max_giorno": max(day_counts.values(), default=0),
        "quota_crypto": sum(d[1] for d in acc.deposits if d[2] == "crypto") / (deposited or 1e-9),
        "quota_voucher_portafogli": sum(d[1] for d in acc.deposits if d[2] in {"voucher", "portafoglio"})
        / (deposited or 1e-9),
        "prelevato_su_depositato": withdrawn / (deposited or 1e-9),
        "giocato_su_depositato": staked / (deposited or 1e-9),
        "sospeso_con_movimenti": 1.0 if acc.status == "sospeso" and (deposited + withdrawn) > 500 else 0.0,
        "depositato": deposited,
    }


RULES = [
    (
        "erogato_su_puntato",
        lambda f: f["erogato_su_puntato"] > 3,
        "Importi erogati molto superiori ai puntati",
    ),
    ("vincite_max_6h", lambda f: f["vincite_max_6h"] >= 10, "Concentrazione anomala di vincite in 6 ore"),
    ("ricariche_max_giorno", lambda f: f["ricariche_max_giorno"] >= 8, "Frequenza anomala delle ricariche"),
    (
        "quota_crypto",
        lambda f: f["quota_crypto"] > 0.5 and f["prelevato_su_depositato"] > 0.6,
        "Depositi in criptovalute e prelievo rapido",
    ),
    (
        "giocato_su_depositato",
        lambda f: (
            f["depositato"] > 3000 and f["giocato_su_depositato"] < 0.1 and f["prelevato_su_depositato"] > 0.5
        ),
        "Fondi depositati e ritirati quasi senza giocare",
    ),
    (
        "sospeso_con_movimenti",
        lambda f: f["sospeso_con_movimenti"] > 0,
        "Conto sospeso con movimenti rilevanti",
    ),
]


def detect(accounts: list[Account], contamination: float = 0.05, seed: int = 7) -> list[dict[str, Any]]:
    from sklearn.ensemble import IsolationForest

    feats = [features(a) for a in accounts]
    names = [k for k in feats[0] if k != "depositato"]
    matrix = [[f[k] for k in names] for f in feats]
    model = IsolationForest(contamination=contamination, random_state=seed).fit(matrix)
    scores = model.decision_function(matrix)
    flags = model.predict(matrix)
    means = {k: mean(f[k] for f in feats) for k in names}
    stds = {k: pstdev([f[k] for f in feats]) or 1e-9 for k in names}
    out = []
    for acc, f, score, flag in zip(accounts, feats, scores, flags, strict=True):
        reasons = [
            {"indicatore": code, "descrizione": text, "valore": round(f[code], 3)}
            for code, rule, text in RULES
            if rule(f)
        ]
        if flag == -1 and not reasons:
            top = max(names, key=lambda k: abs(f[k] - means[k]) / stds[k])
            reasons.append(
                {
                    "indicatore": top,
                    "descrizione": "Valore fuori dalla norma della popolazione (modello di anomalia)",
                    "valore": round(f[top], 3),
                }
            )
        if reasons:
            out.append(
                {
                    "conto": acc.code,
                    "stato": acc.status,
                    "punteggio_anomalia": round(float(-score), 3),
                    "motivi": reasons,
                    "schema_inserito": acc.injected,
                    "indicatori": {k: round(v, 3) for k, v in f.items()},
                }
            )
    return sorted(out, key=lambda r: -r["punteggio_anomalia"])


def evaluate(accounts: list[Account], flagged: list[dict[str, Any]]) -> dict[str, Any]:
    truth = {a.code for a in accounts if a.injected}
    found = {r["conto"] for r in flagged}
    tp = len(truth & found)
    return {
        "conti": len(accounts),
        "anomalie_inserite": len(truth),
        "segnalati": len(found),
        "precisione": round(tp / len(found), 3) if found else 0.0,
        "richiamo": round(tp / len(truth), 3) if truth else 0.0,
        "per_schema": {
            p: f"{len({a.code for a in accounts if a.injected == p} & found)}/{sum(1 for a in accounts if a.injected == p)}"
            for p in PATTERNS
        },
    }


def run(n_accounts: int = 300, anomaly_rate: float = 0.06, seed: int = 7) -> dict[str, Any]:
    accounts = generate(n_accounts, anomaly_rate, seed)
    flagged = detect(accounts, seed=seed)
    return {
        "dati": "sintetici",
        "seme": seed,
        "valutazione": evaluate(accounts, flagged),
        "segnalazioni": flagged[:100],
    }
