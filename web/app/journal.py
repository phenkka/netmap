from fastapi import Request

from . import auth, store

LOGIN = "login"
LOGOUT = "logout"
SETUP = "setup"
PASSWORD = "password"
KEEPING = "keeping"
RECOVER = "recover"
SUBNET = "subnet"
LLDP_AUTO = "lldp_auto"
LLDP_SET = "lldp_set"
DEVICE_AUTH = "device_auth"
DEVICE_FORGET = "device_forget"
CONFIG_TAKEN = "config_taken"
ROLLBACK = "rollback"
APPLY = "apply"
BASELINE_SAVE = "baseline_save"
BASELINE_ATTACH = "baseline_attach"
BASELINE_DROP = "baseline_drop"
CHECKS = "checks"
EXPORT = "export"
IMPORT = "import"
TERMINAL = "terminal"

WORDS = {
    LOGIN: "вход в продукт",
    LOGOUT: "выход из продукта",
    SETUP: "создана учётная запись",
    PASSWORD: "смена пароля",
    KEEPING: "режим хранения доступов",
    RECOVER: "восстановление по ключу",
    SUBNET: "изменена сеть управления",
    LLDP_AUTO: "автонастройка LLDP",
    LLDP_SET: "LLDP настроен на устройстве",
    DEVICE_AUTH: "вход на устройство",
    DEVICE_FORGET: "удалены учётные данные устройства",
    CONFIG_TAKEN: "снята конфигурация",
    ROLLBACK: "откат конфигурации",
    APPLY: "применены команды",
    BASELINE_SAVE: "сохранён эталон",
    BASELINE_ATTACH: "назначен эталон",
    BASELINE_DROP: "удалён эталон",
    CHECKS: "выполнены проверки",
    EXPORT: "выгрузка копий",
    IMPORT: "восстановление из копии",
    TERMINAL: "сессия терминала",
}


def who(request: Request | None) -> str | None:
    if request is None:
        return None
    return (auth.session(request) or {}).get("login")


def record(
    action: str,
    login: str | None = None,
    ip: str | None = None,
    detail: str | None = None,
    ok: bool = True,
) -> dict:
    return dress(store.add_entry(login, action, ip, detail, ok))


def note(
    request: Request | None,
    action: str,
    ip: str | None = None,
    detail: str | None = None,
    ok: bool = True,
) -> dict:
    return record(action, who(request), ip, detail, ok)


def recent(after: int | None = None) -> list[dict]:
    return [dress(row) for row in store.entries(after)]


def dress(row: dict) -> dict:
    return dict(row, word=WORDS.get(row["action"], row["action"]))
