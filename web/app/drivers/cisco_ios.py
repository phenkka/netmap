import re

from .base import Driver


class CiscoIos(Driver):
    name = "cisco_ios"
    vendor = "Cisco"
    version_command = "show version"
    neighbors_command = "show lldp neighbors detail"
    config_command = "show running-config"
    # running-config сам по себе набор команд, отдельного командного вида нет
    config_flat_command = "show running-config"

    # черновика нет, команда применяется сразу. поэтому и проверять нечего
    pending_diff_commands = []

    enter_config = ["configure terminal"]
    leave_config = ["end", "write memory"]

    lldp_state_command = "show lldp"
    lldp_enable_commands = ["configure terminal", "lldp run", "end", "write memory"]

    prompt_pattern = r"[\w.\-]+(?:\([^)]*\))?[>#]"
    config_prompt_marker = r"\(config"

    baseline_ignore = [
        r"^hostname ",
        r"^ip address ",
        r"^\s*ip address ",
        r"^ntp clock-period",
        r"^snmp-server chassis-id",
        r"^\s*description ",
        r"crypto pki certificate",
        r"^\s*quit\s*$",
        r"enable secret|enable password|username .* (?:secret|password)",
        r"^! Last configuration change",
        r"^Current configuration",
    ]

    check_rules = {
        "telnet_off": {"forbid": [r"transport input .*telnet", r"transport input all"]},
        "snmp_closed": {"forbid": [r"snmp-server community\s+public"]},
        "mgmt_acl": {"require": [r"access-class\s+\S+\s+in", r"ip access-class"]},
        "logging_on": {"require": [r"^logging (?:host|buffered|trap|\d)"]},
        "dot1x": {
            "require": [
                r"dot1x system-auth-control",
                r"authentication port-control auto",
                r"dot1x pae authenticator",
            ]
        },
    }

    @classmethod
    def matches(cls, output: str) -> bool:
        return "Cisco IOS" in output or "IOS Software" in output

    @classmethod
    def parse_version(cls, output: str) -> dict:
        hostname = ""
        model = ""
        version = ""

        for line in output.splitlines():
            stripped = line.strip()

            # имя устройства встречается только в строке про время работы
            found = re.match(r"^(\S+) uptime is ", stripped)
            if found:
                hostname = found.group(1)

            found = re.search(r"Version ([\w.()]+)", stripped)
            if found and not version:
                version = found.group(1).rstrip(",")

            if not model:
                found = re.match(r"^[Cc]isco (\S+) .*(?:memory|processor)", stripped)
                if found:
                    model = found.group(1)

        if not model:
            found = re.search(r"^Model [Nn]umber\s*:\s*(\S+)", output, re.MULTILINE)
            if found:
                model = found.group(1)

        return {"hostname": hostname, "model": model, "version": version}

    @classmethod
    def device_type(cls, model: str) -> str:
        # каталист это коммутаторы, ISR и ASR маршрутизаторы
        upper = model.upper()
        if upper.startswith(("WS-", "C9", "C3", "C2")) or "CAT" in upper:
            return "switch"
        if upper.startswith(("ISR", "ASR", "CISCO1", "CISCO2", "CISCO3", "C8")):
            return "router"
        return "switch"

    @classmethod
    def normalize_config(cls, output: str) -> str:
        # эти строки меняются сами и давали бы новую версию на каждом обходе
        drop = (
            "Building configuration",
            "Current configuration",
            "! Last configuration change",
            "ntp clock-period",
        )
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
        return "LLDP is not enabled" not in output

    @classmethod
    def parse_neighbors(cls, output: str) -> list[dict]:
        links: list[dict] = []
        current: dict | None = None
        in_addresses = False

        for line in output.splitlines():
            stripped = line.strip()

            if stripped.startswith("Local Intf:"):
                current = {
                    "local_port": stripped.split(":", 1)[1].strip(),
                    "remote_name": "",
                    "remote_port": "",
                    "remote_addr": "",
                    "capabilities": "",
                }
                links.append(current)
                in_addresses = False
                continue

            if current is None:
                continue

            if stripped.startswith("Port id:"):
                current["remote_port"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("System Name:"):
                current["remote_name"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Enabled Capabilities:"):
                current["capabilities"] = cls._capabilities(
                    stripped.split(":", 1)[1].strip()
                )
            elif stripped.startswith("Management Addresses"):
                in_addresses = True
            elif in_addresses and stripped.startswith("IP:"):
                if not current["remote_addr"]:
                    current["remote_addr"] = stripped.split(":", 1)[1].strip()
                in_addresses = False

        return [link for link in links if link["remote_name"]]

    @staticmethod
    def _capabilities(letters: str) -> str:
        # LLDP у Cisco отдаёт буквами: B мост, R маршрутизатор, W точка доступа
        words = {"B": "BRIDGE", "R": "ROUTER", "W": "WLAN_ACCESS_POINT"}
        return ",".join(
            words[letter]
            for letter in letters.replace(" ", "").split(",")
            if letter in words
        )
