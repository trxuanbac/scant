import socket

import pytest

from support.network_guard import NetworkAccessBlocked


@pytest.mark.unit
def test_test_taxonomy_is_registered(pytestconfig):
    registered = "\n".join(pytestconfig.getini("markers"))
    for marker in ("unit", "integration", "browser", "live"):
        assert f"{marker}:" in registered
    assert isinstance(pytestconfig.getoption("--run-live"), bool)


@pytest.mark.unit
def test_default_suite_blocks_dns_access():
    with pytest.raises(NetworkAccessBlocked, match="example.com"):
        socket.getaddrinfo("example.com", 443)


@pytest.mark.unit
def test_default_suite_blocks_tcp_access():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkAccessBlocked, match="93.184.216.34:443"):
            sock.connect(("93.184.216.34", 443))
    finally:
        sock.close()


@pytest.mark.unit
def test_default_suite_blocks_udp_access():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(NetworkAccessBlocked, match="127.0.0.1:9"):
            sock.sendto(b"blocked", ("127.0.0.1", 9))
    finally:
        sock.close()


@pytest.mark.live
def test_live_marker_sentinel():
    assert True
