from .arista_eos import AristaEos
from .base import Driver
from .cisco_ios import CiscoIos
from .frrouting import FrRouting
from .nokia_srlinux import NokiaSrLinux
from .openwrt import OpenWrt

# порядок важен: опознание идёт перебором, и первым спрашивается тот, чья
# команда версии безобиднее для чужого железа
ALL: list[type[Driver]] = [NokiaSrLinux, CiscoIos, AristaEos, FrRouting, OpenWrt]


def by_vendor(vendor: str) -> type[Driver] | None:
    for driver in ALL:
        if driver.vendor == vendor:
            return driver
    return None
