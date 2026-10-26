#!/usr/bin/env bash
# Convenience launcher for Ubuntu/Linux and macOS: creates a venv on first run, then starts the app.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python -m lyricpip "$@"
