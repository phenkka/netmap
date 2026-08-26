import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.drivers import (  # noqa: E402
    AristaEos,
    CiscoIos,
    FrRouting,
    NokiaSrLinux,
    OpenWrt,
)

SAMPLES = Path(__file__).resolve().parent.parent.parent / "stend" / "samples"

failures = []


def check(what, got, wanted):
    if got == wanted:
        print(f"  ok   {what}")
    else:
        print(f"  FAIL {what}: получено {got!r}, ожидалось {wanted!r}")
        failures.append(what)


CISCO_VERSION = """\
Cisco IOS Software, C2960X Software (C2960X-UNIVERSALK9-M), Version 15.2(4)E10, RELEASE SOFTWARE (fc2)
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2021 by Cisco Systems, Inc.

ROM: Bootstrap program is C2960X boot loader
BOOTLDR: C2960X Boot Loader (C2960X-HBOOT-M) Version 15.2(4r)E1, RELEASE SOFTWARE (fc1)

acc-sw-01 uptime is 32 weeks, 4 days, 6 hours, 12 minutes
System returned to ROM by power-on
System image file is "flash:/c2960x-universalk9-mz.152-4.E10.bin"

cisco WS-C2960X-24TS-L (APM86XXX) processor (revision H0) with 131072K bytes of memory.
Processor board ID FCQ1932X0GH
Model Number                         : WS-C2960X-24TS-L
"""

CISCO_LLDP = """\
------------------------------------------------
Local Intf: Gi1/0/1
Chassis id: 0062.ec9a.1b80
Port id: Gi1/0/24
Port Description: GigabitEthernet1/0/24
System Name: core-sw-01

System Description:
Cisco IOS Software, C3750E Software

Time remaining: 97 seconds
System Capabilities: B,R
Enabled Capabilities: B
Management Addresses:
    IP: 10.10.10.2
Auto Negotiation - supported, enabled

------------------------------------------------
Local Intf: Gi1/0/2
Chassis id: 0062.ec9a.2c40
Port id: Gi0/1
Port Description: GigabitEthernet0/1
System Name: edge-rtr-01

Time remaining: 101 seconds
System Capabilities: R
Enabled Capabilities: R
Management Addresses:
    IP: 10.10.10.3

Total entries displayed: 2
"""

ARISTA_VERSION = """\
Arista DCS-7050SX3-48YC8-F
Hardware version: 11.03
Serial number: JPE19141235
System MAC address: 2899.3a5e.0f4c

Software image version: 4.32.2F
Architecture: x86_64
Internal build version: 4.32.2F-38195967.4322F

Uptime: 3 weeks, 2 days, 5 hours and 12 minutes
Total memory: 8129016 kB
"""

ARISTA_HOSTNAME = """\
Hostname: leaf-01
FQDN: leaf-01.lab.local
"""

ARISTA_LLDP = """\
Interface Ethernet1 detected 1 LLDP neighbors:

  Neighbor 2899.3a5e.0f4c/"Ethernet49/1", age 21 seconds
  Discovered 0:12:33 ago; Last changed 0:12:33 ago
  - Chassis ID type: MAC address (4)
    Chassis ID     : 2899.3a5e.0f4c
  - Port ID type: Interface name (5)
    Port ID     : "Ethernet49/1"
  - Time To Live: 120 seconds
  - System Name: "spine-01"
  - System Description: "Arista Networks EOS version 4.32.2F"
  - System Capabilities : Bridge, Router
    Enabled Capabilities: Bridge, Router
  - Management Address Subtype: IPv4
    Management Address    : 10.10.10.11

Interface Ethernet2 detected 1 LLDP neighbors:

  Neighbor 2899.3a5e.7788/"Ethernet50/1", age 15 seconds
  - Port ID type: Interface name (5)
    Port ID     : "Ethernet50/1"
  - System Name: "spine-02"
  - System Capabilities : Bridge
    Enabled Capabilities: Bridge
  - Management Address Subtype: IPv4
    Management Address    : 10.10.10.12
"""


def cisco():
    print("Cisco IOS")
    check("опознаётся", CiscoIos.matches(CISCO_VERSION), True)

    identity = CiscoIos.parse_version(CISCO_VERSION)
    check("имя", identity["hostname"], "acc-sw-01")
    check("модель", identity["model"], "WS-C2960X-24TS-L")
    check("версия", identity["version"], "15.2(4)E10")
    check("тип по модели", CiscoIos.device_type(identity["model"]), "switch")

    links = CiscoIos.parse_neighbors(CISCO_LLDP)
    check("соседей найдено", len(links), 2)
    check("порт", links[0]["local_port"], "Gi1/0/1")
    check("сосед", links[0]["remote_name"], "core-sw-01")
    check("порт соседа", links[0]["remote_port"], "Gi1/0/24")
    check("адрес соседа", links[0]["remote_addr"], "10.10.10.2")
    check("возможности", links[0]["capabilities"], "BRIDGE")
    check("возможности второго", links[1]["capabilities"], "ROUTER")

    body = CiscoIos.normalize_config(
        "Building configuration...\n\n"
        "Current configuration : 4021 bytes\n"
        "! Last configuration change at 10:12:44 MSK Tue Aug 5 2025\n"
        "!\nhostname acc-sw-01\n!\nntp clock-period 17179862\n"
    )
    check("шум убран", body, "!\nhostname acc-sw-01\n!")

    passed = {r["code"]: r["state"] for r in _checks(CiscoIos, TELNET_ON_CONFIG)}
    check("telnet пойман", passed["telnet_off"], "fail")
    check("snmp public пойман", passed["snmp_closed"], "fail")
    check("журналирование найдено", passed["logging_on"], "pass")


TELNET_ON_CONFIG = """\
hostname acc-sw-01
logging host 10.10.10.50
snmp-server community public RO
line vty 0 4
 transport input telnet ssh
"""

# на стенде 802.1X не настроить: контейнерный SR Linux слова dot1x не знает,
# схема интерфейса его не содержит. поэтому положительный исход правила
# проверяется здесь, иначе кривую регулярку не отличить от отсутствия настройки
NOKIA_TIDY = """\
set / system lldp admin-state enable
set / system logging buffer messages rotate 3
set / system control-plane-traffic input acl acl-filter cpm type ipv4
set / interface ethernet-1/3 dot1x admin-state enable
"""

NOKIA_SLOPPY = """\
set / system lldp admin-state enable
set / system telnet-server admin-state enable
set / system snmp community public
"""


def _checks(driver, config):
    return checks_with(driver, config, ("netadmin", "S3cret!"))


def checks_with(driver, config, login):
    from app import checks

    return checks.run(config, driver.vendor, login)


def arista():
    print("Arista EOS")
    check("опознаётся", AristaEos.matches(ARISTA_VERSION), True)

    identity = AristaEos.parse_version(ARISTA_VERSION)
    check("модель", identity["model"], "DCS-7050SX3-48YC8-F")
    check("версия", identity["version"], "4.32.2F")
    check("имя отдельной командой", AristaEos.parse_hostname(ARISTA_HOSTNAME), "leaf-01")
    check("тип по модели", AristaEos.device_type(identity["model"]), "switch")
    check("тип шасси ядра", AristaEos.device_type("DCS-7504N"), "router")

    links = AristaEos.parse_neighbors(ARISTA_LLDP)
    check("соседей найдено", len(links), 2)
    check("порт", links[0]["local_port"], "Ethernet1")
    check("сосед", links[0]["remote_name"], "spine-01")
    check("порт соседа", links[0]["remote_port"], "Ethernet49/1")
    check("адрес соседа", links[0]["remote_addr"], "10.10.10.11")
    check("возможности", links[0]["capabilities"], "BRIDGE,ROUTER")
    check("второй сосед", links[1]["remote_name"], "spine-02")


def nokia():
    print("Nokia SR Linux")
    version = (SAMPLES / "nokia_srlinux" / "show_version.txt").read_text(encoding="utf-8")
    check("опознаётся", NokiaSrLinux.matches(version), True)

    identity = NokiaSrLinux.parse_version(version)
    check("имя", identity["hostname"], "core1")
    check("модель", identity["model"], "7220 IXR-D2L")
    check("тип по модели", NokiaSrLinux.device_type(identity["model"]), "switch")

    lldp = (SAMPLES / "nokia_srlinux" / "info_from_state_lldp.txt").read_text(
        encoding="utf-8"
    )
    links = NokiaSrLinux.parse_neighbors(lldp)
    check("соседи только по физике", all(
        link["local_port"].startswith("ethernet-") for link in links
    ), True)

    flat = "set / system information location \"rack 1\"\nset / system lldp admin-state enable\n"
    check(
        "путь без значения",
        NokiaSrLinux._path('set / system information location "rack 1"'),
        "/ system information location",
    )
    check(
        "путь у списка",
        NokiaSrLinux._path("set / system lldp management-address mgmt0.0 type [ IPv4 ]"),
        "/ system lldp management-address mgmt0.0 type",
    )

    # откат удаляет то, чего в снимке нет, и возвращает остальное
    commands = NokiaSrLinux.restore_commands(
        "set / system lldp admin-state enable",
        flat,
    )
    check("удаление добавленного", "delete / system information location" in commands, True)
    check("вход в черновик", commands[0], "enter candidate")
    check("сохранение", commands[-2:], ["commit now", "quit"])

    tidy = {r["code"]: r["state"] for r in _checks(NokiaSrLinux, NOKIA_TIDY)}
    check("802.1X настроен — проходит", tidy["dot1x"], "pass")
    check("журналирование — проходит", tidy["logging_on"], "pass")
    check("список доступа — проходит", tidy["mgmt_acl"], "pass")
    check("telnet выключен — проходит", tidy["telnet_off"], "pass")
    check("snmp закрыт — проходит", tidy["snmp_closed"], "pass")

    sloppy = {r["code"]: r["state"] for r in _checks(NokiaSrLinux, NOKIA_SLOPPY)}
    check("telnet включён — падает", sloppy["telnet_off"], "fail")
    check("snmp public — падает", sloppy["snmp_closed"], "fail")
    check("нет журналирования — падает", sloppy["logging_on"], "fail")
    check("нет 802.1X — падает", sloppy["dot1x"], "fail")

    # пароль из документации Nokia продукт обязан ловить
    default = {r["code"]: r["state"] for r in
               checks_with(NokiaSrLinux, NOKIA_TIDY, ("admin", "NokiaSrl1!"))}
    check("пароль по умолчанию пойман", default["no_default_users"], "fail")
    check("свой пароль — проходит", tidy["no_default_users"], "pass")


# Выводы FRRouting и OpenWrt сняты со стенда, узлы edge1 и ap1.
FRR_VERSION = """\
FRRouting 8.4_git (edge1) on Linux(6.18.12+kali-amd64).
Copyright 1996-2005 Kunihiro Ishiguro, et al.
configured with:
    '--prefix=/usr' '--enable-vtysh'
"""

FRR_CONFIG = """\
Building configuration...

Current configuration:
!
frr version 8.4_git
frr defaults traditional
hostname edge1
no ipv6 forwarding
service integrated-vtysh-config
!
end
"""

# eth0 это сеть управления, там устройства видят друг друга без физической связи
FRR_LLDP = """\
-------------------------------------------------------------------------------
LLDP neighbors:
-------------------------------------------------------------------------------
Interface:    eth0, via: LLDP, RID: 1, Time: 0 day, 00:00:39
  Chassis:
    ChassisID:    mac 86:d7:f4:b0:9b:e1
    SysName:      edge2
    MgmtIP:       172.20.20.22
    Capability:   Router, on
  Port:
    PortID:       ifname eth0
-------------------------------------------------------------------------------
Interface:    eth1, via: LLDP, RID: 2, Time: 0 day, 00:05:17
  Chassis:
    ChassisID:    mac 1a:46:02:ff:00:00
    SysName:      core1
    MgmtIP:       172.20.20.11
    Capability:   Bridge, off
    Capability:   Router, on
  Port:
    PortID:       ifname ethernet-1/3
-------------------------------------------------------------------------------
"""

OPENWRT_VERSION = """\
DISTRIB_ID='OpenWrt'
DISTRIB_RELEASE='SNAPSHOT'
DISTRIB_REVISION='r34693-4271b0b0b4'
DISTRIB_TARGET='x86/64'
DISTRIB_ARCH='x86_64'
DISTRIB_DESCRIPTION='OpenWrt SNAPSHOT r34693-4271b0b0b4'
DISTRIB_TAINTS=''
ap1
"""


def frrouting():
    print("FRRouting")
    check("опознаётся", FrRouting.matches(FRR_VERSION), True)

    identity = FrRouting.parse_version(FRR_VERSION)
    check("имя", identity["hostname"], "edge1")
    check("версия", identity["version"], "8.4_git")
    check("тип", FrRouting.device_type(identity["model"]), "router")

    body = FrRouting.normalize_config(FRR_CONFIG)
    check("шум убран", body.splitlines()[0], "!")
    check("имя осталось", "hostname edge1" in body, True)

    links = FrRouting.parse_neighbors(FRR_LLDP)
    check("сеть управления отброшена", len(links), 1)
    check("порт", links[0]["local_port"], "eth1")
    check("сосед", links[0]["remote_name"], "core1")
    check("порт соседа", links[0]["remote_port"], "ethernet-1/3")
    check("адрес соседа", links[0]["remote_addr"], "172.20.20.11")
    check("только включённые возможности", links[0]["capabilities"], "ROUTER")

    # правка идёт потоком в vtysh, первой строкой он и запускается
    commands = FrRouting.session(["ip route 10.0.0.0/8 blackhole"])
    check("запуск vtysh", commands[0], "vtysh")
    check("выход с сохранением", commands[-2:], ["write memory", "exit"])


def openwrt():
    print("OpenWrt")
    check("опознаётся", OpenWrt.matches(OPENWRT_VERSION), True)

    identity = OpenWrt.parse_version(OPENWRT_VERSION)
    check("имя", identity["hostname"], "ap1")
    check("модель", identity["model"], "x86/64")
    check("версия", identity["version"], "SNAPSHOT r34693-4271b0b0b4")
    check("тип", OpenWrt.device_type(identity["model"]), "wifi")

    # у OpenWrt нет команд show, настройка переносится на устройство через uci
    check("сохранение правки", OpenWrt.session(["uci set system.@system[0].hostname='ap9'"])[-1],
          "uci commit")


def main():
    for suite in (nokia, cisco, arista, frrouting, openwrt):
        suite()
        print()

    if failures:
        print(f"провалено проверок: {len(failures)}")
        sys.exit(1)
    print("все проверки прошли")


main()
