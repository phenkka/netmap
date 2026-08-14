from .base import Driver


class NokiaSrLinux(Driver):
    name = "nokia_srlinux"
    vendor = "Nokia"
    version_command = "show version"
    neighbors_command = "info from state system lldp interface *"

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
                    "capabilities": [],
                }
                links.append(current)
            elif current is not None:
                if line.startswith("system-name "):
                    current["remote_name"] = line.split(None, 1)[1].strip('"')
                elif line.startswith("port-id ") and not line.startswith("port-id-type"):
                    current["remote_port"] = line.split(None, 1)[1].strip('"')
                elif line.startswith("capability "):
                    current["capabilities"].append(line.split()[1])

        # в сети управления все видят всех, это не физический линк
        return [
            dict(link, capabilities=",".join(link["capabilities"]))
            for link in links
            if link["local_port"].startswith("ethernet-") and link["remote_name"]
        ]
