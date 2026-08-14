import asyncio
import codecs
import json
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import drivers, scanner, ssh, store

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="netmap")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ON_MAP = {"detected", "authorized", "failed"}

SCAN_EVERY = 60
_subnet: str | None = None


class NotNetworkDevice(Exception):
    pass


class ScanRequest(BaseModel):
    subnet: str


class AuthRequest(BaseModel):
    username: str
    password: str


@app.on_event("startup")
async def startup() -> None:
    store.init()
    asyncio.create_task(_watch_network())


async def _watch_network() -> None:
    # обход в фоне, чтобы браузер его не ждал
    while True:
        await asyncio.sleep(SCAN_EVERY)
        if not _subnet:
            continue
        try:
            for item in await scanner.scan(_subnet):
                store.save_detected(
                    item["ip"],
                    item.get("mac"),
                    item.get("banner"),
                    item.get("login_banner"),
                )
        except (ValueError, OSError):
            continue


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/scan")
async def scan(request: ScanRequest) -> dict:
    global _subnet
    try:
        found = await scanner.scan(request.subnet)
    except ValueError as exc:
        raise HTTPException(400, f"неверная подсеть: {exc}")

    _subnet = request.subnet
    for item in found:
        store.save_detected(
            item["ip"], item.get("mac"), item.get("banner"), item.get("login_banner")
        )
    return {"found": len(found), "devices": store.devices()}


@app.get("/api/devices")
def devices() -> dict:
    capabilities = _capabilities()
    result = []
    for row in store.devices():
        device = _decorate(row)
        device["type"] = _node_type(device, capabilities)
        result.append(device)
    return {"devices": result}


@app.post("/api/devices/{ip}/auth")
def authorize(ip: str, request: AuthRequest) -> dict:
    if not store.device(ip):
        raise HTTPException(404, "устройство не найдено")

    try:
        driver, identity = _identify(ip, request.username, request.password)
    except NotNetworkDevice:
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
    _collect_neighbors(ip, driver)
    return _decorate(store.device(ip))


@app.delete("/api/devices/{ip}/auth")
def forget(ip: str) -> dict:
    store.forget_credentials(ip)
    store.save_neighbors(ip, [])
    store.save_error(ip, "учётные данные удалены")
    return {"ok": True}


@app.post("/api/devices/{ip}/refresh")
def refresh(ip: str) -> dict:
    credentials = store.credentials(ip)
    if not credentials:
        raise HTTPException(400, "устройство не авторизовано")

    username, password = credentials
    driver, identity = _identify(ip, username, password)
    store.save_identity(
        ip, identity["hostname"], driver.vendor, identity["model"], identity["version"]
    )
    _collect_neighbors(ip, driver)
    return _decorate(store.device(ip))


@app.websocket("/api/devices/{ip}/terminal")
async def terminal(socket: WebSocket, ip: str) -> None:
    await socket.accept()

    credentials = store.credentials(ip)
    if not credentials:
        await socket.send_text("устройство не авторизовано\r\n")
        await socket.close()
        return

    username, password = credentials
    try:
        # paramiko блокирующий, в общем цикле он остановит весь сервер
        client, channel = await asyncio.to_thread(ssh.shell, ip, username, password)
    except ssh.SshError as exc:
        await socket.send_text(f"не удалось открыть сессию: {exc}\r\n")
        await socket.close()
        return

    loop = asyncio.get_running_loop()
    outgoing: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def read_device() -> None:
        while not stop.is_set():
            try:
                if channel.recv_ready():
                    data = channel.recv(65536)
                    if not data:
                        break
                    loop.call_soon_threadsafe(outgoing.put_nowait, data)
                elif channel.closed or channel.exit_status_ready():
                    break
                else:
                    time.sleep(0.02)
            except OSError:
                break
        loop.call_soon_threadsafe(outgoing.put_nowait, None)

    threading.Thread(target=read_device, daemon=True).start()

    async def write_browser() -> None:
        # кусок может оборваться посреди многобайтового символа
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            data = await outgoing.get()
            if data is None:
                break
            await socket.send_text(decoder.decode(data))

    pump = asyncio.create_task(write_browser())
    try:
        while True:
            message = json.loads(await socket.receive_text())
            if message.get("type") == "input":
                channel.send(message["data"])
            elif message.get("type") == "size":
                channel.resize_pty(
                    width=int(message["cols"]), height=int(message["rows"])
                )
    except (WebSocketDisconnect, json.JSONDecodeError, KeyError, ValueError, OSError):
        pass
    finally:
        stop.set()
        pump.cancel()
        channel.close()
        client.close()


@app.get("/api/graph")
def graph() -> dict:
    all_devices = [_decorate(d) for d in store.devices()]
    by_hostname = {d["hostname"]: d for d in all_devices if d.get("hostname")}
    capabilities = _capabilities()

    # серверы и рабочие станции на карту не идут, они остаются в списке
    nodes = [
        {
            "id": d["ip"],
            "label": d.get("hostname") or d["ip"],
            "status": d["status"],
            "vendor": d.get("vendor") or d.get("vendor_guess") or "",
            "type": _node_type(d, capabilities),
        }
        for d in all_devices
        if d["status"] in ON_MAP
    ]

    # LLDP отдаёт имя соседа, но не адрес. пока есть неопознанные адреса,
    # сосед может оказаться любым из них, и рисовать его отдельно нельзя
    unresolved = any(d["status"] in ("detected", "failed") for d in all_devices)

    known_ids = {n["id"] for n in nodes}
    edges: dict[tuple, dict] = {}

    for link in store.neighbors():
        source = link["ip"]
        peer = by_hostname.get(link["remote_name"])

        if peer:
            target = peer["ip"]
        elif unresolved:
            continue
        else:
            # все адреса опознаны, а сосед не нашёлся, значит он вне диапазона
            target = f"lldp:{link['remote_name']}"
            if target not in known_ids:
                known_ids.add(target)
                nodes.append(
                    {
                        "id": target,
                        "label": link["remote_name"],
                        "status": "unknown",
                        "vendor": "",
                        "type": _device_type(capabilities.get(link["remote_name"], "")),
                    }
                )

        # связь сообщают оба соседа, концы упорядочиваем одинаково,
        # иначе она меняет направление и карта считает её новой
        key = tuple(sorted([(source, link["local_port"]), (target, link["remote_port"])]))
        edges.setdefault(
            key,
            {
                "id": f"{key[0][0]}:{key[0][1]}-{key[1][0]}:{key[1][1]}",
                "source": key[0][0],
                "source_port": key[0][1],
                "target": key[1][0],
                "target_port": key[1][1],
            },
        )

    return {"nodes": nodes, "edges": list(edges.values())}


def _capabilities() -> dict:
    return {
        link["remote_name"]: link["capabilities"] or ""
        for link in store.neighbors()
        if link["remote_name"]
    }


def _node_type(device: dict, capabilities: dict) -> str:
    # модель точнее, чем поле возможностей LLDP, но известна только после входа
    if device.get("model"):
        driver = drivers.by_vendor(device.get("vendor") or "")
        if driver:
            return driver.device_type(device["model"])
    return _device_type(capabilities.get(device.get("hostname") or "", ""))


def _device_type(capabilities: str) -> str:
    # коммутатор с маршрутизацией объявляет и BRIDGE, и ROUTER
    if "BRIDGE" in capabilities:
        return "switch"
    if "ROUTER" in capabilities:
        return "router"
    if "WLAN_ACCESS_POINT" in capabilities:
        return "wifi"
    return "unknown"


def _identify(ip: str, username: str, password: str):
    for driver in drivers.ALL:
        output = ssh.run(ip, username, password, driver.version_command)
        if driver.matches(output):
            return driver, driver.parse_version(output)
    raise NotNetworkDevice


def _collect_neighbors(ip: str, driver) -> None:
    credentials = store.credentials(ip)
    if not credentials:
        return
    username, password = credentials
    output = ssh.run(ip, username, password, driver.neighbors_command)
    store.save_neighbors(ip, driver.parse_neighbors(output))


def _decorate(device: dict) -> dict:
    device = dict(device)
    device["vendor_guess"] = scanner.vendor_by_mac(
        device.get("mac")
    ) or scanner.vendor_by_banner(device.get("banner"), device.get("login_banner"))
    device["authorized"] = device["status"] == "authorized"
    device["neighbors"] = store.neighbors_of(device["ip"])
    return device
