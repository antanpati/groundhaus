# Groundhaus V2.7 — Safe VPS Upgrade

**Applies to:** Existing Ubuntu VPS running Streamlit in Docker, with HTTPS handled by host-installed Caddy.

**Do not** stop host Caddy, remove Tailscale, run `docker compose down -v`, delete volumes, or reset data.

## 1. Prepare GitHub first

Extract the `Groundhaus_V2_6_Patch.zip` locally. Upload these files to the root of your existing private repository (`antanpati/groundhaus`, branch `main`):

- app.py
- store.py
- engine.py
- owner_exports.py
- reservation_master.py (UPDATED)
- stay_allocation.py (NEW)
- Dockerfile
- README.md (optional)
- DEPLOY_UPGRADE.md (optional)

Keep existing `compose.yaml`, `compose.host.yaml`, `Caddyfile`, `.env`, and the entire Docker volume unchanged. The host Caddy already provides HTTPS. Check GitHub that all changed files are visible **before** updating VPS.

## 2. Make a verified backup on VPS

SSH into VPS. All commands below run in **VPS Ubuntu**, not Mac Terminal.

```bash
cd /home/ubuntu/groundhaus-reporting
mkdir -p "$HOME/groundhaus-backups"
chmod 700 "$HOME/groundhaus-backups"
sudo docker compose -f compose.yaml -f compose.host.yaml exec -T app python -c 'import store,sys;sys.stdout.buffer.write(store.backup_database())' > "$HOME/groundhaus-backups/before-v27.sqlite3"
chmod 600 "$HOME/groundhaus-backups/before-v27.sqlite3"
ls -lh "$HOME/groundhaus-backups/before-v27.sqlite3"
```

Do not continue if the backup is 0 bytes or the command fails. Copy the backup somewhere else securely when possible.

## 3. Update code and validate

```bash
cd /home/ubuntu/groundhaus-reporting
git status --short
git pull --ff-only origin main
python3 -m py_compile app.py store.py engine.py owner_exports.py reservation_master.py
```

If Git reports local edits/conflicts, stop and reconcile. Do not use `git reset --hard` without knowing what it overwrites.

## 4. Rebuild only the app, preserve database

```bash
sudo docker compose -f compose.yaml -f compose.host.yaml up -d --build --no-deps app
sudo docker compose -f compose.yaml -f compose.host.yaml ps app
sudo docker compose -f compose.yaml -f compose.host.yaml logs --tail=80 app
```

Host Caddy configuration does not change. Volume `groundhaus_data` remains mounted under `/app/app_data`.

## 5. Verify production carefully

- Open `https://reporting.groundhaus.co` and log in.
- Confirm old property mappings and expenses are still present.
- Import one Paid file again; identical rows should not be duplicated.
- Import Upcoming; check forecast remains separate from actual.
- Review a previously duplicated confirmation code and the negative Adjustment.
- Test Excel/PDF export including non-Latin guest names.
- Do **not** approve/send owner reports before reconciling the historical changed versions.

## Rollback

Old raw rows and configuration are retained. For a code rollback, use the Git commit you recorded before upgrading, rebuild just `app`, and restore your backup **only if necessary**. Schema additions are backward-compatible but a V2.5 app will not use the V2.7 decisions. Restoring a database overwrites edits since that backup and requires additional care.

## V2.7 specific verification
- Check the 28 Nov–3 Dec example: Nov 3 nights and Dec 2 nights; totals add back to original.
- Check full stay dates stay unchanged while monthly report shows allocated nights and values.
- Check historical report approval status (V2.7 must invalidate old monthly fingerprints).
- Backup prior reports separately; historical monthly numbers change under this accounting method.
