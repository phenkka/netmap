import asyncio
import ipaddress
import subprocess
from functools import lru_cache
from pathlib import Path

import paramiko

OUI_FILE = Path(__file__).resolve().parent / "oui.csv"

SSH_PORT = 22
CONNECT_TIMEOUT = 1.5
BANNER_TIMEOUT = 2.0
CONCURRENCY = 128

BANNER_VENDORS = [
    ("sr linux", "Nokia"),
    ("srlinux", "Nokia"),
    ("nokia", "Nokia"),
    ("routeros", "MikroTik"),
    ("rossh", "MikroTik"),
    ("mikrotik", "MikroTik"),
    ("cisco", "Cisco"),
    ("eltex", "Eltex"),
    ("arista", "Arista"),
    ("huawei", "Huawei"),
    ("junos", "Juniper"),
    ("juniper", "Juniper"),
]


async def scan(subnet: str) -> list[dict]:
    network = ipaddress.ip_network(subnet, strict=False)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def guarded(ip: str) -> dict | None:
        async with semaphore:
            return await _probe(ip)

    # свои адреса пропускаем, иначе продукт находит сам себя
    own = await asyncio.to_thread(local_addresses)
    hosts = [str(h) for h in network.hosts() if str(h) not in own]
    results = await asyncio.gather(*(guarded(ip) for ip in hosts))

    arp = await asyncio.to_thread(arp_table)
    found = [r for r in results if r]

    loop = asyncio.get_running_loop()
    banners = await asyncio.gather(
        *(loop.run_in_executor(None, login_banner, item["ip"]) for item in found)
    )

    for item, banner in zip(found, banners):
        item["mac"] = arp.get(item["ip"])
        item["login_banner"] = banner
    return found


async def _probe(ip: str) -> dict | None:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, SSH_PORT), CONNECT_TIMEOUT
        )
    except (OSError, asyncio.TimeoutError):
        return None

    banner = ""
    try:
        data = await asyncio.wait_for(reader.read(256), BANNER_TIMEOUT)
        banner = data.decode("utf-8", "replace").strip()
    except (OSError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    return {"ip": ip, "banner": banner}


def login_banner(ip: str) -> str:
    transport = None
    try:
        transport = paramiko.Transport((ip, SSH_PORT))
        transport.start_client(timeout=BANNER_TIMEOUT)
        try:
            transport.auth_none("netmap")
        except paramiko.SSHException:
            pass
        return (transport.get_banner() or b"").decode("utf-8", "replace").strip()
    except Exception:
        return ""
    finally:
        if transport is not None:
            transport.close()


def vendor_by_banner(*texts: str | None) -> str | None:
    haystack = " ".join(t for t in texts if t).lower()
    for needle, vendor in BANNER_VENDORS:
        if needle in haystack:
            return vendor
    return None


def vendor_by_mac(mac: str | None) -> str | None:
    if not mac or len(mac) < 8:
        return None
    try:
        first = int(mac[:2], 16)
    except ValueError:
        return None
    # второй бит первого байта — локально назначенный адрес, такие выдают
    # себе виртуалки и контейнеры, производителя по ним не узнать
    if first & 0b10:
        return None
    return _oui_table().get(mac[:8].upper().replace("-", ":"))


def local_addresses() -> set[str]:
    try:
        output = subprocess.run(
            ["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {
        line.split()[3].split("/")[0]
        for line in output.splitlines()
        if len(line.split()) > 3
    }


def arp_table() -> dict[str, str]:
    # ARP виден только в своём сегменте
    try:
        output = subprocess.run(
            ["ip", "neigh", "show"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}

    table = {}
    for line in output.splitlines():
        parts = line.split()
        if "lladdr" in parts:
            table[parts[0]] = parts[parts.index("lladdr") + 1]
    return table


@lru_cache(maxsize=1)
def _oui_table() -> dict[str, str]:
    # собрана из реестра IEEE, оставлены только сетевые производители
    table = {}
    with open(OUI_FILE, encoding="utf-8") as handle:
        for line in handle:
            prefix, _, vendor = line.strip().partition(",")
            if prefix and vendor:
                table[prefix] = vendor
    return table
