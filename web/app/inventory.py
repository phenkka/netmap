"""что известно об устройстве и как это узнать, поверх store и drivers"""

from fastapi import HTTPException

from . import drivers, scanner, ssh, store


class NotNetworkDevice(Exception):
    pass


def decorate(device: dict) -> dict:
    device = dict(device)
    device["vendor_guess"] = scanner.vendor_by_mac(
        device.get("mac")
    ) or scanner.vendor_by_banner(device.get("banner"), device.get("login_banner"))
    device["authorized"] = device["status"] == "authorized"
    device["neighbors"] = store.neighbors_of(device["ip"])
    return device


def identify(ip: str, username: str, password: str):
    for driver in drivers.ALL:
        output = ssh.run(ip, username, password, driver.version_command)
        if driver.matches(output):
            return driver, driver.parse_version(output)
    raise NotNetworkDevice


def capabilities() -> dict:
    return {
        link["remote_name"]: link["capabilities"] or ""
        for link in store.neighbors()
        if link["remote_name"]
    }


def node_type(device: dict, known: dict) -> str:
    # модель точнее, чем поле возможностей LLDP, но известна только после входа
    if device.get("model"):
        driver = drivers.by_vendor(device.get("vendor") or "")
        if driver:
            return driver.device_type(device["model"])
    return device_type(known.get(device.get("hostname") or "", ""))


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


def collect_neighbors(ip: str, driver) -> None:
    credentials = store.credentials(ip)
    if not credentials:
        return
    username, password = credentials
    output = ssh.run(ip, username, password, driver.neighbors_command)
    store.save_neighbors(ip, driver.parse_neighbors(output))
