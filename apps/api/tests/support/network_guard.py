import socket
from typing import Any


class NetworkAccessBlocked(RuntimeError):
    """Raised when a deterministic test attempts external network access."""


def _destination(address: Any) -> str:
    if isinstance(address, tuple) and len(address) >= 2:
        return f"{address[0]}:{address[1]}"
    return str(address)


def install_network_guard(monkeypatch) -> None:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto
    unix_family = getattr(socket, "AF_UNIX", None)

    def guarded_connect(sock, address):
        if unix_family is not None and sock.family == unix_family:
            return original_connect(sock, address)
        raise NetworkAccessBlocked(
            f"Outbound network is disabled in deterministic tests: {_destination(address)}"
        )

    def guarded_connect_ex(sock, address):
        if unix_family is not None and sock.family == unix_family:
            return original_connect_ex(sock, address)
        raise NetworkAccessBlocked(
            f"Outbound network is disabled in deterministic tests: {_destination(address)}"
        )

    def guarded_sendto(sock, data, *args):
        address = args[-1] if args else "<unknown>"
        if unix_family is not None and sock.family == unix_family:
            return original_sendto(sock, data, *args)
        raise NetworkAccessBlocked(
            f"Outbound network is disabled in deterministic tests: {_destination(address)}"
        )

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        raise NetworkAccessBlocked(
            f"Outbound DNS is disabled in deterministic tests: {host}:{port}"
        )

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
