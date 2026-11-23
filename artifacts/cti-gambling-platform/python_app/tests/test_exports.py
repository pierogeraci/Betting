from datetime import UTC, datetime

from openpyxl import load_workbook
from io import BytesIO

from console.exports import build_xlsx, workbook_contains_expected_v05_example


def test_workbook_produces_expected_v05_example():
    payload = build_xlsx(
        {
            "Metodo": (
                ["Voce", "Valore"],
                [
                    ["Esempio di verifica - Vulnerabilità", 11.5],
                    ["Esempio di verifica - Minaccia", 6],
                    ["Esempio di verifica - Indice", 8.75],
                    ["Esempio di verifica - Rischio", "alto"],
                ],
            )
        },
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert workbook_contains_expected_v05_example(payload)


def test_workbook_neutralizes_formula_like_text():
    payload = build_xlsx({"Evidenze": (["Testo"], [["=HYPERLINK(\"https://example.invalid\")"]])})
    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=False)

    assert workbook["Evidenze"]["A2"].data_type == "s"
    assert workbook["Evidenze"]["A2"].value.startswith("'=")
