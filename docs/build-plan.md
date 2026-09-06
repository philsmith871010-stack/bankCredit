# Build plan: bank and building society credit platform

Date: 6 September 2026. Companion to `docs/data-sources-investigation.md`. Assumes a first release inside PWLBtoday as a new tool, on free data only, with the data layer built so a standalone site can be added later.

## 1. Product definition

Working name inside PWLBtoday: **Counterparty**. One line: the free, transparent credit view of every bank and building society a UK treasury team might place money with, built from public regulatory data, public rating registers, traded market prices and primary-source news, with every number traceable to its source document.

Audience, in order: local authority treasury teams (existing PWLBtoday users); treasury advisers and auditors; charity, university and corporate cash managers; savers above the FSCS limit; journalists and analysts.

Jobs the product must do:

1. Answer "is this counterparty acceptable today?" in under ten seconds: score, band, direction of travel, and the one thing to worry about.
2. Support the counterparty list in a treasury management strategy: an exportable, dated, sourced table for a defined universe.
3. Let an analyst dig into one bank: key metrics over time, ratings history, market signals, news, and the underlying documents.
4. Tell people when something changes: rating actions, new Pillar 3, band moves, credit-relevant news.
5. Show its working: a published method, a back-test, and a data-age badge on every figure.

Non-goals for release one: investment advice or a recommendation to deposit; money market funds; sovereign ratings beyond a context strip; intraday market data; paid data of any kind.

## 2. Universe for release one

About 130 entities, grouped by how councils use them:

| Group | Count | Examples | Primary data route |
|---|---|---|---|
| UK banks | 25 | Barclays, HSBC UK, Lloyds, NatWest, Santander UK, Standard Chartered, Virgin Money, TSB, Co-op, Metro, OSB, Shawbrook, Aldermore, Close Brothers, Paragon, Secure Trust, Monzo, Starling, Goldman Sachs International Bank, Handelsbanken plc | Pillar 3 PDFs (plain HTTP for most; FCA NSM for Paragon and Close Brothers; browser job for Lloyds) |
| UK building societies | 20 | Nationwide, Yorkshire, Coventry, Skipton, Leeds, Principality, West Brom, Nottingham, Newcastle, Cumberland and the next ten by assets | Pillar 3 PDFs, annual for most |
| UK subsidiaries of overseas banks | 8 | Al Rayan, Gatehouse, SBI UK, ICICI UK, Bank of China UK, ICBC London, Bank of Baroda UK, Investec | Annual Pillar 3 PDFs |
| EU and EEA banks | 35 | Nordea, SEB, Swedbank, Handelsbanken, Danske, DNB, ING, Rabobank, ABN, Deutsche, Commerzbank, Helaba, LBBW, BayernLB, DZ, BNP, Crédit Agricole, SocGen, BPCE, Crédit Mutuel, KBC, Belfius, Santander, BBVA, CaixaBank, Intesa, UniCredit, Erste, Raiffeisen, Bank of Ireland, AIB, La Banque Postale, OP, Nykredit | EBA Pillar 3 Data Hub (XBRL-CSV), Transparency Exercise backfill |
| Australia and Canada | 12 | ANZ, CBA, NAB, Westpac, Macquarie, Bendigo; RBC, TD, Scotiabank, BMO, CIBC, National Bank | Bank spreadsheets plus APRA and OSFI tables |
| Asia | 10 | DBS, OCBC, UOB; HSBC HK, BOCHK, StanChart HK; MUFG, SMFG, Mizuho, Sumitomo Mitsui Trust | Quarterly Pillar 3 PDFs |
| Gulf | 6 | QNB, FAB, Emirates NBD, ADCB, Al Rajhi, Saudi National Bank | Pillar 3 PDFs (QNB and ADCB via browser job) |
| US and Swiss | 10 | JPMorgan, Bank of America, Citi, Wells Fargo, Goldman, Morgan Stanley, BNY, State Street, Northern Trust; UBS | FDIC API; UBS Pillar 3 |

Every entity gets an LEI, country, type, group parent, regulatory tier, tickers and bond ISINs in the entity master, plus a "locator" record for each document source.

## 3. Information architecture

Top-level navigation inside the PWLBtoday shell (one new sidebar entry, "Counterparty", with sub-pages):

1. **Board**: the whole universe as a dense, sortable table with a card view for mobile. Columns: name, country, type, score, band, 90-day change, CET1 ratio, leverage ratio, LCR, latest rating composite, CDS or spread signal, unread credit events, data age. Filters: group, country, band, adviser-list preset, my watchlist. Saved views per account.
2. **Bank profile**: the product's core page, described in section 4.
3. **Events**: a single timeline across the universe of rating actions, new disclosures, regulatory notices, results and labelled news, filterable by bank, type and severity.
4. **Brief**: a daily credit brief (morning), generated from the previous day's events and reviewed before publication, in the same voice as PWLBbrief.
5. **Compare**: up to four banks side by side, same metric rows, same chart scales.
6. **Method**: the published formula, weights, band thresholds, back-test, data sources, freshness commitments, limitations.
7. **Status**: what updated when, per source; failures visible.

## 4. The bank profile page

Above the fold, on one screen without scrolling on a laptop:

- Header strip: name, group, country flag, entity type, LEI, links to the bank's own disclosure page, watchlist toggle, export.
- Score panel: the score (0 to 100) with band letter, the position within the peer band drawn as a horizontal ribbon with percentile markers, the 90-day and 1-year change, and a one-sentence machine-written "what moved" line reviewed by the editor.
- Key metrics strip: six tiles from KM1 (CET1 ratio, Tier 1 leverage, total capital ratio, LCR, NSFR, RWA growth) each with the value, the change on the prior period, a 12-quarter sparkline, the peer median, and the "as of" date. Tapping a tile opens the trend view for that metric.
- Signals row: rating composite with agency chips; market signal (CDS where it exists, otherwise bond spread proxy, otherwise equity-implied); realised vol; unread events count.

Below the fold, as tabs that deep-link:

- **Trends**: full-width charts per metric over the whole history held (EU from 2013 via the Transparency Exercise, US from 1984, UK as far as parsed), with requirement lines (for example CET1 minimum plus buffers where disclosed), peer band shading and event markers.
- **Ratings**: table by agency of current long-term, short-term, deposit, counterparty and resolution counterparty ratings with outlook and date; history timeline of actions with press-release links to the ESMA record.
- **Market**: equity price with 30 and 90-day realised vol, drawdown from 52-week high; CDS prints and settlement-derived levels for names that have them; iTraxx Senior Financials context; bond spread proxy for names without CDS.
- **News and events**: the labelled timeline for this bank, with event type, severity and source chips, primary sources first.
- **Documents**: every Pillar 3 report, results announcement and regulatory notice collected, with the extracted tables and a page reference for each figure used.
- **Peers**: the bank against its peer group on each metric, percentile bands, same treatment as PWLBtoday's LA Credit Metrics.

Export: a dated PDF "counterparty report" for one bank or a list, formatted for inclusion in a treasury report, with sources and method summary on the last page. This is the feature treasury teams will value most.

## 5. Design direction

Extend PWLBtoday's system rather than invent a new one: navy `#0a2540`, orange `#fd7e14` as the single accent, off-white `#f7f8fa` ground, Inter for text, IBM Plex Mono for every number and code, radii 6, 10 and 14, the existing shell (60px header, 220px collapsible sidebar).

What makes it distinctive rather than a generic dashboard:

- **Numbers first.** Tabular figures in Plex Mono at a size that can be read across a desk, generous whitespace, one accent only. No gauges, no traffic lights, no gradients on data.
- **Band ribbon.** The score is shown as a position on a ribbon relative to peers, not a lone big number. It reads at a glance and encodes uncertainty honestly.
- **Sparklines everywhere a number has history**, drawn to one shared scale per metric, with the endpoint emphasised.
- **Source trail.** Every figure has a hover and tap state showing document, page, reference date and extraction method. Trust is the product.
- **Data-age badges** in a muted style on every panel, turning orange when a source is late against its expected cadence.
- **Restraint in colour**: semantic states use one muted green for "improved", one muted red for "deteriorated", and PWLBtoday orange strictly for attention and actions. Bands use a five-step navy-to-slate scale, not red-amber-green.
- **Motion**: none on load; a single 200ms transition on tab change and chart hover; respects reduced-motion.
- **Mobile**: board becomes cards, profile keeps the score panel and metric strip as the first screen, tabs become a segmented control.
- Accessibility: WCAG AA contrast, keyboard navigation for tables and tabs, chart data available as tables.

Charts follow one system (area for price, line for ratios, bar for flows, dots for events), one grid style, one label style, built as inline SVG components so they render identically in the page and the PDF export.

## 6. Scoring method, version one

Public component (published, weights visible), each metric converted to a 0 to 100 percentile within the bank's peer group and against absolute thresholds:

| Pillar | Inputs | Weight |
|---|---|---|
| Capital | CET1 ratio and headroom over stated requirement; Tier 1 leverage ratio | 30 |
| Liquidity and funding | LCR, NSFR, loan-to-deposit where available | 20 |
| Asset quality | Non-performing or Stage 3 ratio, cost of risk, coverage | 20 |
| Profitability | Return on equity, cost-to-income, net interest margin trend | 15 |
| Stability and support | Size and systemic status, MREL headroom, sovereign context, disclosure timeliness | 15 |

Market overlay (private weights, raw values never displayed): agency rating composite, five-year CDS level and 30-day change where it exists (ICE settlement and DTCC prints), bond spread proxy otherwise, equity realised vol and drawdown. The overlay moves the public score within a bounded range (for example plus or minus 10 points) and the profile shows only the direction and size of the adjustment, labelled "market overlay".

Bands: A (80 to 100), B (65 to 79), C (50 to 64), D (35 to 49), E (below 35), with hysteresis so bands do not flicker. A back-test against Silicon Valley Bank, Credit Suisse, First Republic, Metro Bank 2023 and the 2020 dip is published on the Method page with the dates on which the score would have moved.

## 7. Data model

Postgres, long-format facts, everything time-stamped and sourced:

- `entity` (id, lei, name, short_name, country, type, group_id, tier, tickers, bond_isins, peer_group_id, active)
- `source_locator` (entity_id, source_type, url, link_pattern, cadence, fetch_method, last_success, next_expected)
- `document` (id, entity_id, source_type, url, sha256, reference_date, published_at, storage_key, status)
- `fact` (entity_id, reference_date, metric_code, value, unit, currency, basis, document_id, page, extraction_method, confidence, loaded_at)
- `metric_series` (materialised: entity_id, metric_code, reference_date, value, peer_median, peer_percentile)
- `rating` (entity_id, agency, rating_type, horizon, value, outlook, action_date, source_record_id) and `rating_action` (history with press release reference)
- `market_daily` (entity_id, date, close, currency, vol_30, vol_90, drawdown, source)
- `cds_daily` (entity_id, date, tier, level_bp, source, n_prints) and `cds_print` (raw DTCC rows)
- `news_item` (id, entity_id, published_at, source, url, title, snippet, primary_source flag) and `news_label` (item_id, event_type, direction, severity, confidence, model, reviewed_by)
- `score` (entity_id, date, public_score, overlay_adjustment, final_score, band, components json) with full history
- `pipeline_run` (source, started, finished, status, rows, message) feeding the Status page

Object storage for the raw documents (Cloudflare R2 free tier, ten gigabytes), keyed by sha256, retained forever.

## 8. Ingestion pipeline

A Python package, `bankcredit`, with one adapter per source behind a common interface (`discover`, `fetch`, `parse`, `validate`, `load`), run by GitHub Actions on schedules:

| Schedule | Jobs |
|---|---|
| Daily 06:00 UK | Yahoo closes and vol; ICE CDS snapshot; DTCC files; ESMA rating actions; news collectors (Google News RSS, GDELT, regulator RSS, FCA NSM, EDGAR); Claude labelling; score recompute; brief draft |
| Weekly | Pillar 3 discovery for every locator (new documents by hash); FCA NSM sweep; overdue-document alerts |
| Quarterly windows | FDIC financials; EBA hub pull; APRA and OSFI tables; Transparency Exercise backfill; SEC 17g-7 rating history refresh |
| On demand | Browser job on the Mac (or a small VPS) for the handful of bot-blocked sites: Lloyds, QNB, ADCB, Revolut, Investec, Norinchukin, State Street |

Extraction (revised 6 September 2026, no API key): KM1 tables are read from PDFs by a rules-based extractor (`bankcredit/extract/km1.py`) that keys each row on the template's row number, confirms it against the row label, reads the current-period column, and validates the result arithmetically (CET1 ratio against CET1 capital over RWA, leverage ratio against Tier 1 over exposure, LCR and NSFR against their components, ordering of the three capital ratios, plausible ranges). Clean results load at confidence 0.95; results with warnings load and show an "unverified" badge; failures go to `data/review/queue.json`. The queue is resolved on the maintainer's Mac by the repository skill `.claude/skills/counterparty-review/SKILL.md`, run in Claude Code under the subscription login, which also collects the handful of bot-blocked sites through the browser (`docs/local-run.md`). News labelling in phase two follows the same pattern: rules and source taxonomy in the pipeline, judgement calls in the local skill.

Freshness commitments shown on the Status page: regulatory data within three weeks of publication, ratings and market data daily, news within the day.

## 9. Front end and hosting (decided 6 September 2026)

Beta runs as a static site on GitHub Pages; once you are happy it is handed to your colleague for implementation in production PWLBtoday. That decides the architecture:

- **Static site generator.** A Python build step turns the data store into plain HTML pages (Board, one page per bank, Events, Brief, Method, Status) with inline SVG charts and a small amount of hand-written JavaScript for sorting, filtering and tab switching. No framework, no build toolchain beyond Python, so the pages can be re-templated into any production stack.
- **Design tokens** copied from PWLBtoday's `tokens.css` and the shell (60px header, 220px sidebar) reproduced as static markup, exactly as in the design canvas, so the handover is a matter of swapping the shell for the real one.
- **Data.** The pipeline writes Parquet (history) and compact JSON (per-bank and board payloads) into the repo; the build reads only the JSON. Raw documents are stored in the repo under `data/documents/` by hash while they fit, with Cloudflare R2 as the free overflow if the repo grows past a few hundred megabytes.
- **Jobs.** GitHub Actions runs the daily, weekly and quarterly schedules and commits results, then rebuilds and deploys Pages. A launchd job on your Mac (`scripts/mac/counterparty.sh`, weekdays 07:30) runs the same collector from your home connection, works the review queue through the local skill, fetches the bot-blocked sites (Lloyds, Investec, Handelsbanken plc, QNB, ADCB and the small societies) through the browser, and pushes the data; the Status page lists what is unverified or queued.
- **Accounts.** None in beta. Watchlists and saved views live in the browser (local storage); alerts and the exportable counterparty report wait for production, where PWLBtoday sign-in exists. The report exists in beta as a print stylesheet on the profile page.
- **Publishing rule.** Auto-publish with spot checks: everything publishes on schedule; figures that fail validation appear with an "unverified" badge rather than being held; band changes and failed extractions are listed on the Status page for you to review when convenient. The daily brief publishes as drafted, marked as machine-drafted until you have read it.
- **Name.** Counterparty, presented as a PWLBtoday tool from day one. No separate domain yet.

## 10. Phases

| Phase | Weeks | Deliverables | Exit criterion |
|---|---|---|---|
| 0 Foundations | 1 to 2 | Design canvas signed off; entity master for 130 names with locators; schema; storage; CI; adapter skeleton | A profile page renders from seeded data in the PWLBtoday shell |
| 1 UK and EU core | 3 to 8 | FDIC, EBA hub, Transparency Exercise adapters; UK Pillar 3 fetch and KM1 extraction with review queue; ESMA ratings; Yahoo prices; Board and Profile pages; Method page draft | Board shows all UK and EU names with dated KM1 metrics and ratings; extraction accuracy above 98 percent on a 50-document sample |
| 2 Signals and voice | 9 to 12 | News collectors and labelling; Events page; daily Brief; ICE and DTCC CDS; benchmark spread series (iTraxx Financials from DTCC, ICE BofA indices from FRED) with a bank-versus-sector divergence view; bank bond discovery (ESMA FIRDS) and daily pricing (Börse Frankfurt, LuxSE) feeding the overlay; score version one with overlay; alerts; PDF export | Brief published daily for two weeks with editor review; back-test published |
| 3 Global and polish | 13 to 15 | Australia, Canada, Asia, Gulf, US adapters; Compare and Peers; Status page; performance and accessibility pass; launch | All 130 names populated; Lighthouse and accessibility targets met; launch inside PWLBtoday |
| Ongoing | | Locator maintenance, review queue, method versioning, standalone site decision | |

### Phase one status, 6 September 2026

Built and running: the Pillar 3 collector with per-firm locators for 70 firms (`bankcredit/adapters/pillar3_locators.py`), the FCA NSM poll matched by LEI, the KM1 extractor, the documents table, the review queue, the local review skill and Mac runner, the unverified badge and the documents card on the Status page. The extractor handles the UK and EU KM1 (row numbers first), the Basel KM1 used by APRA, MAS and OSFI filers (including the OSFI layout with the row number after the label and quarter labels on a fiscal calendar), tables without row numbers, tables split over two pages, and headers in five date styles. Locators of kind `pattern` reach banks that publish at predictable addresses without a listing page (RBC, TD, CIBC, BMO, Scotiabank). After the first day 87 of 130 entities are scored, from 267 collected documents. Firms whose PDFs carry no extractable text (Coventry) or no KM1 table (TSB quarterlies, pre-2022 small-society documents, CBA) are queued for the local skill; Lloyds, the Gulf banks, OCBC, UOB, Macquarie and the overseas-owned UK subsidiaries without a scriptable page need the browser.

## 11. Risks

- The EBA hub route is unofficial. Mitigation: adapter isolation, per-bank zip download as fallback, watch for the promised bulk download.
- Yahoo endpoints break periodically. Mitigation: adapter with a second free source and a stale-data badge rather than a blank.
- PDF extraction errors reaching the page. Mitigation: validation rules, review queue, source trail so readers can check, confidence shown.
- Licensing of market inputs. Mitigation: ICE and agency data used only inside the overlay; only DTCC-derived index levels and public-register rating symbols displayed; terms reviewed before launch.
- Reliance on a score by professionals. Mitigation: method page, "information not advice" framing, no deposit recommendations, editor review of the brief.
- Scope creep into the US regional universe. Mitigation: universe fixed for release one; FDIC breadth comes later.

## 12. Decisions taken, 6 September 2026

1. Stack: static site on GitHub Pages for the beta, generated by Python; production implementation by your colleague in PWLBtoday afterwards.
2. Name: Counterparty (PWLBtoday). No standalone domain for now.
3. Accounts: none in beta; browser-only watchlists; alerts deferred to production.
4. Review: auto-publish with spot checks; unverified badges instead of holds; Status page lists what to look at.
5. Browser jobs: weekly launchd job on your Mac for the seven bot-blocked sites.

Phase 0 can start: entity master for the release-one universe, repository layout, data schema, the first adapters (FDIC, EBA hub, ESMA ratings, Yahoo prices), and the static site skeleton in the design canvas's markup.
