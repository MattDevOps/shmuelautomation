"""Sanity tests for deploy/bootstrap.sh.

The script is destructive (creates GCP resources) so we don't actually
run it in tests. We do verify:
- it parses with bash -n
- it fails fast on missing env vars
- it covers each of the steps we promised in DEPLOY.md
- it is idempotent-by-design (each create is guarded by a describe check
  or uses an idempotent gcloud action)
"""
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "deploy" / "bootstrap.sh"


def test_script_exists_and_executable() -> None:
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK), "bootstrap.sh should be chmod +x"


def test_bash_syntax_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, f"syntax error: {result.stderr}"


def test_set_e_u_o_pipefail_present() -> None:
    """Without these flags a failing gcloud step would silently continue
    and we'd half-deploy. Lock them in."""
    text = SCRIPT.read_text()
    assert "set -euo pipefail" in text


def test_fails_fast_on_missing_required_env(tmp_path: Path) -> None:
    """Run the script with a clean env (no PROJECT_ID etc.) — it should
    exit non-zero before doing any gcloud work. Use HOME=tmp so it
    doesn't pick up backend/.env from the repo when CWD is preserved."""
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}
    # Run from a directory without a backend/.env to avoid auto-loading.
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "missing required env" in result.stderr


def test_covers_promised_steps() -> None:
    text = SCRIPT.read_text()
    # Each numbered step in the script's stdout corresponds to a section
    # we promised in DEPLOY.md. If a step disappears, this test fails so
    # we update the docs in the same change.
    expected_step_markers = [
        "1/8  Enable required APIs",
        "2/8  Artifact Registry repo",
        "3/8  Push secrets to Secret Manager",
        "4/8  Run alembic migrations against prod",
        "5/8  First Cloud Run deploy",
        "6/8  Map custom domain",
        "7/8  Service account + IAM roles",
        "8/8  Workload Identity Federation",
    ]
    for marker in expected_step_markers:
        assert marker in text, f"missing step: {marker}"


def test_idempotent_creates() -> None:
    """Every gcloud-create that would 409 on re-run is guarded with a
    describe check so the script can be re-run safely."""
    text = SCRIPT.read_text()
    creates_to_guard = [
        "gcloud artifacts repositories create",
        "gcloud iam service-accounts create",
        "gcloud iam workload-identity-pools create",
        "gcloud iam workload-identity-pools providers create-oidc",
        "gcloud beta run domain-mappings create",
    ]
    for cmd in creates_to_guard:
        idx = text.find(cmd)
        assert idx > 0, f"create command not found: {cmd}"
        # The 200 chars before the create should contain a describe check.
        preceding = text[max(0, idx - 200) : idx]
        assert "describe" in preceding, (
            f"unguarded create (no describe check before): {cmd}"
        )


def test_secrets_creation_handles_existing_secret() -> None:
    """For Secret Manager, the idempotent move is `versions add` if the
    secret exists, else `create`. The push_secret helper does that."""
    text = SCRIPT.read_text()
    assert "gcloud secrets versions add" in text
    assert "gcloud secrets create" in text
    assert "gcloud secrets describe" in text


def test_prints_github_secrets_at_the_end() -> None:
    """The whole point — operator copies these into the repo settings."""
    text = SCRIPT.read_text()
    for token in (
        "GCP_PROJECT_ID",
        "GCP_SERVICE_ACCOUNT",
        "GCP_WIF_PROVIDER",
        "DEPLOY_ENABLED",
    ):
        assert token in text, f"final printout missing: {token}"
