import re


class Driver:

    name = ""
    vendor = ""
    version_command = ""
    neighbors_command = ""
    config_command = ""

    # у Arista show version имени устройства не отдаёт, его спрашивают отдельно
    hostname_command = ""

    # та же конфигурация в виде команд. на устройство откат отправляет её,
    # разобранный человекочитаемый вывод обратно не применяется
    config_flat_command = ""

    # черновика конфигурации нет у Cisco IOS и MikroTik, они применяют сразу
    pending_diff_commands: list[str] = []

    enter_config: list[str] = []
    leave_config: list[str] = []
    # черновик после неудачного commit остаётся грязным и блокирует устройство
    discard_commands: list[str] = []

    lldp_state_command = ""
    lldp_enable_commands: list[str] = []

    # режим определяем по приглашению устройства, а не по набранной команде,
    # её чаще поднимают стрелкой вверх, чем печатают
    prompt_pattern = ""
    config_prompt_marker = ""

    # код проверки -> {"forbid": [...], "require": [...]}, шаблоны по строке
    # конфигурации. чего в таблице нет, то на этом железе не проверяется
    check_rules: dict[str, dict] = {}

    # у каждого устройства своё: имя, адреса, шифрованные секреты. в сверке с
    # эталоном такие строки дают расхождение всегда и топят настоящее
    baseline_ignore: list[str] = []

    @classmethod
    def comparable(cls, config: str) -> str:
        kept = []
        inside_pem = False
        for line in config.splitlines():
            # сертификат и ключ у каждого устройства свои и занимают десятки строк
            if "-----BEGIN" in line:
                inside_pem = True
                continue
            if inside_pem:
                inside_pem = "-----END" not in line
                continue
            if any(re.search(p, line, re.IGNORECASE) for p in cls.baseline_ignore):
                continue
            kept.append(line)
        return "\n".join(kept)

    @classmethod
    def matches(cls, version_output: str) -> bool:
        raise NotImplementedError

    @classmethod
    def parse_version(cls, output: str) -> dict:
        raise NotImplementedError

    @classmethod
    def parse_hostname(cls, output: str) -> str:
        return ""

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
    def normalize_flat(cls, output: str) -> str:
        return output.strip()

    @classmethod
    def clean_pending_diff(cls, output: str) -> str:
        return output.strip()

    @classmethod
    def lldp_ready(cls, output: str) -> bool:
        return True

    @classmethod
    def session(cls, commands: list[str]) -> list[str]:
        return [*cls.enter_config, *commands, *cls.leave_config]

    @classmethod
    def restore_commands(cls, flat: str, current: str = "") -> list[str]:
        return cls.session([line for line in flat.splitlines() if line.strip()])

    # ругань устройства в ответ на команду. проверяется по началу строки,
    # иначе слово error из имени счётчика сойдёт за отказ
    complaints = (r"^\s*%", r"^\s*Error", r"^\s*ERROR", r"invalid input", r"syntax error")

    @classmethod
    def applied_cleanly(cls, output: str) -> tuple[bool, str]:
        for line in output.splitlines():
            for pattern in cls.complaints:
                if re.search(pattern, line, re.IGNORECASE):
                    return False, line.strip()
        return True, ""
