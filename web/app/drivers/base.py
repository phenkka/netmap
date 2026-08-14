class Driver:
    """добавить вендора — добавить такой класс"""

    name = ""
    vendor = ""
    version_command = ""
    neighbors_command = ""

    @classmethod
    def matches(cls, version_output: str) -> bool:
        raise NotImplementedError

    @classmethod
    def parse_version(cls, output: str) -> dict:
        raise NotImplementedError

    @classmethod
    def parse_neighbors(cls, output: str) -> list[dict]:
        raise NotImplementedError

    @classmethod
    def device_type(cls, model: str) -> str:
        return "unknown"
