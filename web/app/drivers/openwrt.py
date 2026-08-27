import re

from . import lldpcli
from .base import Driver


class OpenWrt(Driver):
    # команд в духе show version у OpenWrt нет и не было, настройка идёт через
    # uci, а сведения о себе система держит в /etc/openwrt_release
    name = "openwrt"
    vendor = "OpenWrt"
    version_command = "cat /etc/openwrt_release; uname -n"
    neighbors_command = "lldpcli show neighbors details"
    config_command = "uci export"
    config_flat_command = "uci show"

    pending_diff_commands = []

    shell_login = True

    # uci пишет правку в свой черновик, на устройство её переносит commit
    enter_config = []
    leave_config = ["uci commit"]

    lldp_state_command = "lldpcli show configuration"
    lldp_enable_commands = []

    prompt_pattern = r"[\w.\-]+[$#]"
    config_prompt_marker = r"(?!)"

    management_ports = ("eth0",)

    baseline_ignore = [
        r"hostname",
        r"ipaddr|ip6addr|macaddr",
        r"password|key|psk",
        r"^system\.@system\[\d+\]\.(?:timezone|zonename)",
    ]

    check_rules = {
        # dropbear слушает только SSH, telnetd в современных сборках нет
        "telnet_off": {"forbid": [r"telnetd", r"option\s+telnet\s+'1'"]},
        "snmp_closed": {"forbid": [r"community\s+'?public'?"]},
        "logging_on": {"require": [r"log_ip|log_file|option\s+log_"]},
        "mgmt_acl": {"require": [r"config\s+rule", r"option\s+src\s+", r"firewall\."]},
    }

    # uci и оболочка ругаются по-своему, базовые шаблоны их не ловят
    complaints = Driver.complaints + (r"^uci:", r"^-?(?:ash|sh|bash):")

    @classmethod
    def matches(cls, output: str) -> bool:
        return "DISTRIB_ID='OpenWrt'" in output or "OpenWrt" in output

    @classmethod
    def parse_version(cls, output: str) -> dict:
        fields = {}
        for line in output.splitlines():
            found = re.match(r"^(DISTRIB_\w+)='(.*)'$", line.strip())
            if found:
                fields[found.group(1)] = found.group(2)

        # имя устройства печатает uname -n последней строкой
        tail = [line.strip() for line in output.splitlines() if line.strip()]
        hostname = ""
        if tail and not tail[-1].startswith("DISTRIB_"):
            hostname = tail[-1]

        version = fields.get("DISTRIB_RELEASE", "")
        revision = fields.get("DISTRIB_REVISION", "")
        if revision and revision not in version:
            version = f"{version} {revision}".strip()

        return {
            "hostname": hostname,
            "model": fields.get("DISTRIB_TARGET", ""),
            "version": version,
        }

    @classmethod
    def device_type(cls, model: str) -> str:
        # OpenWrt ставят на точки доступа и домашние маршрутизаторы
        return "wifi"

    @classmethod
    def normalize_config(cls, output: str) -> str:
        return output.strip()

    @classmethod
    def normalize_flat(cls, output: str) -> str:
        return output.strip()

    @classmethod
    def lldp_ready(cls, output: str) -> bool:
        return "Configuration" in output

    @classmethod
    def parse_neighbors(cls, output: str) -> list[dict]:
        return lldpcli.parse(output, skip=cls.management_ports)
