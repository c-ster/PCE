#!/usr/bin/env bash
# Personal Context Engine — installer.
#
# Deliberately not a `curl | bash` one-liner: this is a privacy/security
# tool, so you should be able to read what you're about to run before you
# run it. Download or clone the repo, then run this script from inside it:
#
#   ./install.sh
#
# All it does: find a Python 3.12+ interpreter, create an isolated virtual
# environment in ./.venv, and install PCE into it. It does not touch
# anything outside this repo folder until you later run `pce init`, which
# creates ~/.pce (or wherever $PCE_HOME points).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "Personal Context Engine — installer"
echo "Working directory: $REPO_DIR"
echo

# 1. Find a Python 3.12+ interpreter.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        major="${version%%.*}"
        minor="${version##*.}"
        if [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Couldn't find Python 3.12 or newer on this machine."
    echo "Install it from https://www.python.org/downloads/ and run this script again."
    exit 1
fi

echo "Using $("$PYTHON_BIN" --version) at $(command -v "$PYTHON_BIN")"

# 2. Create an isolated virtual environment (doesn't touch your system Python).
if [ ! -d ".venv" ]; then
    echo "Creating a virtual environment in .venv ..."
    "$PYTHON_BIN" -m venv .venv
else
    echo ".venv already exists — reusing it."
fi

# 3. Install PCE into it.
echo "Installing Personal Context Engine ..."
".venv/bin/pip" install --quiet --upgrade pip
".venv/bin/pip" install --quiet -e .

# 4. Verify the 'pce' command actually works, retrying with a compatibility
# mode if the first attempt produced a broken console script (a known
# quirk on some Python installs).
if ! ".venv/bin/pce" --version >/dev/null 2>&1; then
    echo "First install attempt didn't produce a working 'pce' command; retrying ..."
    ".venv/bin/pip" install --quiet -e . --config-settings editable_mode=compat
fi

if ".venv/bin/pce" --version >/dev/null 2>&1; then
    echo
    echo "Install verified."
else
    echo
    echo "Something went wrong — 'pce' isn't runnable after install."
    echo "Please open an issue: https://github.com/c-ster/PCE/issues"
    exit 1
fi

echo
echo "Done! To start using PCE, open a terminal in this folder and run:"
echo
echo "    source .venv/bin/activate"
echo "    pce init"
echo
echo "Then see docs/GETTING_STARTED.md for what to do next."
