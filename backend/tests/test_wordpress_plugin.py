"""Sanity checks for the WordPress plugin in /wordpress-plugin/.

The plugin is PHP and we don't have a PHP toolchain in this repo, so
these tests focus on what we *can* verify in Python: the file is
present, declares the expected plugin headers, registers the shortcode
+ settings page, and the build script produces a structurally valid
.zip ready for upload.
"""
import subprocess
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "wordpress-plugin" / "classic-jerusalem-listings"
MAIN_PHP = PLUGIN_DIR / "classic-jerusalem-listings.php"
BUILD_SCRIPT = REPO_ROOT / "wordpress-plugin" / "build.sh"


def test_main_plugin_file_exists() -> None:
    assert MAIN_PHP.exists(), f"missing {MAIN_PHP}"


def test_plugin_headers_present() -> None:
    """WordPress requires a specific header block to recognize a plugin
    on upload — without these, the .zip is silently ignored."""
    text = MAIN_PHP.read_text()
    for header in ("Plugin Name:", "Version:", "Requires PHP:"):
        assert header in text, f"plugin file is missing the '{header}' header"


def test_shortcode_registered() -> None:
    text = MAIN_PHP.read_text()
    assert "add_shortcode('classic_listings'" in text or 'add_shortcode("classic_listings"' in text


def test_settings_page_registered() -> None:
    text = MAIN_PHP.read_text()
    assert "add_options_page" in text
    assert "register_setting" in text


def test_php_brackets_balanced() -> None:
    """Coarse syntax check — catches dropped braces. Not a substitute
    for `php -l` but good enough to spot a busted commit. Raw count
    works because we don't have any brace characters inside string
    literals in this plugin (and if we add one, this test will fail
    and we'll fix it explicitly rather than build a real PHP parser)."""
    text = MAIN_PHP.read_text()
    assert text.count("{") == text.count("}"), (
        f"unbalanced curly braces: {text.count('{')} '{{' vs {text.count('}')} '}}'"
    )


def test_readme_txt_present() -> None:
    """WordPress.org reads readme.txt for plugin metadata. Even when not
    publishing to the directory, having one is a small affordance."""
    readme = PLUGIN_DIR / "readme.txt"
    assert readme.exists()
    text = readme.read_text()
    assert "Stable tag:" in text
    assert "[classic_listings]" in text or "classic_listings" in text


def test_build_script_produces_valid_zip(tmp_path: Path) -> None:
    """Running build.sh writes a zip to wordpress-plugin/dist/. Verify
    its structure: must contain <slug>/<slug>.php and <slug>/readme.txt."""
    result = subprocess.run(
        ["bash", str(BUILD_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"build failed: {result.stderr}"

    dist = REPO_ROOT / "wordpress-plugin" / "dist"
    zips = sorted(dist.glob("classic-jerusalem-listings-*.zip"))
    assert zips, "build script produced no zip file"
    latest = zips[-1]

    with zipfile.ZipFile(latest) as zf:
        names = zf.namelist()
    # WP requires the zip to extract into a single top-level dir matching
    # the plugin slug. Verify both expected files are inside that dir.
    assert "classic-jerusalem-listings/classic-jerusalem-listings.php" in names
    assert "classic-jerusalem-listings/readme.txt" in names
    # And nothing scary leaked in:
    for n in names:
        assert "/.git/" not in n, f".git file leaked into zip: {n}"
        assert not n.endswith(".swp"), f"editor swap file leaked: {n}"
