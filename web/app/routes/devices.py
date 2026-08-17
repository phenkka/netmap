from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import inventory, scanner, ssh, store, watch

router = APIRouter(prefix="/api")


class ScanRequest(BaseModel):
    subnet: str


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/scan")
async def scan(request: ScanRequest) -> dict:
    try:
        found = await scanner.scan(request.subnet)
    except ValueError as exc:
        raise HTTPException(400, f"неверная подсеть: {exc}")

    watch.remember(request.subnet)
    for item in found:
        store.save_detected(
            item["ip"], item.get("mac"), item.get("banner"), item.get("login_banner")
        )
    return {"found": len(found), "devices": store.devices()}


@router.get("/settings")
def settings() -> dict:
    return {"subnet": watch.subnet() or ""}


@router.get("/devices")
def devices() -> dict:
    result = []
    for row in store.devices():
        device = inventory.decorate(row)
        device["type"] = inventory.node_type(device)
        result.append(device)
    return {"devices": result}


@router.post("/devices/{ip}/auth")
def authorize(ip: str, request: AuthRequest) -> dict:
    if not store.device(ip):
        raise HTTPException(404, "устройство не найдено")

    try:
        driver, identity = inventory.identify(ip, request.username, request.password)
    except inventory.NotNetworkDevice:
        message = "вход выполнен, но это не сетевое устройство"
        store.save_status(ip, "not_network", message)
        raise HTTPException(400, message)
    except ssh.SshError as exc:
        store.save_error(ip, str(exc))
        raise HTTPException(400, str(exc))

    store.set_credentials(ip, request.username, request.password)
    store.save_identity(
        ip, identity["hostname"], driver.vendor, identity["model"], identity["version"]
    )
    _settle_lldp(ip, driver, request.username, request.password)
    inventory.collect_neighbors(ip, driver)
    return inventory.decorate(store.device(ip))


def _settle_lldp(ip: str, driver, username: str, password: str) -> None:
    if not inventory.lldp_auto():
        return
    try:
        store.save_lldp(ip, inventory.ensure_lldp(ip, driver, username, password))
    except ssh.SshError:
        store.save_lldp(ip, "failed")


@router.delete("/devices/{ip}/auth")
def forget(ip: str) -> dict:
    store.forget_credentials(ip)
    store.save_neighbors(ip, [])
    store.save_error(ip, "учётные данные удалены")
    return {"ok": True}


@router.post("/devices/{ip}/refresh")
def refresh(ip: str) -> dict:
    username, password = inventory.require_credentials(ip)
    driver, identity = inventory.identify(ip, username, password)
    store.save_identity(
        ip, identity["hostname"], driver.vendor, identity["model"], identity["version"]
    )
    _settle_lldp(ip, driver, username, password)
    inventory.collect_neighbors(ip, driver)
    return inventory.decorate(store.device(ip))
