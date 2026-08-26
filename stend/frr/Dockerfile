FROM quay.io/frrouting/frr:10.7.1

RUN apk add --no-cache openssh-server lldpd \
    && ssh-keygen -A \
    && adduser -D admin \
    && echo 'admin:Lab12345!' | chpasswd \
    && addgroup admin frr \
    && addgroup admin frrvty \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config \
    && printf 'service integrated-vtysh-config\n' > /etc/frr/vtysh.conf \
    && chown frr:frr /etc/frr/vtysh.conf

COPY start /usr/local/bin/start
COPY lldp /usr/local/bin/lldp
RUN chmod +x /usr/local/bin/start /usr/local/bin/lldp

ENTRYPOINT ["/usr/local/bin/start"]
