import re

WORDS = {"bridge": "BRIDGE", "router": "ROUTER", "wlan": "WLAN_ACCESS_POINT"}


def parse(output: str, skip: tuple[str, ...] = ()) -> list[dict]:
    # skip это интерфейсы сети управления, в ней все видят всех
    links: list[dict] = []
    current: dict | None = None
    capabilities: list[str] = []

    def close() -> None:
        if current is not None:
            current["capabilities"] = ",".join(capabilities)

    for line in output.splitlines():
        stripped = line.strip()

        found = re.match(r"^Interface:\s+(\S+?),", stripped)
        if found:
            close()
            capabilities = []
            port = found.group(1)
            if port in skip:
                current = None
                continue
            current = {
                "local_port": port,
                "remote_name": "",
                "remote_port": "",
                "remote_addr": "",
                "capabilities": "",
            }
            links.append(current)
            continue

        if current is None:
            continue

        found = re.match(r"^SysName:\s+(.+)$", stripped)
        if found:
            current["remote_name"] = found.group(1).strip()
            continue

        # PortID: ifname ethernet-1/3 либо PortID: mac 86:d7:f4:b0:9b:e1
        found = re.match(r"^PortID:\s+(?:ifname|local|mac)\s+(.+)$", stripped)
        if found:
            current["remote_port"] = found.group(1).strip()
            continue

        found = re.match(r"^MgmtIP:\s+(\d+\.\d+\.\d+\.\d+)$", stripped)
        if found and not current["remote_addr"]:
            current["remote_addr"] = found.group(1)
            continue

        found = re.match(r"^Capability:\s+(\w+),\s*on$", stripped)
        if found:
            word = WORDS.get(found.group(1).lower())
            if word and word not in capabilities:
                capabilities.append(word)

    close()
    return [link for link in links if link["remote_name"]]
