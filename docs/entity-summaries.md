# Entity summaries — design, agreed 15 September 2026, not yet built

A written summary on every profile: who they are, what they do, how they compare to their peers
across everything held, the trends in their ratios and ratings, and the latest news. Cheap, and
never stale without saying so.

## Two layers

**Layer 1 — written by the pipeline on every build, free.** Arithmetic on data already held,
rendered as dated sentences, tested like everything else:

- standing: band, score, rank within the peer group, move since last quarter
- against peers: each of the four policy ratios placed in its peer quartile, with the median
- ratings: composite, each of Fitch, S&P and Moody's with outlook, the last move and its date
- trends: which held series moved past a threshold over one, four and twelve quarters
- latest news: flagged headlines and rating actions of the last 90 days, one line each

**Layer 2 — written by Claude, rarely.** The two things arithmetic cannot do:

- *who they are and what they do*: one background sentence. **May draw on general knowledge**
  (decided: yes), clearly labelled as background, and must avoid anything that dates - no names
  of officers, no "recently".
- *the synthesis*: three or four sentences on what the numbers add up to for a depositor. Every
  figure in it comes from the layer-1 paragraph the skill hands over, with its date; numbers
  from anywhere else are forbidden.

120-180 words in all.

## Refresh: change-driven (decided), with a 90-day ceiling

Each summary stores a fingerprint of its inputs: latest ratings and outlooks, band, the figure
date, the date of the last flagged event. The nightly Mac job (`scripts/mac/counterparty.sh`,
which already runs Claude Code under the subscription and can push) rewrites a summary only
when the fingerprint has moved or the text is older than 90 days. On a normal night that is
zero to three names; the first pass over 152 is an hour or two, once. No API key, no new service.

## Honesty

- The profile shows *"Written 3 Sep 2026 from figures to 30 Jun 2026."*
- When inputs have changed since it was written, an amber line says what: *"S&P outlook moved to
  negative on 12 Sep; this summary predates it."* The reader is never told a stale thing as current.
- Stored as one JSON file per name under `data/review/summaries/`, diffable, so a wrong sentence
  is a one-line fix; the pipeline renders it, the same way it ingests review answers.

## Where it shows

Layer 1 as the lede above the profile's headline tiles, layer 2 beneath it. A one-line version
on hover on policy cards and universe rows.

## To build

1. `bankcredit/site/build.py`: `brief(b)` - the layer-1 paragraph; tests for every sentence type.
2. `.claude/skills/counterparty-summary/SKILL.md` + a `summaries` step in the Mac job, gated on
   the fingerprint; `tools/push-data.sh` already stages `data/review`.
3. Profile rendering with the written/inputs-changed lines; hover version on cards and rows.
