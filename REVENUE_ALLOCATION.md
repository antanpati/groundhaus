# Groundhaus V2.7 — Stay-Based Revenue Allocation

## Rule
Revenue, Gross Earnings proxy and OTA Service Fee are allocated separately across calendar months based on the actual nights of each booking, **not** the number of days (30/31) used for the occupancy denominator. The check-out date does not count as a stay night.

`Monthly Amount = Total Amount × Nights in Month / Total Booking Nights`

For every monetary field, rounded allocations are reconciled to the original total. The remainder goes to the final occupied month. This keeps the total unchanged and avoids rounding leakage. Allocations use decimal precision to 2 places; IDR display can hide decimals for simplicity.

Example 28 Nov–3 Dec, 5 nights, IDR 5,000,000: November 3 nights / IDR 3,000,000; December 2 nights / IDR 2,000,000.

## Separate accounting views
- **Actual Stay Revenue**: monthly allocated amount from deduplicated Paid reservations. This is **not** bank payout.
- **Upcoming Stay Revenue**: allocated forecast from upcoming reservations, kept separate from actual.
- **Payout**: actual transfer ledger by payout date; a payout must be matched/reconciled before attributing it to a villa. Do not add it to stay revenue.
- **Occupancy**: unique occupied room nights in month divided by units × calendar days in that month.
- **Management fee**: existing property-level fee percentage/basis applied to the monthly allocated Amount or Gross.
- **Expenses**: continue to be assigned to the user-selected month, not apportioned automatically.

## Special cases
- Cancelled before stay with zero nights: if a final cancellation penalty remains, it is placed in the effective check-in month; occupancy is 0. This is a reporting convention requiring owner verification.
- Shortened/extended stays use the latest approved final dates/Amount.
- Adjustments with unresolved decisions are **not** silently deducted and should block approval in any affected stay month.
- If source Nights disagrees with check-in/check-out duration, the date interval is used for allocation. Investigate source inconsistencies before approval.
- A booking may appear in two calendar-month reports, but the sum of its allocated revenue across all months equals its full reservation total. The number of bookings touching each month is **not** an additive distinct booking count across months.

## Excel/PDF
- `MONTHLY RECAP` shows monthly allocated Nights, Amount, Gross, and OTA fee, while check-in/out remain the **full stay dates**.
- `ALLOCATION DETAIL` records both the original booking-level totals and monthly allocated totals, so monthly reports can be audited.
- PDF has the same monthly allocation basis.
- `AIRBNB PAYMENT REPORT` remains a separate payout matching ledger.

## Release boundary
No source data, previous reports, or database migration is executed by downloading the package. Before updating the VPS, back up the SQLite database and retain your previous Git commit. All new calculations affect historical months when V2.7 is deployed. Revalidate owners' already issued reports rather than silently replacing them.
