"""Sanity checks on .github/workflows/deploy-backend.yml.

Without a CI/CD test, a typo in a workflow only surfaces when we push
to main. These tests pin the contract: workflow file exists, parses,
gates on DEPLOY_ENABLED, runs the right key steps, references the
secrets we expect, and uses the same Dockerfile we expect.
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-backend.yml"


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_file_exists() -> None:
    assert WORKFLOW.exists()


def test_workflow_yaml_parses() -> None:
    doc = _load()
    assert isinstance(doc, dict)
    assert doc.get("name") == "Deploy backend (Cloud Run)"


def test_triggers_are_main_push_and_dispatch() -> None:
    # PyYAML parses the bare key `on:` as the boolean True (YAML 1.1's
    # 'on' is a yes/no keyword), so check both spellings.
    doc = _load()
    triggers = doc.get("on") or doc.get(True)
    assert triggers is not None, "workflow has no triggers"
    assert "workflow_dispatch" in triggers
    assert "push" in triggers
    assert triggers["push"]["branches"] == ["main"]


def test_deploy_job_is_gated_on_repo_variable() -> None:
    """Until DEPLOY_ENABLED='true' is set, the deploy job is a no-op so
    every push to main doesn't error before GCP is provisioned."""
    doc = _load()
    job = doc["jobs"]["deploy"]
    assert "vars.DEPLOY_ENABLED" in job["if"]


def test_workload_identity_federation_used_not_json_keys() -> None:
    """We auth via WIF, not via a service-account JSON key — that's the
    documented best practice and avoids long-lived credentials in repo
    secrets. If someone refactors to a key-based auth, this test fails
    so we catch it in review."""
    doc = _load()
    steps = doc["jobs"]["deploy"]["steps"]
    auth_steps = [s for s in steps if "google-github-actions/auth" in s.get("uses", "")]
    assert auth_steps, "no GCP auth step found"
    # WIF auth uses workload_identity_provider; key-based auth uses credentials_json.
    auth_with = auth_steps[0]["with"]
    assert "workload_identity_provider" in auth_with
    assert "credentials_json" not in auth_with


def test_required_steps_present() -> None:
    doc = _load()
    step_names = [s.get("name", "") for s in doc["jobs"]["deploy"]["steps"]]
    must_have = [
        "Authenticate to Google Cloud",
        "Build and push image",
        "Run database migrations",
        "Deploy to Cloud Run",
        "Smoke-test the new revision",
    ]
    for name in must_have:
        assert name in step_names, f"missing required step: {name!r}"


def test_id_token_permission_is_granted() -> None:
    """WIF requires id-token: write at the job level. Forgetting this
    is the #1 cause of 'failed to fetch token' errors."""
    doc = _load()
    perms = doc["jobs"]["deploy"]["permissions"]
    assert perms.get("id-token") == "write"


def test_concurrency_does_not_cancel_inflight_deploys() -> None:
    """An in-flight prod deploy should run to completion, not be killed
    by a newer push. Cancelling mid-rollout can leave Cloud Run in a
    weird state."""
    doc = _load()
    concurrency = doc.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is False


def test_dockerfile_referenced_exists() -> None:
    """The workflow builds backend/ — make sure the Dockerfile is there."""
    assert (REPO_ROOT / "backend" / "Dockerfile").exists()
    assert (REPO_ROOT / "backend" / ".dockerignore").exists()
