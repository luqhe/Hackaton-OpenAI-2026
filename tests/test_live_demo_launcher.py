from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run-live-demo.sh"


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def run_launcher(
    tmp_path: Path,
    *,
    help_output: str = "{demo,poll}",
    live_exit_code: int = 0,
    curl_exit_code: int = 0,
) -> tuple[subprocess.CompletedProcess[str], str]:
    project = tmp_path / "project"
    scripts = project / "scripts"
    virtualenv_bin = project / ".venv" / "bin"
    command_bin = tmp_path / "bin"
    scripts.mkdir(parents=True)
    virtualenv_bin.mkdir(parents=True)
    command_bin.mkdir()

    shutil.copy2(LAUNCHER, scripts / LAUNCHER.name)

    live_error = "printf 'live-demo-error\\n' >&2\n" if live_exit_code else ""
    write_executable(
        virtualenv_bin / "python",
        f"""#!/usr/bin/env bash
if [[ "$*" == "-m agent.main --help" ]]; then
  printf '%s\\n' '{help_output}'
  exit 0
fi
if [[ "$*" != "-m agent.main live-demo --controlled-demo --wait-for-unlock" ]]; then
  printf 'unexpected agent arguments: %s\\n' "$*" >&2
  exit 64
fi
printf 'source=OPENAI\\n'
{live_error}exit {live_exit_code}
""",
    )
    write_executable(
        scripts / "run-demo.sh",
        "#!/usr/bin/env bash\nprintf 'fixture-run\\n'\n",
    )
    write_executable(
        command_bin / "curl",
        "#!/usr/bin/env bash\n"
        + ("printf 'api-error\\n' >&2\n" if curl_exit_code else "")
        + f"exit {curl_exit_code}\n",
    )
    write_executable(
        command_bin / "open",
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$1" > "$OPEN_LOG"\n',
    )

    open_log = tmp_path / "opened-url.txt"
    environment = os.environ.copy()
    environment["OPEN_LOG"] = str(open_log)
    environment["PATH"] = f"{command_bin}:/usr/bin:/bin"
    result = subprocess.run(
        ["/bin/bash", str(scripts / LAUNCHER.name)],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    opened_url = open_log.read_text(encoding="utf-8").strip() if open_log.exists() else ""
    return result, opened_url


def test_launcher_uses_local_fixture_when_live_demo_is_unavailable(tmp_path: Path) -> None:
    result, opened_url = run_launcher(tmp_path)

    assert result.returncode == 0
    assert "source=LOCAL_FIXTURE" in result.stdout
    assert "fixture-run" in result.stdout
    assert opened_url == "http://127.0.0.1:8000/demo-chat"


def test_launcher_reports_live_failure_before_fixture_fallback(tmp_path: Path) -> None:
    result, _ = run_launcher(tmp_path, help_output="{demo,live-demo,poll}", live_exit_code=17)

    assert result.returncode == 0
    assert "live-demo-error" in result.stderr
    assert "source=FIXTURE_FALLBACK" in result.stdout
    assert "fixture-run" in result.stdout


def test_launcher_preserves_the_optional_live_demo_source(tmp_path: Path) -> None:
    result, _ = run_launcher(tmp_path, help_output="{demo,live-demo,poll}")

    assert result.returncode == 0
    assert "mode=OPTIONAL_LIVE_DEMO" in result.stdout
    assert "source=OPENAI" in result.stdout
    assert "source=LOCAL_LIVE_DEMO" not in result.stdout
    assert "fixture-run" not in result.stdout


def test_launcher_stops_when_the_local_api_is_unavailable(tmp_path: Path) -> None:
    result, opened_url = run_launcher(tmp_path, curl_exit_code=7)

    assert result.returncode != 0
    assert "api-error" in result.stderr
    assert "127.0.0.1:8000" in result.stderr
    assert "source=" not in result.stdout
    assert "fixture-run" not in result.stdout
    assert opened_url == ""
