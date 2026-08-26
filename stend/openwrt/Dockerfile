# OpenWrt как точка доступа стенда.
#
# Сервер SSH в образе уже есть, это dropbear. Доставляется lldpd, без него
# устройство видно на карте, но без связей.
#
# Командной строки в духе show у OpenWrt нет и не было: система настраивается
# через uci, а сведения о себе отдаёт через ubus. Драйвер продукта обращается
# именно к ним, а не к выдуманным командам.
#
# Узел занимает единицы мегабайт памяти.

FROM openwrt/rootfs:latest

# chpasswd в busybox нет, а passwd спрашивает пароль с терминала, поэтому
# хеш пароля Lab12345! кладётся в shadow напрямую. Стенд, пароль открытый
RUN mkdir -p /var/lock \
    && apk update \
    && apk add lldpd \
    && sed -i 's|^root:[^:]*:|root:$1$R0Y9SfIi$wzQARDdcFdfDd5vRTerZM/:|' /etc/shadow

COPY start /usr/local/bin/start
RUN chmod +x /usr/local/bin/start

ENTRYPOINT ["/usr/local/bin/start"]
