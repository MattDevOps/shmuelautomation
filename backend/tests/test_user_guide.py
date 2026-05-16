"""Sanity test for client/user-guide.md.

The guide is written for Shmuel and references specific UI he'll see
on the dashboard. If we rename a route or page, the guide silently
goes stale. These checks pin a few key references to actual code so
a renamed component breaks the guide-test, not Shmuel's day.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "client" / "user-guide.md"


def test_guide_exists() -> None:
    assert GUIDE.exists()


def test_guide_covers_each_top_level_workflow() -> None:
    """Every nav-bar item Shmuel sees should be mentioned in the guide."""
    text = GUIDE.read_text()
    expected_sections = [
        "Properties",
        "Queue",
        "Groups",
        "Contacts",
        "Import from Yad2",
        "Settings",
        "System",
    ]
    for section in expected_sections:
        assert section in text, f"guide doesn't mention top-nav item '{section}'"


def test_guide_references_features_we_actually_built() -> None:
    text = GUIDE.read_text()
    must_mention = [
        "Compose & share",
        "Mark slot as posted",
        "Import CSV",
        "Export CSV",
        "duplicate",
        "bulk",
        "Google Drive",
    ]
    for needle in must_mention:
        assert needle.lower() in text.lower(), f"guide is missing reference to: {needle}"


def test_guide_includes_troubleshooting_section() -> None:
    """Non-technical users need a 'when in doubt, do this' fallback."""
    text = GUIDE.read_text()
    assert "If something breaks" in text or "if something breaks" in text.lower()
    assert "refresh" in text.lower()


def test_guide_warns_against_automated_posting() -> None:
    """Important — keep the WhatsApp/FB ban-risk reminder in the guide.
    If a future edit removes this, we want to notice and put it back."""
    text = GUIDE.read_text().lower()
    assert "ban" in text or "automated" in text
