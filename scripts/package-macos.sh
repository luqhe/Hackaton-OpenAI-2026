#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package_root="${GUARDIAN_PACKAGE_DIR:-$project_root/.dist/guardian-dev}"
swift_package="$project_root/native/GuardianCaptureHelper"

if [[ "$(uname -s)" != "Darwin" ]]; then
  printf 'Guardian macOS packaging requires macOS.\n' >&2
  exit 2
fi

case "$package_root" in
  "$project_root"/.dist/*) ;;
  *)
    printf 'GUARDIAN_PACKAGE_DIR must stay inside %s/.dist/.\n' "$project_root" >&2
    exit 2
    ;;
esac

rm -rf -- "$package_root"
mkdir -p "$package_root/bin" "$package_root/python"

swift build \
  --package-path "$swift_package" \
  --configuration release \
  --scratch-path "$package_root/swift-build"
install -m 0755 \
  "$package_root/swift-build/release/guardian-capture-helper" \
  "$package_root/bin/guardian-capture-helper"

python3 -m venv "$package_root/python"
"$package_root/python/bin/python" -m pip install --disable-pip-version-check "$project_root"
install -m 0755 "$project_root/packaging/macos/guardian-agent" "$package_root/bin/guardian-agent"

"$package_root/bin/guardian-capture-helper" permissions >/dev/null || true
"$package_root/bin/guardian-agent" --help >/dev/null
printf 'Guardian development bundle created at %s\n' "$package_root"
