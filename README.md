# trading-port-summary

A [Claude Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
that turns a raw **Fidelity `Portfolio_Positions` CSV export** into a clean,
shareable one-page portfolio summary — **Equity positions**, **Cash**, and
**Options** — as both styled HTML and Markdown.

It aggregates lots across every account, decodes Fidelity's option symbols into
readable contracts, and computes each position's share of the portfolio.

## What it produces

Three sections, sorted and share-ready (no account numbers, no per-lot noise):

| Section | Columns |
|---|---|
| Equity positions | Ticker · Shares · Market value · % of port |
| Cash | Money-market cash (all accounts) · Amount · % of port |
| Options | Contract · Type (Long/Short) · Qty · Note |

See [`examples/`](examples/) for sample input and output.

## Install

Drop the `trading-port-summary/` folder into your Claude skills directory (or
import the packaged `.skill` file via the Claude app). Once installed, it
triggers on requests like *"give me a shareable summary of my holdings"* or when
you upload a Fidelity positions CSV.

## Use directly (without Claude)

The renderer is a plain, dependency-free Python script:

```bash
python3 scripts/build_summary.py \
  --csv path/to/Portfolio_Positions_YYYY-MM-DD.csv \
  --outdir ./out \
  --asof 2026-01-15        # optional; defaults to today
```

Outputs `portfolio-summary-<date>.html` and `.md` to `--outdir`.

## How it reads the export

- **Equities** are aggregated by ticker across all accounts.
- **Crypto** (e.g. `BTC/USD`) is listed in the equity section.
- **Money-market** balances (`SPAXX`, `FDRXX`, `FCASH`) and "Pending activity"
  roll into a single Cash line.
- **Options** are detected by Fidelity's leading-dash symbol format
  (`-NBIS260717P200`), decoded to `NBIS Jul-17-26 200 P`, and signed
  Long/Short by quantity.
- **% of port** = position market value ÷ total account value
  (equities + crypto + cash + net option value).
- **Column headers are matched case-insensitively.** Fidelity's export has
  varied the capitalization of its headers over time (e.g. `Current Value` vs
  `Current value`); the script normalizes them so either form parses correctly.

## Caveat: the Options "Note" column is heuristic

A positions export can't distinguish a cash-secured put from a margin put, or a
covered call from a naked one. The script guesses (short put → "cash-secured";
short call → "covered vs TICKER shares" when the underlying is held). **Verify
these before sharing.**

## Scope

This skill *summarizes* holdings. It does not value, rate, or recommend
positions, and adds no price targets or projections.

## Changelog

- **2026-07-15** — Fixed CSV parsing to match column headers
  case-insensitively. A Fidelity export using lowercase headers (e.g.
  `Current value`) previously caused every market value to read as `$0`;
  headers are now normalized before lookup. Backward-compatible with
  title-case exports.

## License

MIT — see [LICENSE](LICENSE).

---

*For informational use only. Not investment advice.*
