# GROUNDHAUS REPORTING V2.3 — PETA PROGRAM

## Alur sistem
1. **Upload CSV** → `app.py` (Data Master), `reporting.py::parse_csv`, `store.py::import_transactions` → SQLite.
2. **Mapping**: setiap **Airbnb Listing** punya **1 Property** dan **1 Room/Unit**. Banyak listing boleh punya Property sama. `app.py` (bagian 2) → `store.py::set_mappings_bulk`; data disimpan pada tabel `mapping`.
3. **Pilih Property**: daftar property unik berasal dari mapping yang **sudah disimpan**. `app.py` bagian 3 (`all_villas`, `st.selectbox`).
4. **Dashboard**: `engine.py::reservation_month`, `engine.py::summarize`, `engine.py::occupancy`, `app.py` bagian 4. Semua kamar dalam property dipadukan untuk summary, tetapi kolom Room tetap tersimpan di detail.
5. **Pengeluaran**: `app.py` bagian 5; `store.py::get_expenses/add_expense/remove_expense`.
6. **Rekonsiliasi payout**: `app.py` bagian 6, `engine.py::reconciliation`, `store.py::get_links/set_links`.
7. **Approval/export**: `app.py` bagian 7; `owner_exports.py::make_excel/make_pdf/zip_all`.
8. **Histori**: `app.py` bagian 8; data dari SQLite.
9. **Reset data**: sidebar `app.py`; `store.py::reset_all_data/backup_database`.

## File utama
- `app.py` — seluruh halaman, form, tombol dan navigasi UI Streamlit.
- `store.py` — operasi database SQLite, mapping, settings, histori, pengeluaran.
- `engine.py` — logika grouping, revenue, occupancy, matching.
- `reporting.py` — parser CSV Airbnb, format IDR, normalisasi data.
- `owner_exports.py` — layout report Excel/PDF.
- `requirements.txt` — library Python.
- `run_mac.command` — launcher Mac yang menjalankan server lokal.
- `app_data/groundhaus.sqlite3` — DATABASE PRIBADI yang dibuat setelah app dijalankan. Tidak dibundel dan jangan di-upload ke GitHub.
- `.gitignore` — menghindari pengiriman CSV, database dan secrets ke GitHub.
- `Dockerfile`, `compose.yaml`, `Caddyfile`, `.env.example` — untuk deployment VPS di kemudian hari, tidak diperlukan untuk mode lokal.

## Panduan revisi berikutnya
- Mau ganti aturan mapping/property/kamar → sebut `app.py BAGIAN 2` dan `store.py`.
- Mau ganti dropdown atau pilihan property → sebut `app.py BAGIAN 3`.
- Mau ganti perhitungan income/occupancy → sebut `engine.py`.
- Mau ganti tampilan dashboard → sebut `app.py BAGIAN 4`.
- Mau ganti laporan Excel/PDF → sebut `owner_exports.py`.
- Mau menambahkan field database → sebut `store.py`.

## Cara menjaga data saat upgrade
1. Tutup aplikasi lokal menggunakan `Control+C` di Terminal.
2. Backup/copy **folder `app_data`** dari versi sebelumnya.
3. Extract aplikasi versi baru ke folder baru.
4. Copy `app_data` ke folder aplikasi versi baru, lalu `bash run_mac.command`.
5. Jangan copy `.venv` atau database ke GitHub.

**Contoh mapping**: `Modern Suite` → `Cemagi` → `Bima`; `Modern Villa` → `Cemagi` → `Sadewa`. Dropdown property hanya menampilkan `Cemagi` sekali.

**Peringatan**: untuk occupancy persis, satu nama Room harus benar-benar mewakili satu unit fisik. Dua listing yang menunjuk kamar fisik sama harus dipetakan ke Room sama. Jumlah unit tersedia disetel di Settings Villa.


### V2.4 Arabic PDF fix
- `owner_exports.py` fungsi `_unicode_font()`: deteksi font TTF lokal yang mendukung huruf Arab.
- `owner_exports.py` fungsi `_pdf_text()`: Arabic shaping + arah baca kanan-ke-kiri untuk PDF.
- `owner_exports.py` fungsi `make_pdf()`: memakai font Unicode dan nama tamu RTL.
- `requirements.txt`: dependensi `arabic-reshaper`, `python-bidi`.
