#!/usr/bin/env bash
# Install cherryfold for local use: venv + editable install + PATH symlink.
# Usage: ./install.sh [target-bin-dir]   (default ~/.local/bin)
# (For end users, `pipx install cherryfold` is the recommended path once published.)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

[ -x "$here/.venv/bin/python" ] || python3 -m venv "$here/.venv"
echo "Installing cherryfold (editable)…"
"$here/.venv/bin/pip" -q install -e "$here"

target="${1:-$HOME/.local/bin}"
mkdir -p "$target"
ln -sf "$here/.venv/bin/cherryfold" "$target/cherryfold"
echo "Linked $target/cherryfold"

case ":$PATH:" in
  *":$target:"*) echo "Ready. From any shell:  cherryfold follow" ;;
  *) echo "Add $target to PATH (e.g. in ~/.zshrc):  export PATH=\"$target:\$PATH\"" ;;
esac
