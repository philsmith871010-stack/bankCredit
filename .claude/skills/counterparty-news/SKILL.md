---
name: counterparty-news
description: Judge the collected headlines for the Counterparty site, the whole stored back book first and then each day's new ones - keep what tells a treasurer something about a bank's credit standing, drop the rest, correct severities - and write the verdicts the pipeline applies. Runs on the maintainer's Claude Code subscription; no API key anywhere.
---

# Counterparty news review (local)

The pipeline collects headlines through a rules-based filter. Rules cannot tell a
share buy-back notice from a capital problem, or a bank's own analyst call from news
about the bank. You can. Your verdicts are applied by the pipeline on every run and
kept for good, so a headline is judged once.

## 1. What to judge

The first runs work through the whole stored back book, newest first, 400 headlines a
run; after that each run sees only the day's new headlines. Repeat the run until the
unjudged total reads 0.

```bash
git pull --ff-only
python3 - <<'PY'
import json, pandas as pd
from bankcredit import store
from bankcredit.adapters.events import load_verdicts
ev = store.read("events"); ev = ev[(ev.type == "news")].sort_values("date", ascending=False)
seen = load_verdicts()
todo = ev[~ev.event_id.isin(seen)].head(400)          # newest first; everything stored is judged once, 400 a run
print(len(todo), "headlines to judge this run;", int((~ev.event_id.isin(seen)).sum()), "unjudged in total")
todo[["event_id", "entity_id", "date", "severity", "source", "title"]].to_csv("data/cache/news_todo.csv", index=False)
PY
```

Read `data/cache/news_todo.csv`. Judge every row.

## 2. The test

Keep a headline only if a treasurer deciding whether to place a deposit with that
bank would want to know it. Keep: rating actions and outlooks, capital or liquidity
news, losses, provisions, fines, enforcement, lawsuits with a material sum, fraud or
money-laundering findings, resolution or rescue talk, senior departures, results,
material M&A, large job cuts, cyber or outage incidents, regulator statements about
the bank. Drop: buy-back and treasury-share notices, 13F holdings, the bank as an
analyst or forecaster, its asset-management or ETF products, macro commentary "by"
the bank, sponsorship and community stories, marketing, and stories where the bank
is only mentioned in passing.

Severity: `bad` for events that could impair the bank's ability to repay (default,
resolution, rescue, fraud findings, large losses, downgrade to sub-investment grade);
`warn` for adverse but bounded (downgrade, negative outlook, fine, lawsuit, loss,
departure); `good` for upgrades, positive outlooks, strong results; `info` for the
rest. Only change a severity when the rules got it wrong.

## 3. Write the verdicts

Append to `data/review/news_verdicts.json` (a JSON object keyed by event_id; create
it if missing), one entry per row:

```json
{"news:0123abcd...": {"keep": false, "severity": null, "why": "share buy-back notice"},
 "news:4567ef01...": {"keep": true,  "severity": "warn", "why": "FCA fine"}}
```

`why` is a few words. Never invent an event_id; never edit entries already present.

## 4. Apply, check, push

```bash
python3 -m bankcredit.cli prune-news
python3 -m bankcredit.cli build
git add data/review/news_verdicts.json data/events.parquet
git commit -m "News review: <kept> kept, <dropped> dropped"
git push
```

Open `site/events/index.html` and confirm the feed reads like a credit desk's morning
list. Report what you dropped most often; recurring kinds become rules.
