"""окно настроек: сеть, поведение продукта, доступы, учётная запись"""

import ipaddress

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from .. import auth, inventory, watch

router = APIRouter(prefix="/api/settings")


class Subnet(BaseModel):
    subnet: str


class Lldp(BaseModel):
    auto: bool


class Keeping(BaseModel):
    keep: bool
    password: str


class Password(BaseModel):
    current: str
    following: str


@router.get("")
def all_settings(request: Request) -> dict:
    session = auth.session(request) or {}
    return {
        "login": session.get("login"),
        "role": session.get("role"),
        "subnet": watch.subnet() or "",
        "lldp_auto": inventory.lldp_auto(),
        "keep_credentials": auth.keeping(),
        "recovery_offered": auth.recovery_offered(),
    }


@router.post("/subnet")
def set_subnet(body: Subnet, later: BackgroundTasks) -> dict:
    value = body.subnet.strip()
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise HTTPException(400, f"неверная подсеть: {exc}")

    watch.remember(value)
    # не ждём общего обхода, он раз в минуту
    later.add_task(watch.sweep, value)
    return {"subnet": value}


@router.post("/lldp")
def set_lldp(body: Lldp) -> dict:
    inventory.set_lldp_auto(body.auto)
    return {"auto": body.auto}


@router.post("/credentials")
def set_keeping(body: Keeping, request: Request) -> dict:
    login = (auth.session(request) or {})["login"]

    if body.keep:
        recovery = auth.start_keeping(login, body.password)
        if recovery is None:
            raise HTTPException(400, "неверный пароль")
        return {"keep": True, "recovery": recovery}

    if not auth.stop_keeping(login, body.password):
        raise HTTPException(400, "неверный пароль")
    return {"keep": False, "recovery": None}


@router.post("/password")
def set_password(body: Password, request: Request) -> dict:
    login = (auth.session(request) or {})["login"]
    if len(body.following) < auth.MIN_PASSWORD:
        raise HTTPException(400, f"пароль короче {auth.MIN_PASSWORD} знаков")
    if not auth.change_password(login, body.current, body.following):
        raise HTTPException(400, "текущий пароль не подошёл")
    return {"ok": True}
