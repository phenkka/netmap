from .base import Driver


class NokiaSrLinux(Driver):
    name = "nokia_srlinux"
    vendor = "Nokia"
    version_command = "show version"
    neighbors_command = "info from state system lldp interface *"
    config_command = "info from running"
    config_flat_command = "info flat from running"

    # candidate общий для всех сессий, чужую несохранённую правку видно
    pending_diff_commands = ["enter candidate", "diff"]

    enter_config = ["enter candidate"]
    leave_config = ["commit now", "quit"]
    discard_commands = ["enter candidate", "discard now", "quit"]

    lldp_state_command = "info from running /system lldp"
    lldp_enable_commands = [
        "enter candidate",
        "set / system lldp admin-state enable",
        "set / system lldp management-address mgmt0.0 type [IPv4]",
        "commit now",
        "quit",
    ]
    # режимов четыре: running, candidate, show, state. приглашение вида
    # --{ + candidate shared default }-- , настройка идёт только в candidate
    prompt_pattern = r"--\{[^}]*\}"
    config_prompt_marker = r"candidate"

    baseline_ignore = [
        r"^\s*name\s+\S+\s*$",
        r"hostname",
        r"\$aes1\$",
        r"\$y\$",
        r"ssh-ed25519|ssh-rsa",
        r"address\s+\d+\.\d+\.\d+\.\d+",
        r"mac-address",
        r"system-mac",
    ]

    check_rules = {
        "telnet_off": {"forbid": [r"telnet-server admin-state enable"]},
        "snmp_closed": {"forbid": [r"snmp .*community public", r"community public"]},
        "mgmt_acl": {"require": [r"system control-plane-traffic input acl"]},
        "logging_on": {"require": [r"system logging"]},
        "dot1x": {"require": [r"interface \S+ dot1x", r"dot1x admin-state enable"]},
    }

    @classmethod
    def matches(cls, output: str) -> bool:
        return "SR Linux" in output

    @classmethod
    def parse_version(cls, output: str) -> dict:
        fields = {}
        for line in output.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        return {
            "hostname": fields.get("Hostname", ""),
            "model": fields.get("Chassis Type", ""),
            "version": fields.get("Software Version", ""),
        }

    @classmethod
    def restore_commands(cls, flat: str, current: str = "") -> list[str]:
        """к возврату прежних значений добавляет удаление того, чего в снимке нет"""
        target = [line for line in flat.splitlines() if line.strip()]
        commands: list[str] = []

        if current:
            wanted = set(target)
            paths = {cls._path(line) for line in target}
            gone = {
                cls._path(line)
                for line in current.splitlines()
                if line.strip() and line not in wanted and cls._path(line) not in paths
            }
            # длинный путь удаляем первым: родитель уносит потомка, и delete
            # потомка после этого падает, а commit на SR Linux атомарный
            commands += [f"delete {path}" for path in sorted(gone, key=len, reverse=True) if path]

        return cls.session(commands + target)

    @staticmethod
    def _path(line: str) -> str:
        """путь настройки без значения: set / system information location "..." """
        body = line.strip()
        if not body.startswith("set "):
            return ""
        body = body[4:].strip()

        if body.endswith("]"):
            cut = body.rfind("[")
            return body[:cut].strip() if cut > 0 else ""
        if body.endswith('"'):
            cut = body.rfind('"', 0, len(body) - 1)
            return body[:cut].strip() if cut > 0 else ""

        parts = body.rsplit(None, 1)
        return parts[0].strip() if len(parts) == 2 else ""

    @classmethod
    def normalize_flat(cls, output: str) -> str:
        # строки вида "set /  !!! комментарий" обратно на устройство не заходят
        return "\n".join(
            line
            for line in output.splitlines()
            if line.strip() and "!!!" not in line
        )

    @classmethod
    def lldp_ready(cls, output: str) -> bool:
        # сам LLDP включён по умолчанию, а объявление адреса управления нет
        if "admin-state disable" in output:
            return False
        return "management-address" in output

    @classmethod
    def device_type(cls, model: str) -> str:
        # 7220 IXR вендор называет leaf switch, 7250 и 7750 — маршрутизаторы
        if "7220" in model:
            return "switch"
        if "7250" in model or "7750" in model:
            return "router"
        return "switch"

    @classmethod
    def parse_neighbors(cls, output: str) -> list[dict]:
        # в короткой таблице нет поля возможностей
        links: list[dict] = []
        interface = None
        current: dict | None = None

        for line in output.splitlines():
            line = line.strip()

            if line.startswith("interface "):
                interface = line.split()[1]
                current = None
            elif line.startswith("neighbor ") and interface:
                current = {
                    "local_port": interface,
                    "remote_name": "",
                    "remote_port": "",
                    "remote_addr": "",
                    "capabilities": [],
                }
                links.append(current)
            elif current is not None:
                if line.startswith("system-name "):
                    current["remote_name"] = line.split(None, 1)[1].strip('"')
                elif line.startswith("port-id ") and not line.startswith("port-id-type"):
                    current["remote_port"] = line.split(None, 1)[1].strip('"')
                elif line.startswith("management-address ") and not current["remote_addr"]:
                    current["remote_addr"] = line.split()[1]
                elif line.startswith("capability "):
                    current["capabilities"].append(line.split()[1])

        # в сети управления все видят всех, это не физический линк
        return [
            dict(link, capabilities=",".join(link["capabilities"]))
            for link in links
            if link["local_port"].startswith("ethernet-") and link["remote_name"]
        ]
