from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import baseline, journal, store

router = APIRouter(prefix="/api/baselines")


class FromVersion(BaseModel):
    name: str
    version_id: int


class Attach(BaseModel):
    ips: list[str]


@router.get("")
def all_baselines() -> dict:
    return {"baselines": store.baselines(), "attached": store.attached()}


@router.post("")
def create(body: FromVersion, request: Request) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "у эталона должно быть имя")

    made = baseline.from_version(name, body.version_id)
    if not made:
        raise HTTPException(404, "версия не найдена")

    journal.note(request, journal.BASELINE_SAVE, None, f"{name} из версии {body.version_id}")
    return {"baseline": made}


@router.delete("/{baseline_id}")
def drop(baseline_id: int, request: Request) -> dict:
    model = store.baseline(baseline_id)
    if not model:
        raise HTTPException(404, "эталон не найден")

    detached = [ip for ip, at in store.attached().items() if at == baseline_id]
    store.forget_baseline(baseline_id)
    for ip in detached:
        store.save_drift(ip, None)

    journal.note(request, journal.BASELINE_DROP, None, model["name"])
    return {"ok": True}


@router.post("/{baseline_id}/devices")
def attach(baseline_id: int, body: Attach, request: Request) -> dict:
    model = store.baseline(baseline_id)
    if not model:
        raise HTTPException(404, "эталон не найден")

    for ip in body.ips:
        store.attach_baseline(ip, baseline_id)
        baseline.refresh(ip)

    journal.note(
        request, journal.BASELINE_ATTACH, None, f"{model['name']}: {len(body.ips)} устройств"
    )
    return {"ok": True, "attached": len(body.ips)}


@router.delete("/devices/{ip}")
def detach(ip: str, request: Request) -> dict:
    store.attach_baseline(ip, None)
    store.save_drift(ip, None)
    journal.note(request, journal.BASELINE_ATTACH, ip, "эталон снят")
    return {"ok": True}


@router.get("/devices/{ip}")
def drift(ip: str) -> dict:
    return baseline.compare(ip)
