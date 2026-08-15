import difflib

from fastapi import APIRouter, HTTPException

from .. import inventory, ssh, store

router = APIRouter(prefix="/api/devices")


@router.post("/{ip}/config")
def take_config(ip: str) -> dict:
    version = inventory.collect_config(ip, "manual")
    last = store.last_config(ip)
    if last:
        last.pop("text")
    return {"changed": bool(version), "version": last}


@router.get("/{ip}/versions")
def versions(ip: str) -> dict:
    return {"versions": store.configs(ip)}


@router.get("/{ip}/versions/{version_id}")
def version(ip: str, version_id: int) -> dict:
    found = store.config(version_id)
    if not found or found["ip"] != ip:
        raise HTTPException(404, "версия не найдена")
    return found


@router.get("/{ip}/diff")
def diff(ip: str, a: int | None = None, b: int | None = None) -> dict:
    history = store.configs(ip)
    if a is None or b is None:
        if len(history) < 2:
            return {"a": None, "b": None, "diff": ""}
        a, b = history[1]["id"], history[0]["id"]

    old, new = store.config(a), store.config(b)
    if not old or not new:
        raise HTTPException(404, "версия не найдена")

    lines = difflib.unified_diff(
        old["text"].splitlines(),
        new["text"].splitlines(),
        f"версия {old['id']}, {old['at']}",
        f"версия {new['id']}, {new['at']}",
        lineterm="",
    )
    return {"a": a, "b": b, "diff": "\n".join(lines)}


@router.get("/{ip}/pending")
def pending(ip: str) -> dict:
    """несохранённые правки там, где вендор даёт черновик"""
    driver = inventory.driver_for(ip)
    if not driver.pending_diff_commands:
        return {"supported": False, "diff": ""}

    username, password = inventory.require_credentials(ip)
    output = ssh.run_lines(ip, username, password, driver.pending_diff_commands)
    return {"supported": True, "diff": driver.clean_pending_diff(output)}
