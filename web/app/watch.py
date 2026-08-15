import asyncio

from . import scanner, store

SCAN_EVERY = 60

# подсеть задаётся первым сканированием из браузера, до него обходить нечего
_subnet: str | None = None


def remember(subnet: str) -> None:
    global _subnet
    _subnet = subnet


async def run() -> None:
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
