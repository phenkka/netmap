import asyncio
import json
import re
import threading
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .. import auth, drivers, inventory, journal, ssh, store

router = APIRouter(prefix="/api/devices")

# приглашение перерисовывается несколько раз подряд, на промежуточных
# кадрах режим скачет, поэтому ждём, пока поток утихнет
SETTLE = 0.3
TAIL = 400


@router.websocket("/{ip}/terminal")
async def terminal(socket: WebSocket, ip: str) -> None:
    await socket.accept()

    session = auth.by_token(socket.cookies.get(auth.COOKIE))
    if not session:
        await _notify(socket, "error", text="требуется вход")
        await socket.close()
        return
    who = session["login"]

    credentials = store.credentials(ip)
    if not credentials:
        await _notify(socket, "error", text="устройство не авторизовано")
        await socket.close()
        return

    username, password = credentials
    try:
        # paramiko блокирующий, в общем цикле он остановит весь сервер
        client, channel = await asyncio.to_thread(ssh.shell, ip, username, password)
    except ssh.SshError as exc:
        journal.record(journal.TERMINAL, who, ip, str(exc), False)
        await _notify(socket, "error", text=f"не удалось открыть сессию: {exc}")
        await socket.close()
        return

    journal.record(journal.TERMINAL, who, ip, "сессия открыта")

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

    driver = drivers.by_vendor((store.device(ip) or {}).get("vendor") or "")
    prompts = _prompt_patterns(driver)
    in_config = False
    tail = ""
    settle: asyncio.Task | None = None

    async def announce() -> None:
        nonlocal in_config
        await asyncio.sleep(SETTLE)
        mode = _mode_from_tail(tail, prompts)
        if mode is not None and mode != in_config:
            in_config = mode
            await _notify(socket, "config_mode" if mode else "config_exit")

    async def write_browser() -> None:
        # поток идёт байтами, служебные сообщения текстом, так их не спутать
        nonlocal tail, settle
        while True:
            data = await outgoing.get()
            if data is None:
                break
            await socket.send_bytes(data)
            if not prompts:
                continue

            tail = (tail + data.decode("utf-8", "replace"))[-TAIL:]
            if settle:
                settle.cancel()
            settle = asyncio.create_task(announce())

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
        if settle:
            settle.cancel()
        channel.close()
        client.close()
        # правка через терминал идёт мимо API, иначе она осталась бы незамеченной
        try:
            version = await asyncio.to_thread(inventory.collect_config, ip, "terminal")
            journal.record(
                journal.TERMINAL,
                who,
                ip,
                "сессия закрыта, конфигурация изменилась"
                if version
                else "сессия закрыта",
            )
        except (HTTPException, ssh.SshError) as exc:
            journal.record(journal.TERMINAL, who, ip, f"сессия закрыта, {exc}", False)


async def _notify(socket: WebSocket, kind: str, **fields) -> None:
    await socket.send_text(json.dumps({"type": kind, **fields}))


def _mode_from_tail(tail: str, prompts) -> bool | None:
    """по хвосту вывода говорит, в режиме конфигурации человек или нет"""
    prompt, marker = prompts
    # в хвосте лежит несколько приглашений, верно только напечатанное последним
    last = None
    for found in prompt.finditer(tail):
        last = found
    if not last:
        return None
    return bool(marker.search(last.group()))


def _prompt_patterns(driver):
    if not driver or not driver.prompt_pattern:
        return None
    return re.compile(driver.prompt_pattern), re.compile(driver.config_prompt_marker)
