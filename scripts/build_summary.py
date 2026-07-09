#!/usr/bin/env python3
"""
build_summary.py — Turn a Fidelity "Portfolio_Positions" CSV export into a
shareable portfolio summary (Markdown + styled HTML).

Sections produced:
  1. Equity positions  — Ticker | Shares | Market value | % of port   (incl. crypto)
  2. Cash              — money-market cash across all accounts | Amount | % of port
  3. Options           — Contract | Type (Long/Short) | Qty | Note

Usage:
  python3 build_summary.py --csv <path> --outdir <dir> [--asof YYYY-MM-DD] [--holdings <ticker=shares:mv>...]

"% of port" = market value / total account value (equities + crypto + cash + net option value).

Notes on the Options "Note" column are HEURISTIC:
  - short put  -> "cash-secured"          (can't tell margin vs cash-secured from the export)
  - short call -> "covered vs TICKER shares" when the underlying is held, else "naked?"
  - long       -> "—"
Review these before sharing.
"""
import argparse, csv, io, re, os, datetime, json

MONEY_MKT = {"SPAXX", "FDRXX", "FCASH", "USD"}

def clean_num(s):
    if s is None:
        return None
    s = s.strip().replace("$", "").replace(",", "").replace("%", "")
    if s in ("", "--", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None

def base_sym(sym):
    return sym.strip().lstrip("-").split("/")[0].strip()

def is_money_market(sym, desc):
    b = base_sym(sym).rstrip("*")
    if b in MONEY_MKT:
        return True
    return "MONEY MARKET" in (desc or "").upper()

OPT_RE = re.compile(r"^-?([A-Z]+\d*)(\d{6})([CP])([\d.]+)$")

def parse_option(sym):
    """'-NBIS260717P200' -> dict(underlying, expiry, cp, strike). None if not an option."""
    raw = sym.strip().lstrip("-").replace(" ", "")
    m = OPT_RE.match(raw)
    if not m:
        return None
    root, yymmdd, cp, strike = m.groups()
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    exp = datetime.date(2000 + yy, mm, dd)
    strike = float(strike)
    strike_s = f"{strike:g}"
    return {
        "underlying": root,
        "expiry": exp,
        "cp": cp,
        "strike": strike,
        "label": f"{root} {exp.strftime('%b-%-d-%y')} {strike_s} {cp}",
    }

def load(csv_path):
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    rows = list(csv.DictReader(io.StringIO(text)))
    equities = {}          # ticker -> [shares, market_value, cost]
    crypto = {}            # ticker -> [qty, market_value, cost]
    options = []           # list of dicts
    cash_total = 0.0
    net_option_value = 0.0

    for r in rows:
        sym = (r.get("Symbol") or "").strip()
        acct = (r.get("Account Name") or "").strip()
        if not sym:
            continue
        desc = r.get("Description") or ""
        val = clean_num(r.get("Current Value")) or 0.0
        qty = clean_num(r.get("Quantity"))
        cost = clean_num(r.get("Cost Basis Total")) or 0.0

        # Cash / money-market / pending
        if is_money_market(sym, desc) or sym.lower().startswith("pending"):
            cash_total += val
            continue

        # Options: Fidelity encodes them with a leading dash
        opt = parse_option(sym)
        if opt is not None:
            net_option_value += val
            options.append({**opt, "qty": qty or 0.0})
            continue

        # Crypto (e.g. BTC/USD)
        if "/" in sym:
            t = base_sym(sym)
            c = crypto.setdefault(t, [0.0, 0.0, 0.0])
            c[0] += qty or 0.0; c[1] += val; c[2] += cost
            continue

        # Plain equity — aggregate lots across accounts
        t = base_sym(sym)
        e = equities.setdefault(t, [0.0, 0.0, 0.0])
        e[0] += qty or 0.0; e[1] += val; e[2] += cost

    book = sum(v[1] for v in equities.values()) + sum(v[1] for v in crypto.values()) + cash_total + net_option_value
    return equities, crypto, options, cash_total, book

def aggregate_options(options, held_tickers):
    """Collapse identical contracts, sign -> type, attach heuristic note."""
    merged = {}
    for o in options:
        key = (o["underlying"], o["expiry"], o["cp"], o["strike"])
        merged.setdefault(key, {**o, "qty": 0.0})["qty"] += o["qty"]
    out = []
    for o in merged.values():
        if abs(o["qty"]) < 1e-9:
            continue
        typ = "Long" if o["qty"] > 0 else "Short"
        note = "—"
        if typ == "Short":
            if o["cp"] == "P":
                note = "cash-secured"          # [INFERENCE]
            else:
                note = (f"covered vs {o['underlying']} shares"
                        if o["underlying"] in held_tickers else "naked?")  # [INFERENCE]
        out.append({"contract": o["label"], "type": typ,
                    "qty": int(abs(o["qty"])), "note": note,
                    "sort": (o["expiry"], o["underlying"])})
    out.sort(key=lambda x: x["sort"])
    return out

# ---------- renderers ----------
def money(x): return f"${x:,.0f}"
def fmt_shares(sh):
    if abs(sh - round(sh)) < 1e-9:
        return f"{sh:,.0f}"
    return f"{sh:,.5f}".rstrip("0").rstrip(".")
def pct(x, book): return f"{100*x/book:.1f}%" if book else "—"

def render_md(equities, crypto, options, cash, book, asof):
    lines = [f"# Portfolio summary — {asof}", "",
             f"**Total port:** {money(book)}", "",
             "## Equity positions", "",
             "| Ticker | Shares | Market value | % of port |",
             "|---|---:|---:|---:|"]
    rows = [(t, v[0], v[1]) for t, v in equities.items()] + [(t, v[0], v[1]) for t, v in crypto.items()]
    for t, sh, mv in sorted(rows, key=lambda x: -x[2]):
        sh_s = fmt_shares(sh)
        lines.append(f"| {t} | {sh_s} | {money(mv)} | {pct(mv, book)} |")
    lines += ["", "## Cash", "",
              "| | Amount | % of port |", "|---|---:|---:|",
              f"| Money-market cash (all accounts) | {money(cash)} | {pct(cash, book)} |",
              "", "## Options", "",
              "| Contract | Type | Qty | Note |", "|---|---|---:|---|"]
    for o in options:
        lines.append(f"| {o['contract']} | {o['type']} | {o['qty']} | {o['note']} |")
    lines += ["", "_Option “Note” values are heuristic ([INFERENCE]) — verify before sharing._"]
    return "\n".join(lines)

HTML_TMPL = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Portfolio summary — {asof}</title><style>
:root{{--ink:#1a1a1a;--muted:#6b6b6b;--rule:#e2ddd4;--bg:#faf9f6;--accent:#2a2a2a}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font-family:Georgia,"Times New Roman",serif;line-height:1.4;
 -webkit-font-smoothing:antialiased}}
.wrap{{max-width:820px;margin:0 auto;padding:48px 40px}}
h1{{font-size:15px;font-weight:700;letter-spacing:.01em;margin:0 0 4px}}
.asof{{color:var(--muted);font-size:13px;margin:0 0 36px}}
h2{{font-size:24px;font-weight:700;margin:40px 0 4px}}
table{{width:100%;border-collapse:collapse;font-size:16px}}
th{{text-align:left;font-weight:700;color:var(--accent);font-size:15px;
 padding:14px 8px;border-bottom:1px solid var(--rule)}}
td{{padding:16px 8px;border-bottom:1px solid var(--rule)}}
th.r,td.r{{text-align:right;font-variant-numeric:tabular-nums}}
tr:last-child td{{border-bottom:1px solid var(--rule)}}
.note{{color:var(--muted);font-size:12px;font-style:italic;margin-top:14px}}
.foot{{color:var(--muted);font-size:12px;margin-top:40px;
 border-top:1px solid var(--rule);padding-top:14px}}
</style></head><body><div class="wrap">
<h1>Portfolio summary</h1><p class="asof">As of {asof} &middot; total port {book}</p>
<h2>Equity positions</h2>
<table><thead><tr><th>Ticker</th><th class="r">Shares</th>
<th class="r">Market value</th><th class="r">% of port</th></tr></thead><tbody>
{equity_rows}
</tbody></table>
<h2>Cash</h2>
<table><thead><tr><th>&nbsp;</th><th class="r">Amount</th>
<th class="r">% of port</th></tr></thead><tbody>
<tr><td>Money-market cash (all accounts)</td><td class="r">{cash}</td>
<td class="r">{cash_pct}</td></tr>
</tbody></table>
<h2>Options</h2>
<table><thead><tr><th>Contract</th><th>Type</th>
<th class="r">Qty</th><th>Note</th></tr></thead><tbody>
{option_rows}
</tbody></table>
<p class="note">Option &ldquo;Note&rdquo; values are heuristic and should be verified before sharing.</p>
<p class="foot">Generated by the trading-port-summary skill. For informational use only; not investment advice.</p>
</div></body></html>"""

def render_html(equities, crypto, options, cash, book, asof):
    rows = [(t, v[0], v[1]) for t, v in equities.items()] + [(t, v[0], v[1]) for t, v in crypto.items()]
    er = []
    for t, sh, mv in sorted(rows, key=lambda x: -x[2]):
        sh_s = fmt_shares(sh)
        er.append(f'<tr><td>{t}</td><td class="r">{sh_s}</td>'
                  f'<td class="r">{money(mv)}</td><td class="r">{pct(mv, book)}</td></tr>')
    orr = [f'<tr><td>{o["contract"]}</td><td>{o["type"]}</td>'
           f'<td class="r">{o["qty"]}</td><td>{o["note"]}</td></tr>' for o in options]
    return HTML_TMPL.format(asof=asof, book=money(book),
                            equity_rows="\n".join(er),
                            cash=money(cash), cash_pct=pct(cash, book),
                            option_rows="\n".join(orr))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--asof", default=datetime.date.today().isoformat())
    args = ap.parse_args()

    equities, crypto, options, cash, book = load(args.csv)
    held = set(equities) | set(crypto)
    opts = aggregate_options(options, held)

    os.makedirs(args.outdir, exist_ok=True)
    md = render_md(equities, crypto, opts, cash, book, args.asof)
    html = render_html(equities, crypto, opts, cash, book, args.asof)
    md_path = os.path.join(args.outdir, f"portfolio-summary-{args.asof}.md")
    html_path = os.path.join(args.outdir, f"portfolio-summary-{args.asof}.html")
    with open(md_path, "w") as f: f.write(md)
    with open(html_path, "w") as f: f.write(html)
    print(json.dumps({"md": md_path, "html": html_path,
                      "book": round(book, 2),
                      "equities": len(equities) + len(crypto),
                      "options": len(opts), "cash": round(cash, 2)}, indent=2))

if __name__ == "__main__":
    main()
