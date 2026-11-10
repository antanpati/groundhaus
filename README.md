# Groundhaus Airbnb Reporting — V2.2

Streamlit web application: upload Airbnb transaction CSV, map listing -> property -> room, individual villa dashboard, owner reports Excel/PDF, payout reconciliation, local SQLite history and admin-only reset.

## Important security warning
The app includes real guest and revenue data: **do not publish without login and HTTPS**. Online mode refuses to show app data without an `APP_PASSWORD` of at least 16 characters. **Do not commit** `.env`, SQLite, financial CSVs, export files or other real guest data. The `.gitignore` and `.dockerignore` are preconfigured.

## Local Mac
Use Python 3.11-3.14; `bash run_mac.command`, then http://127.0.0.1:8501. The local launcher sets APP_MODE=local and binds to loopback only. Never use APP_MODE=local when serving the internet.

## Deploy to Ubuntu VPS via Docker Compose + Caddy TLS
Prerequisites: SSH, Git, Docker Engine and Docker Compose plugin on VPS; domain whose A record points to VPS; 80/443 TCP open; 443/udp optional. **Inspect old services before stopping them**. Avoid conflicts on 80/443: if your VPS already uses Nginx/Traefik/Caddy, integrate there instead of starting a second proxy.

1. Push this folder to a **private GitHub repository** after reviewing tracked files. Do not push databases or reports.
2. SSH to VPS, then `git clone https://github.com/YOUR_ORG/YOUR_PRIVATE_REPO.git /opt/groundhaus-reporting` (use SSH key or GitHub auth as required). `cd /opt/groundhaus-reporting`.
3. `cp .env.example .env` then edit `DOMAIN` and long random `APP_PASSWORD`, e.g. `nano .env`; `chmod 600 .env`.
4. Make sure DNS and ports point to VPS and 80/443 are free. `docker compose up -d --build`.
5. `docker compose ps`, `docker compose logs --tail=80 app caddy` and open `https://YOUR_DOMAIN`.

To update: `git pull --ff-only && docker compose up -d --build`. Named volume `groundhaus_data` remains persistent after container recreation. **Do not run** `docker compose down -v` unless intentionally destroying database volumes.

To back up SQLite database: use in-app download under sidebar > Reset seluruh data (backup first), save offline. When restoring server-side volumes, stop application, restore from verified backup using a container with correct volume ownership.

## Reset
Sidebar > **Reset seluruh data** > Download backup > type `HAPUS SEMUA DATA`, check acknowledgement, and enter admin password on online mode. Deletes transaction history, villa/room mappings, configuration, expenses, links, and approvals. Clears app session state. The schema stays available. Deletion is transactional and cannot be undone without restoring backup.

## Github commands (from this project folder on your Mac)
```
git init
git add .
git status
git commit -m "Groundhaus Reporting V2.2"
git branch -M main
git remote add origin git@github.com:YOUR_ACCOUNT/YOUR_PRIVATE_REPO.git
git push -u origin main
```
Review `git status` before committing. Do not share any CSV or DB in repository.

## Existing VPS service inventory before decommission
```
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
docker compose ls
sudo ss -ltnp | grep -E ':(80|443|8501|3000)\\b' || true
systemctl --type=service --state=running --no-pager
```
Once the specific old app and data paths are identified, back it up before stopping just its containers/services. **Never use** `docker system prune --volumes`, `rm -rf /var/www`, or `docker compose down -v` as generic cleanup.

## Accounting notes
Reservation revenue is assigned by check-in month, occupancy by room nights in month, payout reconciliation is not a bank receipt. Manually review and approve owner reports prior to sharing.


## Update V2.3
- Mapping listing → property → room/unit; satu property hanya tampil sekali dalam pilihan villa.
- Setelah klik Simpan mapping, dropdown menggunakan data mapping yang sudah tersimpan.
- Tabel ringkasan property/rooms di bawah form mapping agar mudah dicek.
- File `PROGRAM_STRUCTURE.md` menjelaskan lokasi setiap fitur untuk revisi selanjutnya.


## V2.4: Nama tamu Arab di PDF

PDF kini memakai font Unicode lokal, dengan `arabic-reshaper` + `python-bidi` untuk tulisan RTL. `run_mac.command` akan memasang dependensinya saat dijalankan dengan koneksi internet. Data asli CSV/Excel tidak diubah.

Font TTF yang didukung otomatis dicari, termasuk macOS `Arial Unicode.ttf` dan `DejaVuSans.ttf` jika terpasang. Bila font yang mendukung Arab tidak ditemukan, aplikasi menampilkan error yang jelas daripada mencetak kotak. Install font DejaVu Sans TTF pada Mac jika perlu, atau jalankan dengan `GROUNDHAUS_UNICODE_FONT=/path/to/font.ttf bash run_mac.command`.
