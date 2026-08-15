import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import routes, store, watch

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="netmap")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

for router in routes.ALL:
    app.include_router(router)


@app.on_event("startup")
async def startup() -> None:
    store.init()
    asyncio.create_task(watch.run())


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
