# Headlines removed from the site

Decided 3 November 2026. The site keeps to the public record and the market: regulatory filings,
the agencies' ratings and their actions from the ESMA register, Pillar 3 reports, and traded
prices. It no longer collects, judges or shows news headlines.

## Why

Headlines never entered the score. They appeared as a "News 30d" count on every table, as an
"adverse headlines" flag on a reader's cards, in the Events feed and the weekly brief, and in the
written summaries. A review of what was held on 3 November found:

- **3,214 headlines** since May, rising fast (59 in May, 1,847 in October), from a Google News
  search per name and a universe-wide sweep for rating-action stories.
- **The volume sat on the wrong names.** Bank of America, Barclays, UniCredit, Commerzbank and
  Goldman Sachs carried the most; 13 of the 20 building societies had none at all.
- **Most of it was dropped on review.** Of 3,123 judged, 1,969 were dropped (the bank as analyst,
  macro commentary, earnings previews, appointments, duplicates). Of the 1,154 kept, three were
  judged "bad".
- **The "bad" flag meant nothing.** All 100 headlines then flagged bad were a word match: about 60
  retold one story (a US money-laundering fine), and the rest were fraud-detection products,
  customer scams and small fines. None described a threat to repayment.
- **A random 150 of the rest:** about 7% would bear on a deposit decision, about 53% were true but
  already in the filings, ratings or prices, and about 41% were noise.
- **The judging could not keep up.** About 1,900 headlines had never been reviewed.

The few that mattered (a takeover changing who the counterparty is, a second annual loss, a large
redress bill) reached the ratings, the filings or the market signal within days. The market prices
news faster than any reading of it can.

## What changed

- `bankcredit/adapters/events.py` collects rating actions from the ESMA register and the Pillar 3
  reports, and nothing else. The Google News search, the agency sweep, the word-match severity,
  the verdicts and `prune-news` are gone.
- The pipeline has no headline mode: `decide.sh` answers full, build or skip.
- `export.py` drops the rows of type `news` already stored, once, so no page can reach them. The
  rows stay in `data/events.parquet`; nothing reads them.
- The News 30d and News 90d columns, the adverse-headline flag, the headline lines in the weekly
  brief and the summary's news sentence are gone. The summary's last sentence now lists the
  agencies' own actions of the last 90 days.
- A written summary that reports news or headlines fails `summaries.check`, so the profile shows
  the data paragraph until the summary job rewrites it.
- The `counterparty-news` skill and the Mac job's news step are removed.
- The Events page went too: its sidebar item, its panel, the weekly brief at its head and the
  RSS feed at `events/feed.xml`. Without headlines it was a list of rating actions and reports
  that each name's profile already shows on its Ratings, Events and Sources tabs, and the site
  is simpler without a second place to look. The old `events/` and `brief/` addresses carry the
  reader to Your counterparties.

## Not changed

The verdict files under `data/review/` are left as they are. The "headline refresh pokes" cloud
routine, which started a pipeline run three times a weekday to refresh headlines, was switched
off the same day.
