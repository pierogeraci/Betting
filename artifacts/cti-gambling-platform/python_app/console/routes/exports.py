"""Download degli estratti operativi."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from console.deps import current_user, get_db
from console.exports import create_cti_export
from core.models import Utente

router = APIRouter()


@router.get("/esporta/excel")
def export_excel(
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    generated_at = datetime.now(UTC)
    payload = create_cti_export(db, generated_at=generated_at)
    filename = f"estrazione_cti_{generated_at:%Y%m%d_%H%M}.xlsx"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
