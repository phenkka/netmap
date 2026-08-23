import gzip
import json
from datetime import datetime, timezone

from . import store

FORMAT = "netmap-backup"
VERSION = 1


def pack() -> bytes:
    devices = [
        {
            "ip": row["ip"],
            "hostname": row["hostname"],
            "vendor": row["vendor"],
            "model": row["model"],
            "version": row["version"],
            "mac": row["mac"],
        }
        for row in store.devices()
    ]

    models = []
    for short in store.baselines():
        full = store.baseline(short["id"])
        if full:
            models.append(
                {
                    "name": full["name"],
                    "vendor": full["vendor"],
                    "at": full["at"],
                    "text": full["text"],
                }
            )

    configs = [
        {
            "ip": row["ip"],
            "at": row["at"],
            "sha256": row["sha256"],
            "lines": row["lines"],
            "source": row["source"],
            "text": row["text"],
            "flat": row["flat"],
        }
        for row in store.restore_all_configs()
    ]

    body = {
        "format": FORMAT,
        "version": VERSION,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "devices": devices,
        "baselines": models,
        "configs": configs,
    }
    return gzip.compress(json.dumps(body, ensure_ascii=False).encode("utf-8"), 6)


def unpack(blob: bytes) -> dict:
    try:
        body = json.loads(gzip.decompress(blob).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        raise ValueError("файл не читается как копия netmap")

    if body.get("format") != FORMAT:
        raise ValueError("это не копия netmap")
    if body.get("version") != VERSION:
        raise ValueError(f"копия версии {body.get('version')}, продукт понимает {VERSION}")

    added = 0
    for item in body.get("configs", []):
        if store.insert_config(
            item["ip"],
            item["at"],
            item["sha256"],
            item["lines"],
            item.get("source") or "backup",
            item["text"],
            item.get("flat"),
        ):
            added += 1

    models = 0
    known = {row["name"] for row in store.baselines()}
    for item in body.get("baselines", []):
        if item["name"] in known:
            continue
        store.save_baseline(item["name"], item.get("vendor") or "", item["text"])
        models += 1

    return {
        "configs": added,
        "baselines": models,
        "skipped": len(body.get("configs", [])) - added,
        "at": body.get("at"),
    }
