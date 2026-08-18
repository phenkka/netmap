import asyncio
import ipaddress
import time

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


async def refresh_neighbors() -> None:
    """о новом устройстве рассказывают уже авторизованные соседи"""
    for device in store.devices():
        driver = drivers.by_vendor(device.get("vendor") or "")
        if not driver or not store.credentials(device["ip"]):
            continue
        # в недоступное устройство SSH уходит на весь таймаут и держит обход
        if not inventory.online(device):
            continue
        try:
            await asyncio.to_thread(inventory.collect_neighbors, device["ip"], driver)
        except (ssh.SshError, OSError):
            continue
