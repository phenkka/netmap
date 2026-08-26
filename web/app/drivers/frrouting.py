import re

from . import lldpcli
from .base import Driver


class FrRouting(Driver):
    # вход по SSH попадает в обычную оболочку, поэтому команды идут так же,
    # как их набирает администратор: конфигурация в vtysh, соседи в lldpcli
    name = "frrouting"
    vendor = "FRRouting"
    version_command = 'vtysh -c "show version"'
    neighbors_command = "lldpcli show neighbors details"
    config_command = 'vtysh -c "show running-config"'
    config_flat_command = 'vtysh -c "show running-config"'

    # правка уходит в running сразу, черновика нет
    pending_diff_commands = []

    # первая строка запускает vtysh, дальше он сам читает поток команд
    enter_config = ["vtysh", "configure terminal"]
    leave_config = ["end", "write memory", "exit"]

    lldp_state_command = "lldpcli show configuration"
    # lldpd поднимается вместе с системой, включать его через продукт нечем
    lldp_enable_commands = []

    prompt_pattern = r"[\w.\-]+(?:\([^)]*\))?[$#>]"
    config_prompt_marker = r"\(config"

    # eth0 это сеть управления, в ней каждый видит каждого
    management_ports = ("eth0",)

    baseline_ignore = [
        r"^hostname ",
        r"^\s*ip address ",
        r"^\s*description ",
        r"^frr version ",
        r"password|secret",
    ]

    check_rules = {
        # vtysh слушает локальный сокет, telnet у демонов включается отдельно
        "telnet_off": {"forbid": [r"^\s*line vty.*telnet", r"telnet-port"]},
        "snmp_closed": {"forbid": [r"community\s+public"]},
        "mgmt_acl": {"require": [r"access-class\s+\S+", r"^\s*ip access-list"]},
        "logging_on": {"require": [r"^log (?:syslog|file|stdout|monitor)"]},
    }

    @classmethod
    def matches(cls, output: str) -> bool:
        return "FRRouting" in output

    @classmethod
    def parse_version(cls, output: str) -> dict:
        # FRRouting 8.4_git (edge1) on Linux(6.18.12+kali-amd64).
        found = re.search(r"^FRRouting (\S+) \(([^)]*)\) on (\S+)", output, re.MULTILINE)
        if not found:
            return {"hostname": "", "model": "", "version": ""}
        return {
            "hostname": found.group(2),
            "model": found.group(3).rstrip("."),
            "version": found.group(1),
        }

    @classmethod
    def device_type(cls, model: str) -> str:
        return "router"

    @classmethod
    def normalize_config(cls, output: str) -> str:
        drop = ("Building configuration", "Current configuration")
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
        return "Configuration" in output or "lldp" in output.lower()

    @classmethod
    def parse_neighbors(cls, output: str) -> list[dict]:
        return lldpcli.parse(output, skip=cls.management_ports)
