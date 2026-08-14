# Выводы команд

Настоящие выводы, снятые по SSH с работающего оборудования на стенде.
Нужны для разработки парсеров, чтобы не поднимать стенд каждый раз.

Формат имени файла — команда, в которой пробелы и слэши заменены на подчёркивание.

## nokia_srlinux

Nokia SR Linux v26.7.1, платформа 7220 IXR-D2L, снято с узла core1.

| Файл                                          | Что внутри                             |
|-----------------------------------------------|----------------------------------------|
| `show_version.txt`                            | модель, серийный номер, версия ПО      |
| `show_system_lldp_neighbor.txt`               | соседи по LLDP, источник для карты     |
| `show_interface_brief.txt`                    | список интерфейсов и их состояние      |
| `show_network-instance_default_protocols.txt` | протоколы маршрутизации                |
| `show_system_aaa_authentication.txt`          | настройки аутентификации               |
| `show_acl_summary.txt`                        | списки доступа                         |
| `info_from_running.txt`                       | полная текущая конфигурация            |

## Как снять заново

```shell
sshpass -p 'NokiaSrl1!' ssh -o StrictHostKeyChecking=no admin@172.20.20.11 'show version' > show_version.txt
```
