from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_offline_wrapper_uses_a_required_linux_network_namespace():
    wrapper = (ROOT / "scripts" / "run-without-network.sh").read_text()

    assert "unshare --net" in wrapper
    assert "ip link set lo up" in wrapper
    assert "SCANT_REQUIRE_NETWORK_NAMESPACE" in wrapper
    assert 'exec "$@"' in wrapper
