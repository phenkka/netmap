class Driver:
    """добавить вендора — добавить такой класс"""

    name = ""
    vendor = ""
    version_command = ""
    neighbors_command = ""
    config_command = ""

    # черновика конфигурации нет у Cisco IOS и MikroTik, они применяют сразу
    pending_diff_commands: list[str] = []

    # режим определяем по приглашению устройства, а не по набранной команде,
    # её чаще поднимают стрелкой вверх, чем печатают
    prompt_pattern = ""
    config_prompt_marker = ""

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

    @classmethod
    def normalize_config(cls, output: str) -> str:
        # счётчики и метки времени меняются сами, иначе каждый обход даёт новую версию
        return output.strip()

    @classmethod
    def clean_pending_diff(cls, output: str) -> str:
        return output.strip()
