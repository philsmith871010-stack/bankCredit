#!/usr/bin/env bash
# Start the local development server for the Counterparty site. The first run creates .venv and
# installs the requirements; every run then builds the site, serves it on
# http://localhost:8000/bankCredit/, rebuilds on every edit and reloads the browser.
#
#   bash tools/dev.sh             serve, rebuild, reload
#   bash tools/dev.sh --open      the same, and open the browser
#   bash tools/dev.sh --once      build into site/ for the browser tests, then exit
#
# Everything after the script name goes to tools/dev.py; see its docstring for the rest.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  # The pipeline runs Python 3.11, so prefer a recent one over an old system python3.
  py=""
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then py="$c"; break; fi
  done
  [ -n "$py" ] || { echo "no python3 found; install one (brew install python@3.12) and run this again" >&2; exit 1; }
  echo "-- first run: creating .venv with $("$py" --version) and installing the requirements"
  "$py" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi
if ! .venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "!! .venv runs $(.venv/bin/python --version); the pipeline uses 3.11. If the build fails," >&2
  echo "!! install a newer Python (brew install python@3.12), delete .venv and run this again." >&2
fi
exec .venv/bin/python tools/dev.py "$@"
