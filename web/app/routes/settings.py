"""окно настроек: сеть, поведение продукта, доступы, учётная запись"""

import ipaddress

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from .. import auth, inventory, journal, watch

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
def set_subnet(body: Subnet, later: BackgroundTasks, request: Request) -> dict:
    value = body.subnet.strip()
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise HTTPException(400, f"неверная подсеть: {exc}")

    watch.remember(value)
    journal.note(request, journal.SUBNET, None, value)
    # не ждём общего обхода, он раз в минуту
    later.add_task(watch.sweep, value)
    return {"subnet": value}


@router.post("/lldp")
def set_lldp(body: Lldp, request: Request) -> dict:
    inventory.set_lldp_auto(body.auto)
    journal.note(
        request, journal.LLDP_AUTO, None, "включена" if body.auto else "выключена"
    )
    return {"auto": body.auto}


@router.post("/credentials")
def set_keeping(body: Keeping, request: Request) -> dict:
    login = (auth.session(request) or {})["login"]

    if body.keep:
        recovery = auth.start_keeping(login, body.password)
        if recovery is None:
            journal.record(journal.KEEPING, login, None, "неверный пароль", False)
            raise HTTPException(400, "неверный пароль")
        journal.record(journal.KEEPING, login, None, "включён")
        return {"keep": True, "recovery": recovery}

    if not auth.stop_keeping(login, body.password):
        journal.record(journal.KEEPING, login, None, "неверный пароль", False)
        raise HTTPException(400, "неверный пароль")
    journal.record(journal.KEEPING, login, None, "выключен, доступы стёрты с диска")
    return {"keep": False, "recovery": None}


@router.post("/password")
def set_password(body: Password, request: Request) -> dict:
    login = (auth.session(request) or {})["login"]
    if len(body.following) < auth.MIN_PASSWORD:
        raise HTTPException(400, f"пароль короче {auth.MIN_PASSWORD} знаков")
    if not auth.change_password(login, body.current, body.following):
        journal.record(journal.PASSWORD, login, None, "текущий пароль не подошёл", False)
        raise HTTPException(400, "текущий пароль не подошёл")
    journal.record(journal.PASSWORD, login, None, "пароль изменён")
    return {"ok": True}
