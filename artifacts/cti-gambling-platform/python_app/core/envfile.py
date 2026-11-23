"""Genera un file .env con segreti casuali a partire da .env.example."""

from __future__ import annotations

import secrets
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    target = root / ".env"
    if target.exists():
        print(".env esiste già: non lo tocco.")
        return
    values: dict[str, str] = {}
    lines = []
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        if "CAMBIAMI" in line and "=" in line and not line.startswith("#"):
            name = line.split("=", 1)[0]
            if name == "DATABASE_URL":
                line = (
                    f"DATABASE_URL=postgresql://betting:{values['POSTGRES_PASSWORD']}@localhost:5432/betting"
                )
            else:
                values[name] = secrets.token_hex(16)
                line = f"{name}={values[name]}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(0o600)
    print("Creato .env con segreti casuali.")


if __name__ == "__main__":
    main()
