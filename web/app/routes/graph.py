from fastapi import APIRouter

from .. import inventory, store

router = APIRouter(prefix="/api")

ON_MAP = {"detected", "authorized", "failed"}


@router.get("/graph")
def graph() -> dict:
    all_devices = [inventory.decorate(d) for d in store.devices()]
    by_hostname = {d["hostname"]: d for d in all_devices if d.get("hostname")}
    by_ip = {d["ip"]: d for d in all_devices}
    known = inventory.capabilities()

    # серверы и рабочие станции на карту не идут, они остаются в списке
    nodes = [
        {
            "id": d["ip"],
            "label": d.get("hostname") or d["ip"],
            "status": d["state"],
            "vendor": d.get("vendor") or d.get("vendor_guess") or "",
            "type": inventory.node_type(d),
        }
        for d in all_devices
        if d["status"] in ON_MAP
    ]

    # LLDP отдаёт имя соседа, но не адрес. пока есть неопознанные адреса,
    # сосед может оказаться любым из них, и рисовать его отдельно нельзя
    unresolved = any(d["status"] in ("detected", "failed") for d in all_devices)

    known_ids = {n["id"] for n in nodes}
    edges: dict[tuple, dict] = {}

    for link in store.neighbors():
        source = link["ip"]
        # адрес управления из LLDP привязывает соседа к найденному устройству
        # ещё до входа на него, по имени сосед находится только после входа
        peer = by_ip.get(link.get("remote_addr") or "") or by_hostname.get(
            link["remote_name"]
        )

        if peer:
            target = peer["ip"]
        elif unresolved:
            continue
        else:
            # все адреса опознаны, а сосед не нашёлся, значит он вне диапазона
            target = f"lldp:{link['remote_name']}"
            if target not in known_ids:
                known_ids.add(target)
                nodes.append(
                    {
                        "id": target,
                        "label": link["remote_name"],
                        "status": "unknown",
                        "vendor": "",
                        "type": inventory.device_type(
                            known.get(link["remote_name"], "")
                        ),
                    }
                )

        # связь сообщают оба соседа, концы упорядочиваем одинаково,
        # иначе она меняет направление и карта считает её новой
        key = tuple(sorted([(source, link["local_port"]), (target, link["remote_port"])]))
        edges.setdefault(
            key,
            {
                "id": f"{key[0][0]}:{key[0][1]}-{key[1][0]}:{key[1][1]}",
                "source": key[0][0],
                "source_port": key[0][1],
                "target": key[1][0],
                "target_port": key[1][1],
            },
        )

    return {"nodes": nodes, "edges": list(edges.values())}
