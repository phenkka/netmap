from fastapi import APIRouter

from .. import journal

router = APIRouter(prefix="/api/journal")


@router.get("")
def entries(after: int | None = None) -> dict:
    rows = journal.recent(after)
    return {"entries": rows, "last": rows[-1]["id"] if rows else after or 0}
