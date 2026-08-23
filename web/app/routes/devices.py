from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import checks, inventory, journal, ssh, store, watch

router = APIRouter(prefix="/api")


class ScanRequest(BaseModel):
    subnet: str


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/scan")
async def scan(request: ScanRequest) -> dict:
    try:
        found = await watch.sweep(request.subnet)
    except ValueError as exc:
        raise HTTPException(400, f"неверная подсеть: {exc}")

    watch.remember(request.subnet)
    return {
        "found": len(found),
        "devices": [inventory.decorate(d) for d in store.devices()],
    }


@router.get("/devices")
def devices() -> dict:
    failed = store.failed_checks()
    result = []
    for row in store.devices():
        device = inventory.decorate(row)
        device["type"] = inventory.node_type(device)
        device["failed_checks"] = failed.get(device["ip"], 0)
        result.append(device)
    return {"devices": result}


@router.post("/devices/{ip}/auth")
def authorize(ip: str, body: AuthRequest, request: Request) -> dict:
    if not store.device(ip):
        raise HTTPException(404, "устройство не найдено")

    who = journal.who(request)
    try:
        driver, identity = inventory.identify(ip, body.username, body.password)
    except inventory.NotNetworkDevice:
        message = "вход выполнен, но это не сетевое устройство"
        store.save_status(ip, "not_network", message)
        journal.record(journal.DEVICE_AUTH, who, ip, message, False)
        raise HTTPException(400, message)
    except ssh.SshError as exc:
        store.save_error(ip, str(exc))
        journal.record(journal.DEVICE_AUTH, who, ip, str(exc), False)
        raise HTTPException(400, str(exc))

    store.set_credentials(ip, body.username, body.password)
    store.save_identity(
        ip, identity["hostname"], driver.vendor, identity["model"], identity["version"]
    )
    journal.record(
        journal.DEVICE_AUTH, who, ip, f"{driver.vendor} {identity['model']}", True
    )
    _settle_lldp(ip, driver, body.username, body.password, who)
    inventory.collect_neighbors(ip, driver)
    _first_snapshot(ip, who)
    return inventory.decorate(store.device(ip))


def _first_snapshot(ip: str, who: str | None) -> None:
    try:
        version = inventory.collect_config(ip, "auth")
    except (HTTPException, ssh.SshError, OSError) as exc:
        journal.record(journal.CONFIG_TAKEN, who, ip, str(exc), False)
        return
    journal.record(
        journal.CONFIG_TAKEN,
        who,
        ip,
        "первый снимок" if version else "конфигурация не изменилась",
        True,
    )


def _settle_lldp(ip: str, driver, username: str, password: str, who: str | None) -> None:
    if not inventory.lldp_auto():
        return
    try:
        state = inventory.ensure_lldp(ip, driver, username, password)
    except ssh.SshError as exc:
        store.save_lldp(ip, "failed")
        journal.record(journal.LLDP_SET, who, ip, str(exc), False)
        return

    store.save_lldp(ip, state)
    # правку в чужую конфигурацию продукт вносит сам, это должно быть видно
    if state in ("enabled", "failed", "busy"):
        journal.record(journal.LLDP_SET, who, ip, state, state == "enabled")


@router.delete("/devices/{ip}/auth")
def forget(ip: str, request: Request) -> dict:
    store.forget_credentials(ip)
    store.save_neighbors(ip, [])
    store.save_error(ip, "учётные данные удалены")
    journal.note(request, journal.DEVICE_FORGET, ip)
    return {"ok": True}


@router.post("/devices/{ip}/refresh")
def refresh(ip: str, request: Request) -> dict:
    username, password = inventory.require_credentials(ip)
    driver, identity = inventory.identify(ip, username, password)
    store.save_identity(
        ip, identity["hostname"], driver.vendor, identity["model"], identity["version"]
    )
    _settle_lldp(ip, driver, username, password, journal.who(request))
    inventory.collect_neighbors(ip, driver)
    return inventory.decorate(store.device(ip))


@router.get("/devices/{ip}/checks")
def device_checks(ip: str) -> dict:
    rows = store.checks_of(ip)
    if not rows:
        rows = inventory.run_checks(ip)
        rows = store.checks_of(ip)
    return {"checks": checks.dress(rows)}


@router.post("/devices/{ip}/checks")
def recheck(ip: str, request: Request) -> dict:
    inventory.run_checks(ip)
    rows = store.checks_of(ip)
    failed = sum(1 for row in rows if row["state"] == "fail")
    journal.note(request, journal.CHECKS, ip, f"не пройдено {failed} из {len(rows)}")
    return {"checks": checks.dress(rows)}
