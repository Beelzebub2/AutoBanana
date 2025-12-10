#!/usr/bin/env bash
set -e

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it and ensure it's on your PATH."
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

python3 AutoBanana.py
