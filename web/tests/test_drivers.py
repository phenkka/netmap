"""разбор вывода команд по образцам

Образцы Nokia берутся из stend/samples, они сняты с работающего стенда.
Образцы Cisco и Arista составлены по опубликованным производителями форматам
вывода: контейнерные образы этих вендоров закрыты регистрацией, снять с них
вывод на стенде пока нельзя. Проверять на живом оборудовании их всё равно надо.

Запуск: python3 -m tests.test_drivers из каталога web
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.drivers import AristaEos, CiscoIos, NokiaSrLinux  # noqa: E402

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


def main():
    for suite in (nokia, cisco, arista):
        suite()
        print()

    if failures:
        print(f"провалено проверок: {len(failures)}")
        sys.exit(1)
    print("все проверки прошли")


main()
