---
name: trading-port-summary
description: Generate a clean, shareable portfolio holdings summary (Equity positions, Cash, Options) from a Fidelity "Portfolio_Positions" CSV export, aggregating lots across all accounts. Use whenever the user asks for a "portfolio summary", "summary of my holdings", "holdings table", "positions I can share", "shareable portfolio", or uploads a Fidelity positions CSV and wants it turned into a tidy overview — even if they don't say the word "skill". Produces both Markdown and a styled, share-ready HTML.
---

# Trading Portfolio Summary

Turns a raw Fidelity positions export into a three-section, share-ready summary:
**Equity positions** (incl. crypto), **Cash**, and **Options**. The goal is a
document that can be handed to another person as-is — no account numbers, no
per-lot noise, no jargon.

**Output files** (create the `portfolio` folder if needed):
- `/outputs/portfolio/portfolio-summary-[YYYY-MM-DD].html`  ← primary shareable
- `/outputs/portfolio/portfolio-summary-[YYYY-MM-DD].md`    ← plain-text version

Present both. Offer a PDF (print the HTML) if the user wants to email/attach it.

---

## Step 1 — Locate the data

Primary source is a **Fidelity `Portfolio_Positions_*.csv` export** in
`/mnt/user-data/uploads/`. If none is attached, ask the user to export one
(Fidelity → Positions → Download), or — if a **SnapTrade** connector is
available — pull live positions and write them into the same CSV column shape
before running the script. Do not fabricate holdings.

Use the export's own "Date downloaded" (bottom of the file) as the as-of date
when present; otherwise today.

## Step 2 — Build the summary

Run the bundled script (it is deterministic — always prefer it over hand-parsing,
which drops fractional shares and misreads Fidelity's option symbols):

```bash
python3 scripts/build_summary.py \
  --csv "/mnt/user-data/uploads/<file>.csv" \
  --outdir /mnt/user-data/outputs/portfolio \
  --asof <YYYY-MM-DD>
```

The script:
- **Aggregates equity lots by ticker across every account** (a name held in both
  IRA and taxable becomes one row).
- Sorts equities by market value, descending.
- Treats crypto (e.g. `BTC/USD`) as an equity-section line.
- Rolls all money-market balances (`SPAXX`, `FDRXX`, `FCASH`) and "Pending
  activity" into a single **Cash** line.
- Detects **options** by Fidelity's leading-dash symbol format and decodes each
  into a readable contract (`NBIS Jul-17-26 200 P`), signs quantity into
  **Long/Short**, and merges duplicate contracts held in different accounts.

**Definitions (keep consistent):**
- **% of port** = position market value ÷ total account value, where total port =
  equities + crypto + cash + net option value. All %s sum to ~100%.
- **Shares** shown whole for ≥1, full precision for fractional crypto.

## Step 3 — Sanity-check before presenting

- Confirm the reported **total port** matches the CSV's own account total.
- **The Options "Note" column is heuristic — treat every value as [INFERENCE].**
  The export can't distinguish cash-secured from margin puts, or covered from
  naked calls; the script guesses (short put → "cash-secured"; short call →
  "covered vs TICKER shares" if the underlying is held, else "naked?").
  Correct any note you know to be wrong before sharing, and keep the
  "verify before sharing" footnote in the output.
- If a ticker looks like an adjusted option (Fidelity `(ADJ)`), the strike/root
  may be non-standard (e.g. `OPEN1`); leave it as decoded and flag it.

## Step 4 — Present

Show both files with `present_files` (HTML first). In chat, give a one-line
readout: total port, top-3 concentrations by % of port, and cash %. Do not
paste the whole table back into chat — the files are the deliverable.

---

## Output format (both files use this exact structure)

```
# Portfolio summary — [as-of date]
Total port: $X

## Equity positions
Ticker | Shares | Market value | % of port

## Cash
Money-market cash (all accounts) | Amount | % of port

## Options
Contract | Type | Qty | Note
```

The HTML uses a restrained serif document style (off-white ground, hairline row
rules, tabular-aligned numbers) so it reads as a finished one-pager rather than a
spreadsheet dump. Keep it single-file and self-contained.

---

## Scope guardrails

This skill **summarizes** holdings only. It does not value, rate, or recommend
positions, and it adds no price targets or gain projections. If the user wants
valuation, trim signals, or expected-gain math, hand off to `assess-company` /
`trading-playbooks` — don't blend analysis into the shareable summary.
