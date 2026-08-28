#!/usr/bin/env bash
#
# Cloud Agent install script for Space Engineers Block Exchanger.
# Idempotent: safe to re-run against cached/partial state.
set -euo pipefail

# The CustomTkinter GUI depends on the standard-library `tkinter`, whose native
# `_tkinter` module ships in the system `python3-tk` package (absent from the
# default base image). Install it at the system level so both the system
# interpreter and any venv can import tkinter.
sudo apt-get update
sudo apt-get install -y --no-install-recommends python3-tk

# System site-packages is read-only for the runtime user, so install the
# application and development dependencies into the per-user site.
python3 -m pip install --user --no-warn-script-location -r requirements.txt

# Development tooling used by CI (lint, type-check, tests). Invoke via
# `python3 -m ruff|mypy|pytest` since ~/.local/bin is not on PATH by default.
python3 -m pip install --user --no-warn-script-location pytest ruff mypy
