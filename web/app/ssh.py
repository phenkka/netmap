import paramiko

TIMEOUT = 20

# управляющий процессор коммутатора плохо переносит наплыв сессий, поэтому
# опрос идёт пачками. по одному 250 устройств обходились бы минутами
AT_ONCE = 16


class SshError(Exception):
    pass


def run(ip: str, username: str, password: str, command: str) -> str:
    client = _client(ip, username, password)
    try:
        _, stdout, stderr = client.exec_command(command, timeout=TIMEOUT)
        return stdout.read().decode("utf-8", "replace") + stderr.read().decode(
            "utf-8", "replace"
        )
    finally:
        client.close()


def run_lines(ip: str, username: str, password: str, lines: list[str]) -> str:
    # SR Linux не принимает несколько команд одной строкой
    client = _client(ip, username, password)
    try:
        stdin, stdout, stderr = client.exec_command("", timeout=TIMEOUT)
        stdin.write("\n".join(lines) + "\n")
        stdin.flush()
        stdin.channel.shutdown_write()
        return stdout.read().decode("utf-8", "replace") + stderr.read().decode(
            "utf-8", "replace"
        )
    finally:
        client.close()


def shell(ip: str, username: str, password: str, cols: int = 120, rows: int = 30):
    client = _client(ip, username, password)
    channel = client.invoke_shell(term="xterm-256color", width=cols, height=rows)
    channel.settimeout(0.0)
    return client, channel


def _client(ip: str, username: str, password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip,
            username=username,
            password=password,
            timeout=TIMEOUT,
            banner_timeout=TIMEOUT,
            auth_timeout=TIMEOUT,
            allow_agent=False,
            look_for_keys=False,
        )
    except paramiko.AuthenticationException:
        raise SshError("неверный логин или пароль")
    except Exception as exc:
        raise SshError(str(exc))
    return client
