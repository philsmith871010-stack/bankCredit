# Counterparty (PWLBtoday)

Free, transparent credit view of banks and building societies that UK treasury teams place money with. Public regulatory data, public rating registers, traded market prices and primary-source news, every figure traceable to its document.

- `docs/data-sources-investigation.md`: where every number comes from and what was verified.
- `docs/build-plan.md`: product, architecture, method, phases and decisions.
- `design/`: screen designs matching PWLBtoday's tokens.
- `bankcredit/`: pipeline (adapters, store, export) and static site generator.
- `research/`: probe scripts used during the investigation.
- `data/`: entity master, Parquet tables and JSON exports committed by the pipeline.

Development happens on `main`; every push rebuilds and deploys the site. A commit message containing `[collect]` also runs the daily adapters and commits the data, the same as the 06:10 UK schedule.

Run locally:

```
pip install -r requirements.txt
python -m bankcredit.cli run esma yahoo fdic eba pillar3
python -m bankcredit.cli build        # writes site/
```

Adapters: `fdic`, `eba`, `edgar` (quarterly), `esma` ratings, `yahoo` prices, `pillar3`
documents, `events` (rating actions, disclosures, filtered news), `fred`
benchmark spreads, `ice` and `dtcc` CDS, `bonds` (daily) and `te`, the EBA Transparency Exercise
(quarterly, six years of EU capital history). Bond quotes come from Börse Frankfurt's
public price pages and are rebuilt on every run rather than committed; the site shows only each bank's
30-day yield change against peers in the same currency, never a level. No AI API key is used anywhere. Pillar 3 PDFs are read by a rules-based KM1
extractor (`bankcredit/extract/km1.py`) with arithmetic cross-checks; whatever
fails goes to `data/review/queue.json`, which is worked through on the
maintainer's Mac by the repository skill `/counterparty-review` under a Claude
Code subscription login. See `docs/local-run.md`.

```
python -m bankcredit.cli extract some.pdf           # try the extractor on a file
python -m bankcredit.cli pdf <entity> some.pdf url  # load a PDF fetched by hand
python -m bankcredit.cli review list | ingest       # review queue
python -m bankcredit.cli reprocess                  # re-read cached PDFs after an extractor change
```
