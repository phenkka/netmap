# Стенд

Тестовая сеть для разработки. Устройства эмулируются контейнерами, но SSH и команды
у них настоящие, вендорские. Физическое железо не нужно.

Три коммутатора Nokia SR Linux и две рабочие станции Alpine Linux.

## Топология

```
              core1
             /     \
      e1/1  /       \  e1/2
           /         \
        acc1 ------- acc2
       /   e1/2   e1/2   \
  e1/3/                   \e1/3
     pc1                  pc2
```

| Узел  | Адрес         | Что это        |
|-------|---------------|----------------|
| core1 | 172.20.20.11  | Nokia SR Linux |
| acc1  | 172.20.20.12  | Nokia SR Linux |
| acc2  | 172.20.20.13  | Nokia SR Linux |
| pc1   | 172.20.20.101 | Alpine Linux   |
| pc2   | 172.20.20.102 | Alpine Linux   |

Вход на устройства: `admin` / `NokiaSrl1!`

## Требования

Linux с ядром 5.x или новее, Docker, containerlab 0.78 или новее, 4 ГБ свободной
памяти. На macOS containerlab не работает, ему нужны сетевые вызовы ядра Linux.

## Установка

```shell
curl -sL https://containerlab.dev/setup | sudo -E bash -s "all"
```

Скрипт ставит Docker и containerlab. Если apt-репозиторий containerlab недоступен,
пакет берётся с GitHub:

```shell
curl -sLO https://github.com/srl-labs/containerlab/releases/latest/download/containerlab_0.78.0_linux_arm64.deb
sudo dpkg -i containerlab_0.78.0_linux_arm64.deb
```

## Запуск

```shell
sudo containerlab deploy -t netmap.clab.yml
```

Остановить и удалить: `sudo containerlab destroy -t netmap.clab.yml`
Посмотреть, что запущено: `sudo containerlab inspect -a`

После перезагрузки хоста контейнеры SR Linux падают по кругу: их сетевое окружение
создаётся при развёртывании и вместе с хостом пропадает. Лечится пересозданием
стенда, то есть destroy и deploy.

## Включить интерфейсы

Интерфейсы на SR Linux по умолчанию выключены, и пока они выключены, LLDP молчит
и соседей не видно. После каждого развёртывания:

```shell
for ip in 172.20.20.11 172.20.20.12 172.20.20.13; do
  printf 'enter candidate
set / interface ethernet-1/1 admin-state enable
set / interface ethernet-1/2 admin-state enable
set / interface ethernet-1/3 admin-state enable
commit now
quit
' | sshpass -p 'NokiaSrl1!' ssh -o StrictHostKeyChecking=no admin@$ip
done
```

Сам LLDP включать не надо, на SR Linux он работает из коробки.

Проверка:

```shell
sshpass -p 'NokiaSrl1!' ssh admin@172.20.20.11 'show system lldp neighbor'
```

Должно показать acc1 на порту `ethernet-1/1` и acc2 на `ethernet-1/2`.

## Особенности, которые влияют на код

**LLDP отдаёт соседей и по интерфейсу `mgmt0`.** Все устройства стоят в одной сети
управления и видят там друг друга. Без фильтрации карта превращается в сетку, где
каждый соединён с каждым. Физические линки это только `ethernet-*`.

**SR Linux не принимает несколько команд через `;`.** Команды подаются потоком
на вход, по одной в строке.

**MAC-адреса назначаются вручную**, из диапазона Nokia `90:EC:E3` по реестру IEEE.
Делается это в `netmap.clab.yml` через `exec`. По умолчанию контейнер получает адрес
Docker с локальным префиксом `02:42`, а по такому адресу производителя не определить.
На живом железе адрес вендорский, так что без этой правки стенд вёл бы себя не как
настоящая сеть.

## Если ничего не скачивается

```shell
getent ahostsv4 ghcr.io
```

Адреса вида `0.0.31.x` или `fd00:` означают, что DNS перехватывает прокси на хосте.
Трафик виртуальной машины идёт от процесса `vmnet-natd`, его надо пустить напрямую,
мимо прокси.

## Выводы команд

В папке `samples/` лежат настоящие выводы, снятые с работающего устройства.
Парсеры пишутся по ним, поднимать стенд для этого не нужно.
