#!/bin/bash
set -e
cd "$(dirname "$0")"
# Prefer stable Python 3.12 / 3.13 over 3.14 when available.
PYTHON=""
for exe in python3.12 python3.13 python3.11 python3.14 python3; do
  if command -v "$exe" >/dev/null 2>&1 && "$exe" -c 'import sys; assert (3,11)<=sys.version_info[:2]<(3,15)' 2>/dev/null; then PYTHON="$exe";break; fi
done
if [ -z "$PYTHON" ]; then echo 'Python 3.11+ belum ditemukan. Install Python 3.12 dari python.org'; exit 1;fi
echo "Using: $($PYTHON --version) via $(command -v "$PYTHON")"
if [ -d .venv ];then
  if ! .venv/bin/python -c 'import sys; assert (3,11)<=sys.version_info[:2]<(3,15)' 2>/dev/null;then
    echo 'Environment lama tidak cocok. Hapus hanya folder .venv lalu jalankan ulang.';exit 1
  fi
else
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
APP_MODE=local .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
