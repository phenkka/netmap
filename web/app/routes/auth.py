import ipaddress

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import auth, scanner, watch

router = APIRouter(prefix="/api")


class Credentials(BaseModel):
    login: str
    password: str


class Setup(Credentials):
    subnet: str


class Subnet(BaseModel):
    subnet: str


CHECK_LIMIT = 65534
# иначе в подсказку лезут мосты докера, машина к ним тоже подключена
SUGGEST_LIMIT = 1024


def _network(value: str):
    try:
        return ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise HTTPException(400, f"неверная подсеть: {exc}")


def _size(value: str) -> int:
    network = ipaddress.ip_network(value)
    # у /31 и /32 адреса сети и широковещательный не выделяются
    if network.prefixlen >= network.max_prefixlen - 1:
        return network.num_addresses
    return network.num_addresses - 2


@router.get("/session")
def state(request: Request) -> dict:
    found = auth.session(request)
    return {
        "login": found["login"] if found else None,
        "role": found["role"] if found else None,
    }


@router.get("/setup")
def offer() -> dict:
    return {
        "configured": auth.configured(),
        "least": auth.MIN_PASSWORD,
        "networks": [n for n in scanner.local_networks() if _size(n) <= SUGGEST_LIMIT],
    }


@router.post("/setup/check")
async def check(body: Subnet) -> dict:
    if auth.configured():
        raise HTTPException(400, "продукт уже настроен")

    network = _network(body.subnet)
    hosts = _size(str(network))
    if not hosts:
        raise HTTPException(400, "в этой сети нет адресов для обхода")

    mine = scanner.local_networks()
    if str(network) not in mine:
        mine = [n for n in mine if _size(n) <= SUGGEST_LIMIT]
        # за маршрутизатором не виден ARP, значит и вендор по MAC не определится
        own = scanner.local_addresses()
        outside = next((str(h) for h in network.hosts() if str(h) not in own), None)
        if not outside or not scanner.route_to(outside):
            raise HTTPException(400, "до этой сети нет ни интерфейса, ни маршрута")
        return {"attached": False, "checked": False, "networks": mine, "hosts": hosts}

    if hosts > CHECK_LIMIT:
        return {"attached": True, "checked": False, "hosts": hosts}

    return {
        "attached": True,
        "checked": True,
        "hosts": hosts,
        "found": await scanner.any_open(body.subnet),
    }


@router.post("/setup")
def setup(body: Setup, response: Response) -> dict:
    if auth.configured():
        raise HTTPException(400, "продукт уже настроен")
    if not body.login.strip():
        raise HTTPException(400, "логин не заполнен")
    if len(body.password) < auth.MIN_PASSWORD:
        raise HTTPException(400, f"пароль короче {auth.MIN_PASSWORD} знаков")

    _network(body.subnet)

    auth.create_user(body.login.strip(), body.password)
    watch.remember(body.subnet.strip())
    return _enter(auth.check(body.login.strip(), body.password), response)


@router.post("/login")
def login(body: Credentials, response: Response) -> dict:
    user = auth.check(body.login.strip(), body.password)
    if not user:
        raise HTTPException(401, "неверный логин или пароль")
    return _enter(user, response)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    auth.close_session(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


def _enter(user: dict, response: Response) -> dict:
    response.set_cookie(
        auth.COOKIE,
        auth.open_session(user),
        httponly=True,
        samesite="lax",
        max_age=auth.IDLE_TIMEOUT,
    )
    return {"login": user["login"], "role": user["role"]}
