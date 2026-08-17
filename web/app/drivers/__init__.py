from .base import Driver
from .nokia_srlinux import NokiaSrLinux

ALL: list[type[Driver]] = [NokiaSrLinux]


def by_vendor(vendor: str) -> type[Driver] | None:
    for driver in ALL:
        if driver.vendor == vendor:
            return driver
    return None
