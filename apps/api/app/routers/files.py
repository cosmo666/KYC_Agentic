from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings

router = APIRouter(prefix="/uploads", tags=["files"])


@router.get("/{session_id}/{filename}")
async def get_upload(session_id: str, filename: str) -> FileResponse:
    """Serve an image saved under /data/uploads/<session>/<file>.

    Used by the FE to display the cropped Aadhaar photo + the user's selfie
    on the verdict card. Soft auth: the session UUID in the URL is unguessable.
    Filename is constrained to a safe set of names we actually write.
    """
    if "/" in session_id or ".." in session_id or "\\" in session_id:
        raise HTTPException(400, "Invalid session_id")
    if "/" in filename or ".." in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")

    root = Path(get_settings().upload_dir).resolve()
    target = (root / session_id / filename).resolve()

    # Defence-in-depth: ensure resolved path is still inside the upload root.
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(400, "Path escapes upload root") from exc

    if not target.is_file():
        raise HTTPException(404, "File not found")

    return FileResponse(
        target,
        headers={"Cache-Control": "private, max-age=300"},
    )
