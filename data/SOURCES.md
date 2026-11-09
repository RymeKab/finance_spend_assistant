# Data sources

Every file in this folder is read once, when the backend starts. Nothing in this folder is ever written by the app.

| File | Where it comes from | Notes |
|---|---|---|
| `invoices_2025_clean.csv` | Take-home data pack | 140 invoices from 2025 in EUR, GBP and USD. Some have no PO number or no approver; this is intentional. |
| `vendor_master.csv` | Take-home data pack | 10 vendors, each with a country, category and status (ACTIVE / INACTIVE / ON_HOLD). |
| `procurement_policy.md` | Take-home data pack | Excerpt of policy FIN-POL-014 v3.2. Loaded in full into the assistant's prompt and quoted word for word as evidence. |
| `ecb_eur_rates_2025.csv` | **Added by me**, downloaded from the European Central Bank (see below) | Exchange rates used to convert GBP and USD amounts to EUR, as required by policy §5.1. |

## About `ecb_eur_rates_2025.csv`

Policy §5.1 says non-EUR invoices are converted "at the ECB reference rate on the invoice date". The data pack has no exchange rates, so I downloaded the official ECB euro foreign exchange reference rates for 2025 and saved them here **unchanged**. The app reads this exact file, and its SHA-256 fingerprint appears in `GET /summary` and in every audit-log entry.

**Format:** `Date,USD,GBP`, one row per ECB business day (2 January to 31 December 2025, 255 days). Each value is the number of units of that currency per 1 EUR, as the ECB quotes it. For example, `2025-10-20,1.1655,...` means 1 EUR = 1.1655 USD on 20 October, so `amount_eur = amount / 1.1655`.

**Lookup rule:** each invoice uses the rate for its own date. The ECB publishes no rate on weekends and on its holidays (1 January, Good Friday, Easter Monday, 1 May, 25 and 26 December), so an invoice dated on one of those days uses the previous business day's rate. 16 of the 51 GBP and USD invoices fall on such a day; for example INV-20071 (Saturday 1 February) uses Friday 31 January's rate.

**Checks done on the file** (also covered by `backend/tests/test_fx.py`):

- 255 rows, no duplicate dates, no weekend rows, no empty cells; the only missing weekdays are the six ECB holidays listed above.
- USD stays between 1.0198 and 1.1837, GBP between 0.8253 and 0.8846.
- One cell is written unusually: the USD rate for 15 January is `01.03`. It is read as 1.03, which fits the days around it. No GBP or USD invoice is dated before 1 February, so it doesn't affect any figure.

**To refresh it:** download the 2025 USD and GBP reference rates from the ECB website, keep the same three columns (`Date,USD,GBP`), replace this file and restart the backend. The fingerprint changes, so answers produced with different rates can always be told apart.
