---
name: counterparty-review
description: Work through the Counterparty review queue on this machine - read Pillar 3 PDFs that the rules-based extractor could not verify, fill in the KM1 figures, collect PDFs from bot-blocked bank sites, and push the answers. Runs on the maintainer's Claude Code subscription; no API key anywhere.
---

# Counterparty review (local)

You are running inside a clone of the `bankCredit` repository on the maintainer's Mac.
The GitHub Actions pipeline collects Pillar 3 PDFs and reads the KM1 key-metrics
template with fixed rules. Whatever it cannot verify lands in
`data/review/queue.json`. Your job is to resolve those items and to fetch the
handful of documents that scripted collection cannot reach. Nothing here calls
an AI API: you are the reviewer, using your own reading of the PDF.

## 0. Prepare

```bash
git checkout -- data/json 2>/dev/null   # built JSON is regenerated locally and committed by the runner; never merge it by hand
git pull --ff-only
python3 -m bankcredit.cli review list
```

If the queue is empty and there is no browser-only work due (section 3), stop.

## 1. Resolve each queued item

For every open item (fields: `id`, `entity_id`, `url`, `local`, `page`,
`reference_date`, `currency`, `values`, `checks`, `reason`):

1. Get the PDF. Use `data/<local>` if it exists, otherwise download `url` into
   `data/cache/pdf/<entity_id>/` with curl (a normal browser User-Agent is fine).
2. Read the KM1 page. `page` is the extractor's best guess (1-based). Print it
   with PyMuPDF rather than opening the whole file:
   ```bash
   python3 -c "import fitz,sys; d=fitz.open(sys.argv[1]); print(d[int(sys.argv[2])-1].get_text())" <pdf> <page>
   ```
   If that page is not the key-metrics template, search the document for
   `KM1` / `Key metrics` and read the right page. The template may continue on
   the next page.
3. Take the **current period column** (column a, normally the first). Record
   these rows when present, in the template's own units:
   `cet1_capital`, `tier1_capital`, `total_capital`, `rwa` (currency millions),
   `cet1_ratio`, `tier1_ratio`, `total_capital_ratio`, `overall_capital_requirement`,
   `leverage_ratio`, `lcr`, `nsfr` (percent), `leverage_exposure` (currency millions).
   Convert thousands to millions. Use the group / consolidated column when a
   table shows group and solo side by side.
4. Check yourself the way the pipeline does: CET1 ratio must equal CET1 capital
   over RWA within about 0.3 points; Tier 1 ratio and total capital ratio must
   not be below CET1 ratio; the reference date must be the column header date.
5. Write the answer to `data/review/resolved/<id>.json`:
   ```json
   {"id": "<id>", "entity_id": "<entity_id>", "url": "<url>", "page": 7,
    "reference_date": "2026-06-30", "currency": "GBP",
    "values": {"cet1_capital": 2575.0, "rwa": 9141.4, "cet1_ratio": 28.2, "leverage_ratio": 6.7, "lcr": 186.7, "nsfr": 138.4},
    "note": "what you checked"}
   ```
   If the document has no KM1 table at all (for example a remuneration-only
   disclosure), write `{"id": "<id>", "skip": true, "note": "why"}` instead.

Never invent a figure. If a value is unreadable, leave it out and say so in `note`.

## 2. Load the answers

```bash
python3 -m bankcredit.cli review ingest
python3 -m bankcredit.cli learn
python3 -m bankcredit.cli build
```

`review ingest` also teaches the extractor: your page, currency and figures become
hints for that bank's next document (`data/review/hints.json`), a skipped document's
filename shape is never queued again, and your figures are the baseline the next
extraction is checked against for continuity. `learn` prints how often the rules
agreed with you and on which metrics they did not; it is committed with the data so
the maintainer can fix the rules where they keep failing. Nothing more is needed
from you for this.

Open `site/banks/<entity_id>.html` for one or two of the entities you touched
and confirm the figures and reference dates look right.

## 3. Browser-only firms

`bankcredit/adapters/pillar3_locators.py` marks some firms `kind="browser"`
(Lloyds Banking Group and its banks, Investec, Handelsbanken plc, the small
societies). Their sites block scripts. About once a quarter, or when the
Status page shows them older than 150 days:

1. Run `python3 -m bankcredit.cli browser` first. It tries each site with
   browser headers, then with headless Chromium, loads whatever it finds and
   prints the firms that are still blocked. Nothing else is needed for the
   firms it collected.
   Firms reported as "no matching links" had a readable page whose documents the
   locator pattern did not fit; the links the page offered are saved in
   `data/review/browser-links.json` (commit it with your push) so the pattern can
   be fixed in code. If one of those links is plainly the newest Pillar 3 PDF,
   download it and use step 3 rather than waiting.
2. For the firms it reports as blocked, use the Chrome extension. This only
   works in an interactive Claude Code session with Claude in Chrome connected
   (the daily `claude -p` job has no browser), so the maintainer starts one and
   asks for the blocked list. For each site: open the locator's `page` in the
   browser tab, let any challenge complete, find the newest Pillar 3 PDF (the
   link text or file name carries "Pillar 3" and a date), download it, move
   it under `data/cache/pdf/<entity_id>/`, note the URL, and go to step 3.
   The eight sites that block everything else, with what to look for:

   | entity_id | page | what to take |
   |---|---|---|
   | handelsbanken-plc | https://www.handelsbanken.co.uk/en/about-us/financial-information | "Pillar 3 disclosures" PDF, latest year end |
   | newcastle-bs | https://newcastle.co.uk/about-us/financial-results/ | "Pillar 3" PDF alongside the annual report |
   | sbi-uk | https://www.sbiuk.com/about-us/financial-information | "Pillar 3 disclosure" PDF (the site's certificate is bad; accept the warning) |
   | icbc-london | https://www.icbclondon.com/en/about-us/ | follow "Financial information" or "Disclosures"; the page moved |
   | qib-uk | https://www.qib-uk.com/about-us/financial-information/ | "Pillar 3" PDF |
   | uob | https://www.uobgroup.com/investor-relations/financial/index.page | "Pillar 3 Disclosure" quarterly PDF under Financial reports |
   | adcb | https://www.adcb.com/en/about-us/investor-relations/basel-iii/ | "Basel III Pillar 3" quarterly PDF |
   | qnb | https://www.qnb.com/sites/qnb/qnbglobal/page/en/eninvestorrelations.html | "Pillar III Disclosures" PDF under Financial Results |

   If a site has moved its documents, save the page you found them on: run
   `python3 -c "from bankcredit import learn; learn.remember_browser_page('<entity_id>', '<url>')"`
   so the collector tries there next time.
3. Run `python3 -m bankcredit.cli pdf <entity_id> <file> <source-url>`. It
   extracts, validates and loads exactly as the pipeline would; a failure goes
   to the queue and you resolve it as in section 1.

## 4. Push

```bash
git add data/facts.parquet data/documents.parquet data/review
git commit -m "Review queue: <n> items resolved, <m> documents added"
git push
```

The push triggers the pipeline, which rebuilds and republishes the site. Do
not commit anything under `data/cache/`. Do not touch the overlay secret or any
credentials. Report what you resolved, what you skipped and why.
