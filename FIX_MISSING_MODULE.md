# Groundhaus V2.7 — Fix missing modules on VPS

Error: `ModuleNotFoundError: No module named 'reservation_master'`.

The required files `reservation_master.py` and `stay_allocation.py` must exist in the root of the GitHub repository alongside `app.py`. The Dockerfile must copy both modules into `/app`.

This package corrects the V2.7 Dockerfile to use:

```dockerfile
COPY app.py store.py reporting.py engine.py owner_exports.py reservation_master.py stay_allocation.py ./
```

## Update on GitHub

Upload `reservation_master.py`, `stay_allocation.py`, `Dockerfile` from this package to repository root; also check that the other V2.7 files are in sync (`app.py`, `store.py`, `engine.py`, `owner_exports.py`, `reporting.py`, `requirements.txt`). Commit to main.

## On Ubuntu VPS

```bash
cd /home/ubuntu/groundhaus-reporting
git status --short
git pull --ff-only origin main
ls -l reservation_master.py stay_allocation.py Dockerfile
python3 -m py_compile app.py reservation_master.py stay_allocation.py
sudo docker compose -f compose.yaml -f compose.host.yaml build --no-cache app
sudo docker compose -f compose.yaml -f compose.host.yaml up -d --no-deps app
sudo docker compose -f compose.yaml -f compose.host.yaml exec -T app python -c 'import reservation_master, stay_allocation; print("Both modules available")'
```

Do not use `docker compose down -v`, delete Docker volumes, or reset data. This update only changes application files. Caddy on Ubuntu stays untouched.
