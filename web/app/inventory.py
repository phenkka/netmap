"""что известно об устройстве и как это узнать, поверх store и drivers"""

from fastapi import HTTPException

from . import drivers, scanner, ssh, store


class NotNetworkDevice(Exception):
    pass


# одиночный потерянный пакет не должен красить карту, ждём три обхода подряд
OFFLINE_AFTER = 3


def decorate(device: dict) -> dict:
    device = dict(device)
    device["vendor_guess"] = scanner.vendor_by_mac(
        device.get("mac")
    ) or scanner.vendor_by_banner(device.get("banner"), device.get("login_banner"))
    device["authorized"] = device["status"] == "authorized"
    device["online"] = device.pop("misses", 0) < OFFLINE_AFTER
    # состояние для интерфейса: недоступность важнее того, есть ли доступ
    device["state"] = device["status"] if device["online"] else "offline"
    device["neighbors"] = store.neighbors_of(device["ip"])
    return device


def online(device: dict) -> bool:
    return (device.get("misses") or 0) < OFFLINE_AFTER


def identify(ip: str, username: str, password: str):
    for driver in drivers.ALL:
        output = ssh.run(ip, username, password, driver.version_command)
        if driver.matches(output):
            return driver, driver.parse_version(output)
    raise NotNetworkDevice


def capabilities() -> dict:
    known: dict[str, str] = {}
    for link in store.neighbors():
        for key in (link["remote_name"], link.get("remote_addr")):
            if key:
                known[key] = link["capabilities"] or ""
    return known


def node_type(device: dict) -> str:
    # тип берётся из модели, а она известна только после входа. до него
    # показываем безымянную коробку, а не догадку по возможностям LLDP
    if device.get("model"):
        driver = drivers.by_vendor(device.get("vendor") or "")
        if driver:
            return driver.device_type(device["model"])
    return "device"


def device_type(capabilities_field: str) -> str:
    # коммутатор с маршрутизацией объявляет и BRIDGE, и ROUTER
    if "BRIDGE" in capabilities_field:
        return "switch"
    if "ROUTER" in capabilities_field:
        return "router"
    if "WLAN_ACCESS_POINT" in capabilities_field:
        return "wifi"
    return "unknown"


def require_credentials(ip: str) -> tuple[str, str]:
    credentials = store.credentials(ip)
    if not credentials:
        raise HTTPException(400, "устройство не авторизовано")
    return credentials


def driver_for(ip: str):
    device = store.device(ip)
    if not device:
        raise HTTPException(404, "устройство не найдено")
    driver = drivers.by_vendor(device.get("vendor") or "")
    if not driver:
        raise HTTPException(400, "производитель неизвестен, сначала войдите на устройство")
    return driver


def collect_config(ip: str, source: str) -> dict | None:
    driver = driver_for(ip)
    if not driver.config_command:
        raise HTTPException(400, f"{driver.vendor} не умеет отдавать конфигурацию")

    username, password = require_credentials(ip)
    output = ssh.run(ip, username, password, driver.config_command)
    return store.save_config(ip, driver.normalize_config(output), source)


def lldp_auto() -> bool:
    return store.setting("lldp_auto") != "no"


def ensure_lldp(ip: str, driver, username: str, password: str) -> str | None:
    """дописывает настройку LLDP и отдаёт, чем дело кончилось"""
    if not driver.lldp_state_command or not driver.lldp_enable_commands:
        return None

    if driver.lldp_ready(ssh.run(ip, username, password, driver.lldp_state_command)):
        return "on"

    # черновик общий, наш commit применил бы чужую незаконченную правку
    if driver.pending_diff_commands:
        pending = driver.clean_pending_diff(
            ssh.run_lines(ip, username, password, driver.pending_diff_commands)
        )
        if pending:
            return "busy"

    ssh.run_lines(ip, username, password, driver.lldp_enable_commands)
    state = ssh.run(ip, username, password, driver.lldp_state_command)
    return "enabled" if driver.lldp_ready(state) else "failed"


def collect_neighbors(ip: str, driver) -> None:
    credentials = store.credentials(ip)
    if not credentials:
        return
    username, password = credentials
    output = ssh.run(ip, username, password, driver.neighbors_command)
    store.save_neighbors(ip, driver.parse_neighbors(output))
