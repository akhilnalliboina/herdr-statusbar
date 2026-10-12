#!/bin/sh
# Herdr launches manifest commands from the plugin root. No build step needed.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=${HERDR_STATUSBAR_PYTHON:-python3}
command -v "$python" >/dev/null 2>&1 || {
  printf 'herdr-statusbar requires Python 3.11+. Install python3 first.\n' >&2
  exit 1
}
exec "$python" "$root/cli.py" "$@"
