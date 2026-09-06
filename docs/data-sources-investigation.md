# Bank credit analysis platform: data source investigation

Date: 6 September 2026. Status: research only, nothing built.

Legend for each claim: **[V]** verified today by calling the endpoint or reading the document from a cloud (Claude Code on the web) container; **[S]** from documentation or search results; **[M]** from memory, unverified.

## 1. Summary

1. **US data is solved and free.** The FDIC BankFind API (new host `api.fdic.gov/banks`) returns Call Report ratios for all 4,235 insured banks with no key, about 50 days after quarter end, and already holds 30 June 2026 data. [V]
2. **European data has changed fundamentally since you last looked.** The EBA Pillar 3 Data Hub (P3DH) went live publicly on 26 January 2026. Every large and "other" EU/EEA institution now files quantitative Pillar 3 templates (KM1, OV1, CR1, LIQ1 and about 110 more) as XBRL-CSV to the EBA, which republishes them free on the European Data Access Portal (EDAP). There is no official API or bulk file yet, but the portal is a Power BI report with a public embed token, and I pulled KM1 for 224 banks at end-2025 in four seconds with a 60-line Python script from this container. Data is loaded through the 30 June 2026 reference date. [V]
3. **UK remains the hard region.** No public bank-level regulatory data exists; Pillar 3 stays as PDFs on each firm's website, annual for building societies. PDF extraction with an LLM is the only route. [V/S]
4. **Other global banks:** Canada (OSFI) and a handful of European national supervisors publish bank-level tables; Japan, Australia, Switzerland, Hong Kong and Singapore are PDF-per-bank. For listed banks anywhere, SEC EDGAR (US filers) and cheap fundamentals vendors (EODHD) cover accounting data but not Pillar 3. [V/S]
5. **Market inputs:** equity prices and realised vol are free (Yahoo endpoints work from the cloud, including LSE, Xetra, Paris, SIX, Tokyo tickers). Options-implied vol is free only for US-listed names and ADRs. **Single-name bank CDS is not obtainable at individual budget**; bond-price spreads, iTraxx Financials and equity-implied distance-to-default are the realistic proxies. Ratings history is free and legally clean via the SEC Rule 17g-7 XBRL files and the ESMA European Rating Platform. [V]
6. **News:** free discovery via Google News RSS and GDELT, plus regulator and SEC feeds; EODHD at about £16 a month adds full-text, ticker-tagged global news; Claude Haiku 4.5 classifies about 1,000 headlines for under $0.50. [V]
7. **Scheduling:** Claude Code routines work but are the wrong tool for deterministic fetches. Recommended split: GitHub Actions cron running plain Python for ingestion (free, no Mac needed), Claude API calls inside that pipeline for PDF extraction and news classification, and a Claude Code routine only for the weekly "review anomalies and write commentary" step. From this cloud container, every data endpoint that matters was reachable; the blocked hosts (FT, Bloomberg, Reuters, S&P Global, ffiec.gov/npw, SEC full-text search) are bot-protected regardless of where you run. [V]

## 2. Starting point

Both repositories (`bankCredit`, `BuildingQuotes`) contain only an initial README. Nothing from the previous platform survives here, so this is greenfield. `BuildingQuotes` appears unrelated to this project.

## 3. United States

### 3.1 FDIC BankFind Suite API (primary) [V]

- Base: `https://api.fdic.gov/banks/` with endpoints `institutions`, `financials`, `summary`, `history`, `failures`, `locations`, `demographics`, `sod`. The old `banks.data.fdic.gov/api` host now 301-redirects.
- No key required. Rate limit header shows 120 requests per window. `limit` max 10,000 per call with `offset` paging. Elasticsearch-style `filters`, `fields`, `sort_by`.
- Lag: Q2 2026 (30 June) financials index built 19 August 2026, about 50 days after quarter end. Institution structure data refreshes nightly.
- Field dictionary: `https://api.fdic.gov/banks/docs/risview_properties.yaml` (2,378 fields) and sibling YAML files per endpoint.
- Verified credit fields (returned live for Wells Fargo, CERT 3511, 30 June 2026):

| Need | Field codes |
|---|---|
| CET1, Tier 1, total risk-based ratios | `RBCT1CER`, `IDT1RWAJR`, `RBCRWAJ`; leverage `RBC1AAJ`; RWA `RWAJ` |
| Noncurrent loans, NCOs | `NCLNLS`, `NCLNLSR`, `NTLNLS`, `NTLNLSR`, `NTLNLSQ` |
| Reserves and provisions | `LNATRES`, `LNLSRES`, `ELNATR` |
| Profitability | `ROA`, `ROE`, `NIMY`, `EEFFR`, `NETINC` |
| Deposits | `DEP`, `DEPINS`, `DEPUNINS`, `BRO` (brokered) |
| Liquidity | `CHBAL`, `SC`, `SCAF`, `SCHA`, `IDLNCORR` |
| HTM unrealised loss | derive `SCHF` minus `SCHA` |
| CRE concentration | derive from `LNRECONS`, `LNRENROT`, `LNREMULT` over Tier 1 plus reserves |

- Bulk history: FDIC FOIA RIS bulk download (CSV and SAS bundles, 1984 to 2026).

### 3.2 FFIEC Central Data Repository [V]

- Bulk Call Report and UBPR downloads with no login at `cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx`, tab-delimited or XBRL, updated about 46 days after quarter end (a week ahead of FDIC).
- The SOAP web service was retired on 28 February 2026. The replacement REST API (`ffieccdr.azure-api.us/public`) needs a free account and a 90-day JWT that must be regenerated manually in the portal. The `ffiec-data-connect` Python package (v3.0.0, April 2026) wraps it and is actively maintained.
- UBPR peer group definitions changed in February 2026, which breaks naive peer time series.

### 3.3 Holding companies (FR Y-9C) [V]

- NIC Financial Data Download has quarterly Y-9C zips since 2000, but every `ffiec.gov/npw` URL returns 403 with a JavaScript challenge to scripts, from this container and from the research agent. Requires a real browser session or manual download. Chicago Fed legacy CSVs stop at 2021 Q1.
- For listed holding companies, SEC EDGAR XBRL `companyfacts` and `frames` APIs work from the cloud with a compliant User-Agent (mandatory, 403 without it) at 10 requests per second. Tags such as `TierOneRiskBasedCapitalToRiskWeightedAssets` and `Deposits` are present, but CET1 ratio, nonaccrual and uninsured deposits usually sit in company extension taxonomies, so cross-bank comparability is poor. Use FDIC for ratios and EDGAR for group-level accounting items.

### 3.4 US Pillar 3, stress tests, FFIEC 101/102 [V/S]

- Pillar 3 applies to institutions with at least $50bn assets (12 CFR 217.61-63, quarterly key tables). No central repository; PDFs on each bank's investor relations site.
- A March 2026 interagency proposal would replace the advanced approaches with a single expanded risk-based approach for Category I and II firms. Not final; expect the tables to change.
- Fed stress test results are a clean CSV: `federalreserve.gov/supervisionreg/files/public_results_DFAST_2026.csv`, keyed by RSSD ID, all years 2013 to 2026.

## 4. European Union and EEA

### 4.1 EBA Pillar 3 Data Hub [V]

What it is:
- Mandated by CRR3 (Regulation 2024/1623 Article 434) with the technical standard in Commission Implementing Regulation 2026/722. Institutions submit quantitative templates as XBRL-CSV (DPM 4.1, moving to 4.2) and qualitative sections as PDF; the EBA republishes both unchanged.
- Scope today: large institutions at highest EEA consolidation, large subsidiaries, and "other" institutions at highest EEA level. The model holds 1,494 entities across 30 countries (Germany 381, Italy 136, France 102, ...). Small and non-complex institutions are not in scope yet; a June 2026 discussion paper proposes the EBA computing their disclosures from COREP/FINREP.
- Timeline: transitional reference dates 30 June, 30 September and 31 December 2025 were back-filled after onboarding; public go-live 26 January 2026; steady state from the March 2026 reference date with a four-month submission deadline. The model already contains accepted instances dated 30 June 2026.
- 117 templates. KM1 key metrics is `K_61.00`; KM2 (MREL) is `K_90.01`; CR6 is `K_26.00`. Values are converted to EUR at ECB rates; ratios are decimals.

Access:
- Public URL: `https://edap-public.eba.europa.eu/Report/index/MTE1` (note: `p3dh.eba.europa.eu` is not the public host; it fails). Anonymous, no registration. Session cookie required; plain curl without a cookie jar loops on redirects.
- Official download options (from the January 2026 EDAP user guide): per-institution zip of the original XBRL-CSV and PDF submissions, and Power BI "Export data" capped at 30,000 rows CSV or 150,000 rows XLSX. The guide says bulk download "should" come in a future release. There is no REST API, no swagger, no documented bulk file.
- Unofficial programmatic route, proven today: the page inlines a public Power BI embed token (rotates roughly hourly). With it you can POST semantic queries to the Power BI cluster (`wabi-west-europe-d-primary-redirect.analysis.windows.net/explore/querydata`) against a star schema (`fact_Value`, `dm_Entity` with LEI, `dm_ReportInstance` with reference date and `IsCurrent`/`IsAccepted`, `dm_Template`, `dm_Table`, `dm_Row`, `dm_Column`, `dm_TableKey`). A public notebook (`github.com/at621/snippets`, `pillar3_hub_overview.ipynb`) documents the encoding. My test script is in `research/p3dh_probe.py`. Each query returned in 1 to 4 seconds; a 30,000-fact window cap applies per query, so page by country or template row.
- Risks: unsupported and could change without notice; Power BI rate limits; resubmissions coexist (filter on `IsCurrent = 1` and `IsAccepted = 1`); some entities have several versions; open tables need the key dimension.
- Licence: EBA legal notice allows reproduction with source acknowledgement.

Implications:
- UniCredit already states that from 31 March 2026 its Pillar 3 is published only on the hub, and Santander has uploaded its history there. Expect IR-site PDFs to thin out for EU banks. Keep PDF scraping only for pre-2025 history, early releases (banks often post with results, weeks before the hub deadline), and non-EEA groups.

### 4.2 EBA EU-wide Transparency Exercise [V]

- Annual, about 120 banks, published early December with four reference quarters. 2025 edition CSVs (no auth) at `eba.europa.eu/assets/TE2025/Full_database/883401/{tr_cre,tr_mrk,tr_sov,tr_oth}.csv` with a data dictionary. Long format keyed by LEI, period, item code, EUR millions.
- Best free source of clean annual history from 2013 to 2025 (capital, RWA, P&L, NPE, sovereign exposures). The EBA says the exercise transitions to P3DH from the June 2025 reference date, so treat it as a history backfill rather than an ongoing feed.

### 4.3 ECB [V]

- Supervisory Banking Statistics and the Data Portal SDMX datasets (`SUP`, `CBD2`) are aggregates by country and bank category, not bank-level. Useful as benchmarks. Data API at `data-api.ecb.europa.eu/service/data/SUP?...` accepts `text/csv` or `application/json`; structure queries need XML. `application/vnd.sdmx.data+csv` returns 406.
- One bank-level exception: Pillar 2 requirements per significant institution (about 150 banks, xlsx, updated February 2026) at `bankingsupervision.europa.eu/activities/srep/pillar-2-requirement`.

### 4.4 National supervisors with bank-level tables [V/S]

| Country | Source | Notes |
|---|---|---|
| Switzerland | FINMA key metrics for banks | Annual Excel, capital and liquidity per bank, published about July |
| Sweden | Finansinspektionen capital requirements | Quarterly per bank, PDF and some Excel |
| Denmark | Finanstilsynet key figures database | Half-year and annual Excel per institution |
| Netherlands | DNB individual bank key data | Dashboard, consent-based |
| Spain | Banco de España public statements | Entity-by-entity, PDF, Excel, CSV |
| Norway | Finanstilsynet | Sample-based, no bank-level portal found |
| Germany, Italy, France | Bundesbank, Banca d'Italia, ACPR | Bank-level microdata is researcher-access only |

## 5. United Kingdom

### 5.1 No public bank-level regulatory data [V/S]

- COREP and FINREP returns are confidential under FSMA section 348. Nothing at firm level is exposed by the Bank of England or the PRA.
- The Bank of England Statistical Interactive Database is aggregate only. The working CSV endpoint is `bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&SeriesCodes=...&CSVF=TN&UsingCodes=Y` (up to 300 series per call, no auth). Useful for sector context (lending, deposits, sector capital).
- Bank Capital Stress Test results (seven firms: Barclays, HSBC, Lloyds, Nationwide, NatWest, Santander UK, Standard Chartered) are published in the Financial Stability Report as PDF and HTML tables, with firm low-point CET1 and leverage ratios. Extraction needed.
- Firm-specific MRELs: annual HTML table at `bankofengland.co.uk/financial-stability/resolution/mrels-2026` (12 bail-in firms and 6 transfer firms, MREL as percent of RWA and leverage exposure). The Bank intends to stop publishing this from 2027 once firms disclose UK KM2 and MREL templates themselves.
- PRA policy statement PS11/26 (March 2026) adds UK KM2 and MREL templates from the 31 December 2026 reference date but keeps disclosures as firm-published documents. There is no UK equivalent of the EBA hub and none is planned.

### 5.2 UK bank Pillar 3 PDFs [V]

All UK banks use the UK KM1 key metrics template, so one KM1 extractor covers the universe. None publish machine-readable Pillar 3; everything is PDF and URL patterns change each period. The FCA National Storage Mechanism (`data.fca.org.uk/#/nsm`) is a stable secondary location for listed groups.

| Firm | Cadence | Location |
|---|---|---|
| Barclays PLC, Barclays Bank PLC, Barclays Bank UK PLC | Quarterly | home.barclays results announcements (for example `Q126-BPLC-Pillar-3.pdf`) |
| HSBC Holdings, HSBC Bank plc, HSBC UK Bank | Quarterly for Holdings, annual and interim for subsidiaries | hsbc.com investors results |
| Lloyds Banking Group, Lloyds Bank, Bank of Scotland | Quarterly | lloydsbankinggroup.com investor PDFs |
| NatWest Group, NWH, NWB, RBS, Coutts, NatWest Markets | Quarterly | investors.natwestgroup.com |
| Standard Chartered | Quarterly | sc.com |
| Santander UK Group Holdings and Santander UK plc | Quarterly, as "Additional Capital and Risk Management Disclosures" | santander.co.uk |
| Nationwide (group and sub-group), Virgin Money UK sub-group | Quarterly summary, semi-annual, annual (March year end) | nationwide.co.uk, virginmoneyukplc.com |
| TSB | Semi-annual large subsidiary disclosure | tsb.co.uk |
| Co-operative Bank, Metro Bank | Annual plus half-year | own sites |
| Monzo, Starling, Atom, Revolut | Annual (March year ends for the first three) | own sites |
| OSB Group, Paragon, Close Brothers, Shawbrook, Aldermore | Annual plus interim (varied year ends: September, July, June) | own investor sites |

### 5.3 Building societies [V]

- Every BSA member publishes Pillar 3 on its own site. Quarterly: Nationwide, Yorkshire, Coventry, Leeds. Semi-annual plus annual: Skipton. Annual only, some with interims: Principality, West Brom, Newcastle, Nottingham and all smaller societies. Newcastle hosts its PDFs on an unstable content-delivery domain.
- BSA sector information page (`bsa.org.uk/statistics/sector-info-performance/sector-information`) has per-society key statistics as Excel for 2017/18 to 2025/26 (assets, liabilities, liquidity, members, branches) but no per-society CET1. Capital must come from Pillar 3 or annual reports.
- FCA Mutuals Public Register (`mutuals.fca.org.uk`) holds statutory accounts and annual returns. Document downloads (`/Documents/Download/{id}`) work without auth from the cloud, but IDs are opaque so the society page must be scraped to find them. Building societies do not file at Companies House.

### 5.4 Companies House [V/S]

- Free API key, about 600 requests per five minutes. Filing history and the Document API return PDFs and iXBRL. Monthly bulk accounts zips cover all electronically filed accounts. UK bank plcs file full IFRS accounts with limited detail tagging: fine for entity totals, useless for RWA or CET1.

## 6. Other global banks

| Country | Source | Bank-level? | Format and cadence |
|---|---|---|---|
| Canada | OSFI Financial Data for Banks, now on open.canada.ca as CSV (`banks_monthly_m4.csv`, `banks_quarterly_ba.csv` capital adequacy, data dictionary) | Yes | Monthly balance sheet on the 15th, quarterly capital about 7 to 8 weeks after quarter end. The OSFI page loaded from the cloud, but the CSV downloads were rejected by the open.canada.ca firewall; may need a non-datacentre address [V] |
| Australia | APRA quarterly ADI statistics, "ADI centralised publication" XLSX (March 2013 to March 2026) | Yes, capital and liquidity ratios per entity | Quarterly, about 3-month lag. Reachable from the cloud [V] |
| Japan | Japanese Bankers Association "Financial Statements of All Banks" Excel zip per bank | Yes, balance sheet and P&L only | Semi-annual. Capital ratios are in each bank's Japanese-language Basel PDFs [V] |
| Brazil | Banco Central IF.data OData API (`olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata/...`) | Yes, including capital and Basel ratios | Quarterly JSON, no auth, about 3-month lag, Portuguese labels [V] |
| India | RBI Statistical Tables relating to Banks (DBIE portal) | Yes, CRAR and NPAs per bank | Annual Excel, about 9-month lag [S] |
| Mexico | CNBV Portafolio de Información | Yes, including capitalisation index | Monthly Excel and CSV, site flaky from the cloud [S] |
| Hong Kong | HKMA Open API (aggregate) plus each institution's Banking Disclosure statements | PDF per bank | HKMA API works without auth but is aggregate [V] |
| Singapore | MAS statistics (aggregate); DBS, OCBC, UOB Pillar 3 PDFs | PDF per bank | Quarterly [S] |
| Switzerland | FINMA annual key metrics Excel; SNB cube API (aggregate) | Yes (FINMA, annual) | Annual, about July [V] |
| China | NFRA quarterly aggregates | No | Use HKEX and Shanghai filings per bank [S] |
| Supranational | BIS SDMX v2 (works), IMF FSI via the new `api.imf.org/external/sdmx/2.1` (works, no key), World Bank GFDD (stale, data to 2021) | No | Country-risk overlay only [V] |

Commercial vendors with real bank-level global coverage (S&P Capital IQ Pro with SNL, Moody's BankFocus, Fitch Connect, Bloomberg, LSEG) are five-figure annual contracts and not individual-friendly. Cheap fundamentals vendors (EODHD at about $100 a month for the all-in-one tier, Financial Modeling Prep, Alpha Vantage) give listed-bank IFRS or GAAP statements but not RWA, CET1 or NPL lines, and omit unlisted UK challengers and building societies.

No open-source project maintains a global Pillar 3 or KM1 dataset. You would be building the first one.

## 7. Market inputs (kept private, used as score weights)

### 7.1 Equity prices and volatility [V]

- Yahoo Finance `query2.finance.yahoo.com/v8/finance/chart/{ticker}` returned prices from this container for BARC.L, HSBA.L, BNP.PA, DBK.DE, UBSG.SW, 8306.T, CBA.AX, RY.TO. Unofficial, personal use tolerable, no redistribution. `yfinance` v1.7.0 (August 2026) is actively maintained but breaks whenever Yahoo changes. Realised vol is straightforward from daily closes.
- Options-implied vol: Yahoo option chains need the cookie-and-crumb dance and cover US listings and ADRs only (HSBC, Barclays, Deutsche, UBS, MUFG, Santander, ING and the US banks). Cboe's delayed options JSON (`cdn.cboe.com/api/global/delayed_quotes/options/JPM.json`) worked from the cloud with no key. No free bank-sector IV index exists; VIX from FRED CSV is the free macro overlay. Proper IV surfaces cost about $99 to $199 a month (ORATS).
- Paid but cheap global end-of-day equities: EODHD All-World at $19.99 a month covers every exchange and includes the news API.

### 7.2 CDS spreads [V/S]

- No affordable programmatic single-name bank CDS source exists for an individual. S&P Global (ex-Markit), Bloomberg, LSEG and ICE are institutional contracts. investing.com blocks bots; worldgovernmentbonds.com has sovereign CDS only.
- Workable proxies, all free: bond prices from Börse Frankfurt's unofficial quote JSON (senior, Tier 2 and AT1 ISINs per bank, then spread to swap); FINRA TRACE for USD bonds (web only); iTraxx Senior and Sub Financials index levels as a sector factor; equity-implied distance-to-default from vol and leverage.

### 7.3 Credit ratings [V/S]

- SEC Rule 17g-7(b) XBRL rating histories: every registered agency (Moody's, S&P, Fitch, DBRS, KBRA and others) must publish its full rating history monthly. Free, bulk, and the cleanest legal footing. S&P's disclosure page returned 403 to scripts today; Moody's page loads. A community mirror (`ratingshistory.info`) serves CSVs but check freshness.
- ESMA European Rating Platform: all EU-registered agency ratings and rating actions since July 2015, updated daily. The Solr backend at `registers.esma.europa.eu/solr/esma_registers_radar/select` is reachable and holds about 10 million action records with rating value, action type, date and press release link. Undocumented but public.
- Do not scrape Moody's, S&P or Fitch websites: their terms forbid bots and database building. The two sources above make that unnecessary.

## 8. Bank news relevant to credit

### 8.1 Free discovery layer [V]

- Google News RSS search (`news.google.com/rss/search?q="Barclays"+capital&gl=GB`) works and covers global banks by name. Headline, source and redirect URL only.
- GDELT DOC 2.0 API works, global and multilingual, but responses took 15 seconds and the service asks for one request every 5 seconds. Title and snippet only.
- Bing News API was retired in August 2025.

### 8.2 Primary sources, higher signal [V]

Reachable RSS or feeds from the cloud: Federal Reserve press (all), FDIC (`fdic.gov/rss.xml`), OCC news and enforcement, ECB Banking Supervision press, EBA, Bank of England and PRA publications, FINMA, FCA. ACPR blocks bots; BaFin has an RSS index page. SEC EDGAR latest-filings Atom feed (8-Ks) works with a compliant User-Agent, but the full-text search host `efts.sec.gov` returned 403 from this container. London Stock Exchange RNS is a paid feed; `lse.co.uk/rss/news.xml` is a free substitute and Investegate company pages load. Moody's and Fitch RSS endpoints return empty; ESMA rating actions with press-release links are the practical rating-action feed.

### 8.3 Paid full text and classification [V]

- EODHD ($19.99 a month) is the only cheap option with full article bodies and non-US ticker tagging. Marketaux ($29 to $99) is a reasonable entity-tagged mid tier. NewsAPI's free tier is dev-only.
- Classification: keyword pre-filter (capital raise, AT1, write-down, provision, downgrade, enforcement, deposit outflow, liquidity, resolution, bail-in, merger, CEO, fraud, fine, stress test), then Claude Haiku 4.5 with a fixed JSON label schema (event type, direction, severity, entity). Cost about $0.35 to $0.45 per 1,000 headlines, roughly half via the Batch API; Sonnet 5 about $1. At 1,000 headlines a day that is about $12 a month on Haiku.

## 9. Scheduling: Claude Code routines versus alternatives

### 9.1 What was verified about this cloud environment [V]

- Outbound HTTPS from the container goes through an Anthropic proxy with no published egress IP. Every data source that matters worked: FDIC, FFIEC CDR bulk, SEC EDGAR data APIs, Bank of England database, EBA and EDAP, ECB, OSFI, APRA, Yahoo, Cboe, FRED, GDELT, Google News, all regulator RSS feeds, ESMA registers, GLEIF.
- Blocked or bot-challenged: FT, Bloomberg, Reuters, S&P Global, FCA register API (needs key anyway), `ffiec.gov/npw`, `efts.sec.gov`, investing.com, ACPR, Stooq. These block scripts from residential IPs too, so a Mac does not help much except for `ffiec.gov/npw`, where a real browser session is the fix.
- Headless Chromium could not connect through the proxy in my attempts (connection reset), so browser-driven scraping in routines is unproven here. Everything above was done with plain HTTP.

### 9.2 Options [S, docs at code.claude.com/docs/en/routines]

| Option | Reliability | Network | Cost | Best for |
|---|---|---|---|---|
| GitHub Actions cron plus Python | High | Azure runner IPs, occasionally throttled by Yahoo; 5-minute minimum, 6-hour job limit | Free for a public repo, 2,000 minutes a month private | All deterministic fetch, parse, store |
| Claude Code routine (cloud) | Medium: a fresh agent session each run, non-deterministic | Environment's network policy; default "trusted" allowlist must be widened to your data hosts, or set to full | Consumes subscription usage; hourly minimum | Judgement steps: review new data, write commentary, triage anomalies |
| Mac launchd plus `claude -p` or cron | Low unless the Mac stays awake | Home ISP IP, best reputation with bot-protected sites | Subscription or API usage | Browser-driven scrapes (NIC, bank IR PDFs) if needed |
| Small VPS | High | Fixed data-centre IP | About $5 a month | Alternative to GitHub Actions if runtime or IP reputation becomes a problem |

Recommendation: Python ingestion on GitHub Actions (or a VPS) writing to a small Postgres (Neon or Supabase free tier) or to Parquet files committed to the repo; Claude API calls inside that pipeline for PDF table extraction and news labelling; one Claude Code routine, weekly, that reads the fresh data and drafts the credit commentary and anomaly list. Use the Mac only for the few browser-gated sources, if at all.

## 10. Proposed architecture (for discussion, not built)

1. **Entity master**: LEI-keyed bank list (GLEIF API works from the cloud), with FDIC CERT, RSSD ID, SEC CIK, tickers, ISINs for bonds, country, tier (G-SIB, D-SIB, other), and a source map per entity.
2. **Ingestion adapters**, one per source, each idempotent and producing a common long-format fact table (entity, reference date, metric, value, currency, source, as-of timestamp):
   - FDIC financials (quarterly, all US banks; subset to a watch list for the UI).
   - P3DH Power BI queries (KM1, KM2, OV1, CR1, LIQ1, LIQ2, CC1, LR2) plus per-bank original zips as the audit copy.
   - Transparency Exercise CSVs (one-off backfill).
   - Fed DFAST CSV (annual), ECB P2R xlsx (annual), FINMA and Nordic supervisors (annual).
   - UK and other PDF Pillar 3 reports: fetch, hash, extract KM1-style tables with Claude (Sonnet 5 for tables, Haiku for triage), store with page references for audit.
   - Market: daily closes (Yahoo or EODHD), realised vol, ADR implied vol, bond quotes, iTraxx level.
   - Ratings: 17g-7 monthly files and ESMA daily actions into a private table.
   - News: RSS and GDELT collectors, keyword filter, Claude labels, dedupe by URL and title similarity.
3. **Scoring**: transparent public component (capital, asset quality, liquidity, profitability, trend) and a private weighting layer (vol, spread proxy, ratings) that only affects the final score and never surfaces raw values.
4. **Presentation**: static site or lightweight app reading the fact table; commentary drafted by the weekly routine and reviewed by you before publishing.

## 11. Decisions needed from you

1. Universe: how many banks in the first cut? Suggest the roughly 80 EU/EEA large institutions, top 50 US by assets plus any watch list, the 10 UK banks and 8 largest building societies, and 20 other global names.
2. Whether to rely on the unofficial P3DH Power BI route now (fast, complete, could break) or wait for the EBA's promised bulk download and use per-bank zip downloads meanwhile.
3. Budget for EODHD (about £16 a month) versus free-only sources for news and prices.
4. Storage: Parquet in the repo (simple, versioned, fine for tens of megabytes) versus a hosted Postgres.
5. Whether the private inputs (vol, spreads, ratings) live in the same repo (private repo required) or a separate private store.

## Appendix A: reachability from this cloud container

Tested with plain HTTPS from the Claude Code on the web container on 6 September 2026. "OK" means an HTTP 200 with the expected payload.

| Source | Result |
|---|---|
| FDIC BankFind (`api.fdic.gov/banks`) | OK after 301 from old host; data through 2026-06-30 |
| FFIEC CDR bulk pages | OK |
| FFIEC NIC (`ffiec.gov/npw`) | 403 JavaScript challenge |
| SEC EDGAR `data.sec.gov` XBRL APIs | OK with User-Agent |
| SEC full-text search `efts.sec.gov` | 403 |
| Fed press RSS, OCC RSS, FDIC RSS | OK |
| EBA site, Transparency Exercise CSVs, EBA RSS | OK |
| EDAP Pillar 3 Data Hub (`edap-public.eba.europa.eu`) | OK with cookie jar; anonymous embed token issued; Power BI queries OK |
| `p3dh.eba.europa.eu` | Not reachable (not the public host) |
| ECB Data Portal SDMX | OK with `text/csv` or XML Accept headers |
| ECB Banking Supervision RSS | OK |
| Bank of England database CSV, RSS | OK |
| BSA statistics, FCA Mutuals Register document download | OK |
| Companies House API | 401 (needs free key), web pages OK |
| FCA Register API | 403 (needs key) |
| OSFI page | OK; open.canada.ca CSV downloads blocked |
| APRA statistics | OK |
| HKMA Open API | OK (aggregate) |
| Brazil BCB IF.data OData | OK |
| BIS SDMX v2, IMF SDMX 2.1 | OK |
| ESMA registers (rating platform, Solr) | OK |
| GLEIF LEI API | OK |
| Yahoo Finance chart endpoint (US, LSE, Xetra, Paris, SIX, Tokyo, ASX, TSX) | OK |
| Yahoo options | 401 without cookie and crumb; OK with them |
| Cboe delayed options JSON | OK |
| FRED CSV | OK |
| Stooq | Blocked by JavaScript challenge |
| GDELT DOC API | OK, 15-second response |
| Google News RSS | OK |
| Moody's site, Fitch site, DBRS, Scope, S&P press site | Pages load; RSS feeds empty; S&P ratings disclosure 403 |
| Reuters | 401 |
| FT, Bloomberg, S&P Global, investing.com, ACPR | 403 |
| London Stock Exchange news page, Investegate | OK (page loads; official RNS feed is paid) |
| EODHD, Marketaux, NewsAPI, Twelve Data, FMP, Finnhub | Reachable; 401 or 403 without a key as expected |
| Alpha Vantage | OK with demo key |

## Appendix B: P3DH proof of concept

See `research/p3dh_probe.py`. Run it to list entities, templates and instances and to pull KM1 facts for a reference date. It needs only `requests`.

## 12. Follow-up: UK Pillar 3 collection and free ratings coverage

Added 6 September 2026 in answer to three questions: can UK Pillar 3 PDFs be collected automatically, does the FCA hold them centrally, and are free ratings global or US-only.

### 12.1 FCA National Storage Mechanism [V]

- The NSM has an undocumented but stable JSON search API behind the Angular app: `POST https://api.data.fca.org.uk/search?index=nsm-search`. The body shape is the app's own: `{"from":0,"size":50,"sortorder":"desc","criteriaObj":{"criteria":[{"name":"headline","value":"Pillar 3"}],"dateCriteria":[{"name":"publication_date","value":{"from":"2025-01-01T00:00:00Z","to":"2026-09-06T23:59:59Z"}}]}}`. Headline is a plain string, dates are ISO with a trailing Z, and the response is Elasticsearch-style hits with company, LEI, headline, type, source, publication date and a download link. Download links resolve under `https://data.fca.org.uk/artefacts/` and direct uploads come back as real PDFs.
- Coverage is the problem, not access. Searching headlines for "Pillar 3" from January 2025 to today returns 62 documents. UK filers: Standard Chartered (every quarter, PDF plus RNS notice), NatWest Group (RNS notice only), Barclays Bank PLC (RNS notice only, pointing to the Barclays website), Paragon (half-year PDF), Close Brothers (annual PDF), Skipton Building Society (annual PDF). The rest are Australian and South African banks with London listings (ANZ, Westpac, CBA, Bendigo, Standard Bank) and one BBVA filing.
- Missing entirely: HSBC, Lloyds, Santander UK, Nationwide, Virgin Money, TSB, Co-op, Metro, Monzo, Starling, OSB, Shawbrook, Aldermore, Atom and every building society other than Skipton. Pillar 3 is not "regulated information" under the Disclosure Guidance and Transparency Rules, so filing it on the NSM is voluntary.
- Useful anyway: the RNS notices that do get filed contain the headline metrics in plain text (Barclays Bank PLC on 28 April 2026: CET1 12.3%, LCR 147.4%, UK leverage 5.4%), which gives an early, machine-readable signal for those firms before any PDF parsing.
- Conclusion: use the NSM as one collector among several, not as the central source. Poll it weekly by headline keyword and by LEI for the firms that do file.

### 12.2 Automating collection from bank websites [V]

See the firm-by-firm table in section 12.4. In summary, the large banks (HSBC, NatWest, Standard Chartered, Metro, OSB, Monzo) expose Pillar 3 PDF links in server-rendered HTML that a plain HTTP fetch can parse; several others (Barclays, Lloyds, Nationwide, most building societies) need the exact current page URL or render their document lists with JavaScript; a few (Paragon, Starling, Shawbrook) block or reset scripted requests and need a headless browser or a residential connection.

The workable design is a per-firm "locator" record (page URL, link pattern, cadence, fallback NSM query) plus a generic fetcher that hashes each PDF, stores it with its reference date, and raises an alert when a firm's expected publication is overdue. Expect to touch the locator for each firm about once a year when its site is reorganised.

### 12.3 Ratings: free and global, with two caveats [V]

- ESMA European Rating Platform. Every rating issued or endorsed into the EU by an EU-registered agency is in the register, and because Moody's, S&P, Fitch, DBRS, KBRA, Scope and JCR all endorse their global ratings into the EU, coverage is global, not European. Verified today via the Solr endpoint (`registers.esma.europa.eu/solr/esma_registers_radar/select`): current issuer-level ratings for Nationwide (Fitch AA-, S&P A+, Moody's A1 deposits, DBRS A high), Barclays Bank PLC (Fitch AA-, S&P A+, KBRA A+, DBRS A high), Coventry, Yorkshire and Skipton building societies (Fitch and Moody's), Starling (Moody's Baa2, June 2026), OSB Group (Fitch BBB, Moody's Baa2), Deutsche Bank, JPMorgan Chase, Mitsubishi UFJ (including JCR) and Commonwealth Bank of Australia. Monzo has no rating in the register.
- Query notes: filter `type_s:parent` for the current state and `type_s:child` for the action history; `ratedObjectCode:ISR` gives issuer-level ratings and `INT` gives individual bonds; exclude `ratingStatusLabel:Withdrawal`; `issuerRatingName` distinguishes deposit, issuer, counterparty and resolution counterparty ratings; `racValidityDatetimeStr` is the action date. Child records carry press-release links. The register updates daily.
- SEC Rule 17g-7(b) rating history files. Each US-registered agency must publish XBRL histories of all its ratings monthly, and these also cover global issuers because the registered entity is the group. The Moody's financial-institutions file from the community mirror at ratingshistory.info (88 MB CSV, July 2024 snapshot) contains Barclays (10,563 rows), Lloyds, Nationwide, Coventry, Yorkshire, Skipton, Deutsche Bank, Mitsubishi UFJ, Commonwealth Bank, Royal Bank of Canada and Santander. Caveats: the agencies' own download pages (Moody's `ratings.moodys.com/sec-17g-7b`, Fitch, S&P `disclosure.spglobal.com`) are JavaScript apps or return 403 to scripts, so fetching the fresh monthly files needs a browser session; the mirror's freshness must be checked before relying on it.
- Recommendation: ESMA for current ratings and daily actions across all agencies, with the 17g-7 files as the long-history backfill. Both are public regulatory disclosures, so storing them privately for scoring is clean. Do not scrape the agencies' commercial sites.
