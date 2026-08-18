import asyncio
import ipaddress
import time

from fastapi import HTTPException

from . import drivers, inventory, scanner, ssh, store

SCAN_EVERY = 60
LLDP_EVERY = 5
SUBNET = "subnet"


def remember(value: str) -> None:
    store.save_setting(SUBNET, value)


def subnet() -> str | None:
    return store.setting(SUBNET)


async def sweep(target: str) -> list[dict]:
    """обход подсети: ответившие обновляются, промолчавшие получают отметку"""
    found = await scanner.scan(target)
    for item in found:
        store.save_detected(
            item["ip"], item.get("mac"), item.get("banner"), item.get("login_banner")
        )
    store.bump_misses(_silent(target, {item["ip"] for item in found}))
    return found


def _silent(target: str, answered: set[str]) -> list[str]:
    """кого обход не нашёл. чужие подсети не трогаем, их никто не обходил"""
    network = ipaddress.ip_network(target, strict=False)
    missing = []
    for device in store.devices():
        if device["ip"] in answered:
            continue
        try:
            if ipaddress.ip_address(device["ip"]) in network:
                missing.append(device["ip"])
        except ValueError:
            continue
    return missing


async def run() -> None:
    cycle = 0
    pause = SCAN_EVERY
    while True:
        await asyncio.sleep(pause)
        cycle += 1
        target = subnet()
        if not target:
            continue

        started = time.monotonic()
        try:
            await sweep(target)
        except (ValueError, OSError):
            continue
        if cycle % LLDP_EVERY == 0:
            await refresh_neighbors()

        # крупную сеть обход проходит минутами, и без этой паузы машина
        # оказывается занята им почти непрерывно
        pause = max(SCAN_EVERY, time.monotonic() - started)


async def catch_up() -> None:
    """после входа администратора: доступы вернулись в память, проверяем ими сеть

    Продукт мог простоять выключенным, поэтому за один проход подтверждаем
    доступ, перечитываем соседей и снимаем конфигурации. Расхождения с последним
    сохранённым состоянием становятся новыми версиями в истории.
    """
    await _spread(_recheck, _ready())


async def refresh_neighbors() -> None:
    """о новом устройстве рассказывают уже авторизованные соседи"""
    await _spread(_reread_neighbors, _ready())


def _ready() -> list[dict]:
    """кого есть чем и куда опрашивать: пароль в памяти, устройство отвечает"""
    # в недоступное устройство SSH уходит на весь таймаут и держит пачку
    return [
        device
        for device in store.devices()
        if store.credentials(device["ip"]) and inventory.online(device)
    ]


async def _spread(job, devices: list[dict]) -> None:
    """опрос идёт пачками, размер пачки задаёт ssh.AT_ONCE"""
    limit = asyncio.Semaphore(ssh.AT_ONCE)

    async def guarded(device: dict) -> None:
        async with limit:
            await asyncio.to_thread(job, device)

    await asyncio.gather(*(guarded(device) for device in devices))


def _recheck(device: dict) -> None:
    ip = device["ip"]
    credentials = store.credentials(ip)
    if not credentials:
        return
    try:
        driver, identity = inventory.identify(ip, *credentials)
        store.save_identity(
            ip,
            identity["hostname"],
            driver.vendor,
            identity["model"],
            identity["version"],
        )
        inventory.collect_neighbors(ip, driver)
        inventory.collect_config(ip, "startup")
    except (ssh.SshError, OSError, HTTPException, inventory.NotNetworkDevice) as exc:
        store.save_error(ip, str(exc) or "устройство не отвечает")


def _reread_neighbors(device: dict) -> None:
    driver = drivers.by_vendor(device.get("vendor") or "")
    if not driver:
        return
    try:
        inventory.collect_neighbors(device["ip"], driver)
    except (ssh.SshError, OSError):
        pass
