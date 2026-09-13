from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def workflow_text() -> str:
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text()


def test_offline_wrapper_uses_a_required_linux_network_namespace():
    wrapper = (ROOT / "scripts" / "run-without-network.sh").read_text()

    assert "unshare --net" in wrapper
    assert "ip link set lo up" in wrapper
    assert "SCANT_REQUIRE_NETWORK_NAMESPACE" in wrapper
    assert 'exec "$@"' in wrapper


def test_ci_runs_every_release_gate_without_application_secrets():
    workflow = workflow_text()
    for command in (
        "bash scripts/check-secrets.sh",
        "scripts/run-without-network.sh python -m pytest -q",
        "scripts/run-without-network.sh npm test",
        "scripts/run-without-network.sh npm run typecheck",
        "scripts/run-without-network.sh npm run lint",
        "scripts/run-without-network.sh npm run build",
        "tests/test_alembic_postgresql.py",
        "alembic check",
    ):
        assert command in workflow
    assert "pull_request_target" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "OPENAI_API_KEY" not in workflow


def test_ci_uses_current_pinned_major_actions_and_read_only_checkout():
    workflow = workflow_text()

    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "actions/setup-node@v7" in workflow
    assert workflow.count("persist-credentials: false") == 4
    assert "SCANT_REQUIRE_NETWORK_NAMESPACE: \"1\"" in workflow
