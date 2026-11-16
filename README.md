## V2.7 — Stay-Based Revenue Allocation

See `REVENUE_ALLOCATION.md`. November/December stays now split Amount, Gross and OTA Fee by occupied nights. Historic monthly report figures will change; backup and verify before production deployment.

# Groundhaus Airbnb Reporting V2.7

Streamlit application for Groundhaus villa reporting. Python 3.12 recommended.

## Changes in V2.7

- Import **Paid** and **Upcoming** separately (Airbnb CSV exports).
- Deduplicate reservations by **Confirmation Code**; identical repeated uploads are ignored.
- Keep a **version history**, report differences, and allow explicit selection of the accepted Paid / Upcoming version.
- **Manual Cancel / Shorten / Modify** with final dates, revenue, OTA fee, gross and a required reason. Past source rows are preserved; actions have an audit trail.
- **Adjustment review**: when Airbnb includes an Adjustment transaction, choose whether it is already included, must be applied, or excluded. Never apply it automatically, to avoid a second deduction.
- Separate **Actual Paid** versus **Upcoming Expected** in the villa dashboard.
- Export Excel and PDF for actual Paid reservations. Excel includes a new `RESERVATION STATUS` worksheet.
- Keep previous property / room mapping, additional expenses, management fees, and report approval workflow.

**Important reporting definitions:** Paid is a source category, not proof that cash has entered the bank; Upcoming Amount is a forecast, not realized revenue. No automatic cancellation is inferred from a missing Upcoming booking.

## Data migration

Old database remains untouched in structure and original transactions. V2.7 creates tables with the `v26_` prefix, which are populated from the existing `transactions` table when the app starts. This is a nondestructive migration.

An old report approval is **invalidated** by the new reservation snapshot state and must be reviewed again. Always make a database backup before updating server code.

## Usage

1. Upload **Paid CSV** in the sidebar using `Import CSV ke histori`.
2. Upload **Upcoming CSV** in the separate sidebar upload.
3. Set property/room mapping if a new listing appears.
4. Choose a property and month.
5. Check `Reservation Lifecycle` and resolve flagged versions / adjustments.
6. For a cancellation or shortened stay, select the Confirmation Code and set dates and final amounts; enter a reason.
7. Verify actual, forecast, occupancy, payout matching; approve and export the owner report.

### Manual cancellation with penalty

Use status `Cancelled`, check-in date equal to check-out date, 0 occupied nights, and set **Amount final** to the penalty that belongs in the report (or 0 for a full refund). Do not assume a percentage refund based on room nights. For an early checkout, use `Modified`, not `Cancelled`, to keep actual occupied nights.

### What this version does NOT do

- It does not automatically know that a booking was cancelled because it disappeared from an Upcoming export.
- It does not merge third-party reservation feeds or provide real-time Airbnb API sync.
- It does not automatically match a payout to bank receipt.
- It does not decide whether an Adjustment has already affected the final Amount. That remains a manual review.
- New V2.7 UI has been validated by source compilation and automated engine tests, but not end-to-end against the live VPS and Streamlit browser.

## Files

- `app.py` — Streamlit UI, imports, dashboard, review, approval, export
- `reservation_master.py` — V2.7 deduplication, versioning, audit, changes, import
- `store.py` — persistent SQLite schema and legacy storage
- `engine.py` — monthly occupancy, revenue, payout reconciliation
- `reporting.py` — Airbnb CSV normalization and IDR formatting
- `owner_exports.py` — Excel/PDF reporting with status worksheet
- `Dockerfile` — Python 3.12, packages and Unicode font
- `DEPLOY_UPGRADE.md` — GitHub + VPS safe update instructions
- `tests/test_master.py` — synthetic unit tests, no guest data

Run locally: `bash run_mac.command` (or `streamlit run app.py`).
