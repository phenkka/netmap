import asyncio

from . import scanner, store

SCAN_EVERY = 60
SUBNET = "subnet"


def remember(value: str) -> None:
    store.save_setting(SUBNET, value)


def subnet() -> str | None:
    return store.setting(SUBNET)


async def run() -> None:
    while True:
        await asyncio.sleep(SCAN_EVERY)
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
