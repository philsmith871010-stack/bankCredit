# What "unverified" should mean for the score

A decision to make, with the numbers under it. Nothing here has been changed: the site behaves
today as described under "What happens now".

## What the mark means

A figure is marked *unverified* when the extractor read it out of a PDF and one of its own
cross-checks did not pass. Across the 208 documents carrying the mark, the reasons are mundane:

| times | reason |
|---:|---|
| 55 | the bank publishes no LCR row at that reporting level |
| 44 | the bank publishes no leverage row |
| 38 | a column header's date disagrees with the quarter expected |
| 29 | no period date in the template header, so the expected date was used |
| 28 | month and year split across two header lines |
| 28 | the table labels its rows without numbering them |

None of that says the number is wrong. It says it was not confirmed twice.

## What happens now

Unverified figures **do** feed the score. Confidence is used only to choose between two competing
readings of the same quarter — the higher-confidence one wins — never to exclude. Where an
unverified reading is the only one held for a quarter, it scores.

The scale: 4,119 of 7,863 PDF-read figures (52%) carry the mark, across 65 entities. But that
number overstates the exposure, because most of those are older quarters that no longer drive
anything. What matters is the newest capital reading, and there **10 of the 118 scored banks**
rest on an unconfirmed figure.

## The three options

### A. Leave it (what happens today)
A marked figure beats no figure. The mark is visible on the profile tile, the document is one
click away, and the glossary explains it. Nothing changes.

### B. Exclude unverified figures from scoring
Ten banks lose their newest capital reading. Seven of them fall out of the scored universe
altogether — five because no confirmed reading of that metric exists at any date, two because the
confirmed reading they fall back to is older than the method's 550-day limit:

| bank | score today | band | if excluded |
|---|---:|---|---|
| BOCHK | 89.2 | A | **unscored** — no confirmed capital reading at any date |
| TD Bank | 83.3 | A | **unscored** — no confirmed capital reading at any date |
| MUFG | 73.7 | B | **unscored** — no confirmed capital reading at any date |
| CIBC | 73.5 | B | **unscored** — no confirmed capital reading at any date |
| SMFG | 70.3 | B | **unscored** — no confirmed capital reading at any date |
| Standard Chartered HK | 86.0 | A | **unscored** — falls back to 2023-09-30, 1,074 days old |
| Barclays Bank | 65.4 | B | **unscored** — falls back to 2022-12-31, 1,347 days old |
| Bank of Scotland | 65.9 | B | scored on 2025-12-31 figures (251 days old) |
| Bendigo and Adelaide Bank | 62.4 | C | scored on 2026-03-31 figures (161 days old) |
| Vanquis | 49.5 | D | scored on 2025-06-30 figures (435 days old) |

Worth seeing plainly: MUFG, SMFG, BOCHK and Standard Chartered HK are the names the coverage
push spent its effort on. Excluding unverified figures would put four of them straight back to
"not scored", and would take the scored count from 118 to 111.

### C. Count them, but say so in the coverage figure
Keep the score, and reduce the bank's coverage percentage in proportion to how much of it rests
on unconfirmed readings. A reader comparing two banks would see the same score with different
coverage, and the profile already explains what coverage means. More work than either A or B:
the coverage calculation and its definition both change.

## What I would do, and why

**A, with the mark made louder rather than the figure removed.** The site's stated position is
that it shows public figures with their source and date and lets the reader check — and it now
does: the mark carries its own definition on the profile, and the document is a click away. B
trades a small, visible uncertainty for a large, invisible one: seven banks reading "not scored"
tells a treasurer less than a scored bank with a marked figure, and four of the seven are among
the largest names covered.

The case for B is real if the score is ever quoted without the profile behind it. If that day
comes, B is the safer default and the seven names are the price.

C is the honest middle and the most work; it would be my choice if the coverage figure were
already carrying more weight in how people read the site.

---

*Figures as at 2026-09-08, from `data/facts.parquet` and `data/json/board.json`. The per-bank
working is in `/tmp/unverified_impact.csv` on the machine that generated this; re-run the
analysis from the commit message of this file's commit to reproduce it.*
