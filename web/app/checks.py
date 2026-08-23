import re

from . import drivers

TELNET = "telnet_off"
DEFAULTS = "no_default_users"
SNMP = "snmp_closed"
MGMT_ACL = "mgmt_acl"
LOGGING = "logging_on"
DOT1X = "dot1x"

ALL = [
    {
        "code": TELNET,
        "title": "Telnet отключён",
        "why": "Telnet передаёт пароль открытым текстом, управление ведётся по SSH.",
    },
    {
        "code": DEFAULTS,
        "title": "Нет учётных записей с паролями по умолчанию",
        "why": "Пароль производителя из документации известен всем, кто её читал.",
    },
    {
        "code": SNMP,
        "title": "SNMP с community public недоступен",
        "why": "Community public отдаёт карту сети и настройки любому, кто спросит.",
    },
    {
        "code": MGMT_ACL,
        "title": "Доступ к управлению ограничен списком контроля доступа",
        "why": "Без списка управляющий интерфейс отвечает всей сети, а не сети управления.",
    },
    {
        "code": LOGGING,
        "title": "Журналирование ведётся",
        "why": "Без журнала на устройстве не установить, кто и когда менял настройки.",
    },
    {
        "code": DOT1X,
        "title": "Настроена аутентификация на портах по 802.1X",
        "why": "Без неё в свободный порт включается любое устройство.",
    },
]

BY_CODE = {item["code"]: item for item in ALL}

# пароли из документации производителей. проверка сравнивает с ними то, чем
# продукт фактически входит на устройство, по конфигурации этого не видно
VENDOR_DEFAULTS = {
    "Nokia": [("admin", "NokiaSrl1!"), ("admin", "admin")],
    "Cisco": [("cisco", "cisco"), ("admin", "admin"), ("admin", "Cisco123")],
    "Arista": [("admin", ""), ("admin", "admin"), ("arista", "arista")],
    "MikroTik": [("admin", ""), ("admin", "admin")],
}


def run(config: str, vendor: str, login: tuple[str, str] | None) -> list[dict]:
    driver = drivers.by_vendor(vendor)
    rules = driver.check_rules if driver else {}
    results = []

    for item in ALL:
        code = item["code"]
        if code == DEFAULTS:
            results.append(_default_password(vendor, login))
            continue

        rule = rules.get(code)
        if not rule:
            results.append(
                {
                    "code": code,
                    "state": "skip",
                    "detail": "на этом оборудовании продукт такую настройку не разбирает",
                }
            )
            continue
        results.append(_by_rule(code, rule, config))

    return results


def _by_rule(code: str, rule: dict, config: str) -> dict:
    for pattern in rule.get("forbid", []):
        found = _find(pattern, config)
        if found:
            return {"code": code, "state": "fail", "detail": f"в конфигурации: {found}"}

    wanted = rule.get("require", [])
    if wanted and not any(_find(pattern, config) for pattern in wanted):
        return {"code": code, "state": "fail", "detail": "настройка не найдена"}

    return {"code": code, "state": "pass", "detail": None}


def _find(pattern: str, config: str) -> str:
    for line in config.splitlines():
        if re.search(pattern, line, re.IGNORECASE):
            return line.strip()[:200]
    return ""


def _default_password(vendor: str, login: tuple[str, str] | None) -> dict:
    if not login:
        return {
            "code": DEFAULTS,
            "state": "skip",
            "detail": "устройство не авторизовано, сравнивать нечего",
        }

    known = VENDOR_DEFAULTS.get(vendor, [])
    if not known:
        return {
            "code": DEFAULTS,
            "state": "skip",
            "detail": "пароли по умолчанию для этого производителя продукту неизвестны",
        }

    username, password = login
    if (username, password) in known:
        return {
            "code": DEFAULTS,
            "state": "fail",
            "detail": f"продукт входит под учётной записью {username} с паролем из документации",
        }
    return {"code": DEFAULTS, "state": "pass", "detail": None}


def dress(rows: list[dict]) -> list[dict]:
    return [dict(row, **BY_CODE.get(row["code"], {})) for row in rows]
