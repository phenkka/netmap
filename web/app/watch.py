import asyncio

from . import drivers, inventory, scanner, ssh, store

SCAN_EVERY = 60
LLDP_EVERY = 5
SUBNET = "subnet"


def remember(value: str) -> None:
    store.save_setting(SUBNET, value)


def subnet() -> str | None:
    return store.setting(SUBNET)


async def run() -> None:
    cycle = 0
    while True:
        await asyncio.sleep(SCAN_EVERY)
        cycle += 1
        target = subnet()
        if not target:
            continue
        try:
            for item in await scanner.scan(target):
                store.save_detected(
                    item["ip"],
                    item.get("mac"),
                    item.get("banner"),
                    item.get("login_banner"),
                )
        except (ValueError, OSError):
            continue
        if cycle % LLDP_EVERY == 0:
            await refresh_neighbors()


async def refresh_neighbors() -> None:
    """о новом устройстве рассказывают уже авторизованные соседи"""
    for device in store.devices():
        driver = drivers.by_vendor(device.get("vendor") or "")
        if not driver or not store.credentials(device["ip"]):
            continue
        try:
            await asyncio.to_thread(inventory.collect_neighbors, device["ip"], driver)
        except (ssh.SshError, OSError):
            continue
