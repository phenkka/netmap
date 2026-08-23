import asyncio
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import auth, routes, store, watch

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

class Fresh(StaticFiles):

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="netmap")
app.mount("/static", Fresh(directory=STATIC_DIR), name="static")

for router in routes.PUBLIC:
    app.include_router(router)

for router in routes.GUARDED:
    app.include_router(router, dependencies=[Depends(auth.require)])

for router in routes.SOCKETS:
    app.include_router(router)


@app.on_event("startup")
async def startup() -> None:
    store.init()
    asyncio.create_task(watch.run())


@app.get("/")
def index(request: Request) -> FileResponse:
    if not auth.configured():
        page = "setup.html"
    elif auth.session(request):
        page = "index.html"
    else:
        page = "login.html"
    # без запрета браузер отдаст из кеша страницу входа уже вошедшему
    return FileResponse(STATIC_DIR / page, headers={"Cache-Control": "no-store"})
