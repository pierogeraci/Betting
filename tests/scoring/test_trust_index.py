"""Il motore deve riprodurre i numeri del foglio v0.5."""

from datetime import UTC, datetime, timedelta

import pytest

from scoring.trust_index import Bet, compute, threat, vulnerability

# Indicatori del foglio "Calcolo Vulnerabilità": No, SI, SI, SI, No, No, SI
FOGLIO = {
    "piu_account_per_conto": "assente",
    "pagamento_conto_ue": "presente",
    "assenza_registrazione": "presente",
    "assenza_documento": "presente",
    "pagamento_terze_parti": "assente",
    "pagamento_criptovalute": "assente",
    "pagamento_offshore": "presente",
}
# Tabella "Tab_Estrazione_Dati": importo puntato, importo vinto
PUNTATE = [(3, 24), (1000, 2), (5, 0), (100, 59), (0, 0), (0, 0), (0, 0), (10, 67)]


def ind(values):
    return {k: {"valore": v, "certezza": 1, "evidenza": {}} for k, v in values.items()}


def bets(rows=PUNTATE, start=None):
    start = start or datetime(2026, 11, 1, 10, tzinfo=UTC)
    return [Bet(stake=s, won=w, at=start + timedelta(minutes=i)) for i, (s, w) in enumerate(rows)]


def test_sheet_vulnerability():
    v = vulnerability(ind(FOGLIO))
    assert v.score == 11.5 and v.level == "medio" and v.coverage == 1


def test_sheet_threat():
    t = threat(bets())
    assert t.refined == {
        "numero_puntate": 5,
        "totale_scommesso": 1118,
        "numero_vittorie": 4,
        "totale_vinto": 152,
        "percentuale_vincite": 0.8,
    }
    assert [v["valore"] for v in t.variables] == [224, 152, 0.8]
    assert [v["voto"] for v in t.variables] == [2, 1, 3]
    assert t.score == 6 and t.level == "medio"


def test_sheet_trust_index():
    result = compute(ind(FOGLIO), bets())
    assert result.value == 8.75 and result.risk_class == "alto"
    assert result.detail()["versione"] == "dossier-0.5.1"


@pytest.mark.parametrize(("pct_wins", "vote"), [(0.2, 1), (0.25, 2), (0.4, 2), (0.5, 3)])
def test_middle_win_band_is_reachable(pct_wins, vote):
    # Correzione del foglio: tra 25% e 50% il voto è medio.
    rows = [(10, 5 if i < pct_wins * 20 else 0) for i in range(20)]
    v3 = next(v for v in threat(bets(rows)).variables if v["codice"] == "percentuale_vincite")
    assert v3["voto"] == vote


@pytest.mark.parametrize(("value", "lvl"), [(5.5, "basso"), (6, "medio"), (11.5, "medio"), (12, "alto")])
def test_vulnerability_thresholds(value, lvl):
    from scoring.config import level, load_rules

    assert level(value, load_rules()["vulnerabilita"]["livelli"]) == lvl


@pytest.mark.parametrize(("value", "lvl"), [(3.5, "basso"), (4, "medio"), (7, "medio"), (7.25, "alto")])
def test_index_thresholds(value, lvl):
    from scoring.config import level, load_rules

    assert level(value, load_rules()["trust_index"]["livelli"]) == lvl


def test_undetermined_is_not_absent():
    partial = dict(FOGLIO)
    partial.update(
        {
            "pagamento_criptovalute": "non_determinabile",
            "pagamento_offshore": "non_determinabile",
            "assenza_documento": "non_determinabile",
        }
    )
    v = vulnerability(ind(partial))
    assert v.score == 3.5 and v.score_max == 17.5
    assert v.coverage == pytest.approx(4 / 7, abs=0.001)
    assert v.level is None  # copertura bassa e livello incerto: nessun livello
    result = compute(ind(partial), bets())
    assert result.value is None and "Copertura" in result.excluded_reason


def test_no_bets_no_index():
    result = compute(ind(FOGLIO), [])
    assert result.value is None and result.vulnerability.level == "medio"
    assert "puntata" in result.excluded_reason


def test_licensee_excluded_and_adm_flag():
    result = compute(ind(FOGLIO), bets(), adm_outcome="concessionario")
    assert result.value is None and "Concessionario" in result.excluded_reason
    flagged = compute(ind(FOGLIO), bets(), adm_without_title=True)
    assert flagged.flags == ["adm_senza_titolo"] and flagged.value == 8.75


def test_window_and_currency():
    start = datetime(2026, 11, 1, tzinfo=UTC)
    old = [Bet(1000, 0, at=start)]
    recent = [Bet(10, 0, at=start + timedelta(hours=30, minutes=i)) for i in range(5)]
    t = threat(old + recent + [Bet(10, 0, currency="XYZ", at=start + timedelta(hours=30))])
    assert t.bets_used == 5 and t.excluded_currency == 1
    assert t.refined["totale_scommesso"] == 50
