from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import apply, journal, store

router = APIRouter(prefix="/api/apply")


class Batch(BaseModel):
    ips: list[str]
    commands: str


@router.post("")
async def group(body: Batch, request: Request) -> dict:
    commands = [line for line in body.commands.splitlines() if line.strip()]
    if not commands:
        raise HTTPException(400, "нечего применять")
    if not body.ips:
        raise HTTPException(400, "не выбрано ни одного устройства")

    results = await apply.group(body.ips, commands, journal.who(request))
    return {"results": results, "applied": sum(1 for r in results if r["ok"])}


@router.get("/targets")
def targets() -> dict:
    ready = []
    for device in store.devices():
        if device["status"] != "authorized" or not store.credentials(device["ip"]):
            continue
        ready.append(
            {
                "ip": device["ip"],
                "hostname": device["hostname"] or device["ip"],
                "vendor": device["vendor"] or "",
                "model": device["model"] or "",
            }
        )
    return {"targets": ready}
