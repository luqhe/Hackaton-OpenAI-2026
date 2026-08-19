from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_macos_package_script_builds_isolated_agent_and_helper() -> None:
    script = (PROJECT_ROOT / "scripts" / "package-macos.sh").read_text(encoding="utf-8")
    launcher = (PROJECT_ROOT / "packaging" / "macos" / "guardian-agent").read_text(encoding="utf-8")

    assert '[[ "$(uname -s)" != "Darwin" ]]' in script
    assert '"$project_root"/.dist/*' in script
    assert "swift build" in script
    assert "--configuration release" in script
    assert 'python3 -m venv "$package_root/python"' in script
    assert 'pip install --disable-pip-version-check "$project_root"' in script
    assert 'exec "$bundle_root/python/bin/python" -m agent.main "$@"' in launcher


def test_launch_agent_starts_after_login_and_is_kept_alive() -> None:
    plist = (PROJECT_ROOT / "packaging" / "macos" / "com.guardian.agent.plist").read_text(encoding="utf-8")
    installer = (PROJECT_ROOT / "scripts" / "install-macos-dev.sh").read_text(encoding="utf-8")

    assert "<key>RunAtLoad</key>" in plist
    assert "<key>KeepAlive</key>" in plist
    assert "<string>observe</string>" in plist
    assert "--runtime-state-path" in plist
    assert 'launchctl bootstrap "gui/$UID" "$target_plist"' in installer
    assert 'launchctl enable "$service_target"' in installer
    assert 'launchctl kickstart -k "$service_target"' in installer
    assert 'plutil -lint "$target_plist"' in installer
