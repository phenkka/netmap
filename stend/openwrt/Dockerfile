FROM openwrt/rootfs:latest

RUN mkdir -p /var/lock \
    && apk update \
    && apk add lldpd \
    && sed -i 's|^root:[^:]*:|root:$1$R0Y9SfIi$wzQARDdcFdfDd5vRTerZM/:|' /etc/shadow

COPY start /usr/local/bin/start
COPY lldp /usr/local/bin/lldp
RUN chmod +x /usr/local/bin/start /usr/local/bin/lldp

ENTRYPOINT ["/usr/local/bin/start"]
