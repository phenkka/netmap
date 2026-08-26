# FRRouting как маршрутизатор стенда.
#
# Базовый образ отдаёт только демоны маршрутизации, поэтому доставляются сервер
# SSH и lldpd. Своей командной оболочки поверх не строится: продукт обращается
# к устройству его же родными командами, vtysh для маршрутизации и конфигурации,
# lldpcli для соседей. Так же с этим стеком работают и настоящие сетевые ОС.
#
# Узел занимает около 12 МБ памяти против полутора гигабайт у Nokia SR Linux,
# что и позволяет держать на стенде больше устройств.

FROM frrouting/frr:latest

RUN apk add --no-cache openssh-server lldpd \
    && ssh-keygen -A \
    && adduser -D admin \
    && echo 'admin:Lab12345!' | chpasswd \
    && addgroup admin frr \
    && addgroup admin frrvty \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config \
    # без него vtysh ругается на каждую команду, хотя и выполняет её
    && printf 'service integrated-vtysh-config\n' > /etc/frr/vtysh.conf \
    && chown frr:frr /etc/frr/vtysh.conf

COPY start /usr/local/bin/start
RUN chmod +x /usr/local/bin/start

ENTRYPOINT ["/usr/local/bin/start"]
