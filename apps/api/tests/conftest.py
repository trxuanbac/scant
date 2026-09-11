import pytest

from support.network_guard import install_network_guard


def pytest_addoption(parser):
    group = parser.getgroup("scant-live")
    group.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that require external network or configured services",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skipped = pytest.mark.skip(
        reason="live test disabled; rerun with --run-live and required services configured"
    )
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skipped)


@pytest.fixture(autouse=True)
def block_network_in_deterministic_tests(request, monkeypatch):
    is_live = request.node.get_closest_marker("live") is not None
    if is_live and request.config.getoption("--run-live"):
        return
    install_network_guard(monkeypatch)
