#!/bin/bash
# Wrapper to run RISU MCP server with venv
cd "$(dirname "$0")"
exec ./venv/bin/python3 server.py "$@"

