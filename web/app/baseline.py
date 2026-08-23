import difflib

from . import drivers, store

MATCH = "match"
DIFFERS = "differs"


def from_version(name: str, version_id: int) -> dict | None:
    version = store.config(version_id)
    if not version:
        return None
    device = store.device(version["ip"]) or {}
    return store.save_baseline(name, device.get("vendor") or "", version["text"])


def compare(ip: str) -> dict:
    model = store.baseline_of(ip)
    if not model:
        return {"baseline": None, "state": None, "diff": ""}

    latest = store.last_config(ip)
    if not latest:
        return {"baseline": _short(model), "state": None, "diff": ""}

    driver = drivers.by_vendor(model["vendor"])
    trim = driver.comparable if driver else (lambda text: text)

    lines = list(
        difflib.unified_diff(
            trim(model["text"]).splitlines(),
            trim(latest["text"]).splitlines(),
            f"эталон {model['name']}",
            f"снято {latest['at']}",
            lineterm="",
        )
    )
    return {
        "baseline": _short(model),
        "state": DIFFERS if lines else MATCH,
        "diff": "\n".join(lines),
    }


def refresh(ip: str) -> str | None:
    state = compare(ip)["state"]
    store.save_drift(ip, state)
    return state


def refresh_attached(baseline_id: int) -> None:
    for ip, attached_to in store.attached().items():
        if attached_to == baseline_id:
            refresh(ip)


def _short(model: dict) -> dict:
    return {"id": model["id"], "name": model["name"], "vendor": model["vendor"]}
