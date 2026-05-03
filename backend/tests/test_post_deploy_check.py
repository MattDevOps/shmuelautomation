"""Sanity tests for deploy/post-deploy-check.sh.

The script can't be run end-to-end in CI (it hits prod URLs), so we
just verify it's well-formed and exercises each layer once.
"""
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "deploy" / "post-deploy-check.sh"


def test_exists_and_executable() -> None:
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)


def test_bash_syntax_valid() -> None:
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_covers_each_layer() -> None:
    """Backend, admin SPA, WordPress public site — at least one check
    against each. If a whole layer is dropped, this catches it."""
    text = SCRIPT.read_text()
    assert "API=" in text and "/health" in text
    assert "ADMIN=" in text
    assert "PUBLIC_SITE=" in text
    assert "cjl-listing" in text  # plugin output marker


def test_only_uses_GET_requests() -> None:
    """Smoke checks must be non-destructive. Fail if anyone adds a
    POST/PUT/DELETE to this file by accident."""
    text = SCRIPT.read_text()
    for forbidden in (' -X POST', ' -X PUT', ' -X DELETE', ' -X PATCH'):
        assert forbidden not in text, f"non-GET request found: {forbidden}"


def test_exits_nonzero_when_any_check_fails() -> None:
    """Without a non-zero exit on failure, CI/cron jobs would silently
    accept a broken prod."""
    text = SCRIPT.read_text()
    assert "exit $(( fail > 0 ? 1 : 0 ))" in text
