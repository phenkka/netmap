from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from .. import backup, journal

router = APIRouter(prefix="/api/backup")


@router.get("/export")
def export(request: Request) -> Response:
    blob = backup.pack()
    journal.note(request, journal.EXPORT, None, f"{len(blob)} байт")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        blob,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="netmap-{stamp}.json.gz"'},
    )


@router.post("/import")
async def restore(request: Request) -> dict:
    blob = await request.body()
    if not blob:
        raise HTTPException(400, "пустой файл")

    try:
        result = backup.unpack(blob)
    except ValueError as exc:
        journal.note(request, journal.IMPORT, None, str(exc), False)
        raise HTTPException(400, str(exc))

    journal.note(
        request,
        journal.IMPORT,
        None,
        f"добавлено версий {result['configs']}, эталонов {result['baselines']}",
    )
    return result
