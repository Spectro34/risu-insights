#!/bin/bash
# Fix venv activation - recreate it pointing to current directory
cd "$(dirname "$0")"
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
echo "✓ Virtual environment recreated and package installed"
