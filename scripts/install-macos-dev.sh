#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package_root="${GUARDIAN_PACKAGE_DIR:-$project_root/.dist/guardian-dev}"
launch_agents_dir="${HOME:?}/Library/LaunchAgents"
guardian_data_dir="${HOME:?}/Library/Application Support/Guardian"
target_plist="$launch_agents_dir/com.guardian.agent.plist"
template_plist="$project_root/packaging/macos/com.guardian.agent.plist"
service_target="gui/$UID/com.guardian.agent"

if [[ "$(uname -s)" != "Darwin" ]]; then
  printf 'Guardian LaunchAgent installation requires macOS.\n' >&2
  exit 2
fi
if [[ ! -x "$package_root/bin/guardian-agent" ]]; then
  printf 'Build the development package first: scripts/package-macos.sh\n' >&2
  exit 2
fi

mkdir -p "$launch_agents_dir" "$guardian_data_dir"
install -m 0644 "$template_plist" "$target_plist"
plutil -replace ProgramArguments.0 -string "$package_root/bin/guardian-agent" "$target_plist"
plutil -replace ProgramArguments.3 -string "$guardian_data_dir/blocked-apps.json" "$target_plist"
plutil -replace ProgramArguments.5 -string "$guardian_data_dir/runtime-state.json" "$target_plist"
plutil -replace ProgramArguments.7 -string "$guardian_data_dir/outbox.json" "$target_plist"
plutil -replace StandardOutPath -string "$guardian_data_dir/agent.stdout.log" "$target_plist"
plutil -replace StandardErrorPath -string "$guardian_data_dir/agent.stderr.log" "$target_plist"
plutil -lint "$target_plist"

launchctl bootout "gui/$UID" "$target_plist" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$target_plist"
launchctl enable "$service_target"
launchctl kickstart -k "$service_target"
printf 'Guardian LaunchAgent installed: %s\n' "$target_plist"
