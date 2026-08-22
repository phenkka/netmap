from .arista_eos import AristaEos
from .base import Driver
from .cisco_ios import CiscoIos
from .nokia_srlinux import NokiaSrLinux

ALL: list[type[Driver]] = [NokiaSrLinux, CiscoIos, AristaEos]


def by_vendor(vendor: str) -> type[Driver] | None:
    for driver in ALL:
        if driver.vendor == vendor:
            return driver
    return None
