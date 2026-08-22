import re

from .base import Driver


class AristaEos(Driver):
    name = "arista_eos"
    vendor = "Arista"
    version_command = "show version"
    hostname_command = "show hostname"
    neighbors_command = "show lldp neighbors detail"
    config_command = "show running-config"
    config_flat_command = "show running-config"

    # правка уходит в running сразу, черновик появляется только в configure session
    pending_diff_commands = []

    enter_config = ["configure terminal"]
    leave_config = ["end", "write memory"]

    lldp_state_command = "show lldp"
    lldp_enable_commands = ["configure terminal", "lldp run", "end", "write memory"]

    prompt_pattern = r"[\w.\-]+(?:\([^)]*\))?[>#]"
    config_prompt_marker = r"\(config"

    baseline_ignore = [
        r"^hostname ",
        r"^\s*ip address ",
        r"^\s*description ",
        r"^snmp-server (?:chassis-id|location|engineID)",
        r"secret sha512|password 7|username .* secret",
        r"certificate|-----BEGIN",
    ]

    check_rules = {
        "telnet_off": {"forbid": [r"^\s*no shutdown\b.*telnet", r"^management telnet"]},
        "snmp_closed": {"forbid": [r"snmp-server community\s+public"]},
        "mgmt_acl": {"require": [r"ip access-group\s+\S+\s+in", r"^\s*ip access-class"]},
        "logging_on": {"require": [r"^logging (?:host|buffered|trap|level)"]},
        "dot1x": {"require": [r"dot1x pae authenticator", r"^dot1x system-auth-control"]},
    }

    @classmethod
    def matches(cls, output: str) -> bool:
        return "Arista" in output

    @classmethod
    def parse_version(cls, output: str) -> dict:
        model = ""
        version = ""

        for line in output.splitlines():
            stripped = line.strip()

            found = re.match(r"^Arista (\S+)", stripped)
            if found and not model:
                model = found.group(1)

            found = re.match(r"^Software image version:\s*(\S+)", stripped)
            if found:
                version = found.group(1)

        # имя устройства show version не отдаёт, его берёт hostname_command
        return {"hostname": "", "model": model, "version": version}

    @classmethod
    def parse_hostname(cls, output: str) -> str:
        found = re.search(r"^Hostname:\s*(\S+)", output, re.MULTILINE)
        return found.group(1) if found else ""

    @classmethod
    def device_type(cls, model: str) -> str:
        # 7500 и 7800 это шасси уровня ядра, остальные линейки коммутаторы
        if re.search(r"75\d\d|78\d\d", model):
            return "router"
        return "switch"

    @classmethod
    def normalize_config(cls, output: str) -> str:
        drop = ("! Command:", "! device:", "! boot system", "! Startup-config")
        kept = [
            line
            for line in output.splitlines()
            if line.strip() and not line.strip().startswith(drop)
        ]
        return "\n".join(kept).strip()

    @classmethod
    def normalize_flat(cls, output: str) -> str:
        return cls.normalize_config(output)

    @classmethod
    def lldp_ready(cls, output: str) -> bool:
        return "LLDP transmit" in output or "enabled" in output.lower()

    @classmethod
    def parse_neighbors(cls, output: str) -> list[dict]:
        links: list[dict] = []
        interface = None
        current: dict | None = None
        expect_address = False

        for line in output.splitlines():
            stripped = line.strip()

            found = re.match(r"^Interface (\S+) detected", stripped)
            if found:
                interface = found.group(1)
                current = None
                continue

            if stripped.startswith("Neighbor ") and interface:
                current = {
                    "local_port": interface,
                    "remote_name": "",
                    "remote_port": "",
                    "remote_addr": "",
                    "capabilities": "",
                }
                links.append(current)
                expect_address = False
                continue

            if current is None:
                continue

            found = re.match(r"^-?\s*Port ID\s*:\s*(.+)$", stripped)
            if found:
                current["remote_port"] = found.group(1).strip().strip('"')
                continue

            found = re.match(r"^-?\s*System Name\s*:\s*(.+)$", stripped)
            if found:
                current["remote_name"] = found.group(1).strip().strip('"')
                continue

            if re.match(r"^-?\s*System Capabilities\s*:", stripped):
                current["capabilities"] = cls._capabilities(stripped)
                continue

            if re.match(r"^-?\s*Management Address Subtype\s*:\s*IPv4", stripped):
                expect_address = True
                continue

            found = re.match(r"^-?\s*Management Address\s*:\s*(\S+)", stripped)
            if found and expect_address and not current["remote_addr"]:
                current["remote_addr"] = found.group(1)
                expect_address = False

        return [link for link in links if link["remote_name"]]

    @staticmethod
    def _capabilities(line: str) -> str:
        lowered = line.lower()
        found = []
        if "bridge" in lowered:
            found.append("BRIDGE")
        if "router" in lowered:
            found.append("ROUTER")
        if "wlan" in lowered:
            found.append("WLAN_ACCESS_POINT")
        return ",".join(found)
