# Ratings without attribution

Decided 23 September 2026. The site shows one rating per name, worked out from the three main
agencies, and never says which agency holds which rating.

## Why

A credit rating shown with its agency's name on it is that agency's product. The agencies'
terms of use say the free public access they must give under the CRA Regulation (article 10:
every rating disclosed publicly, non-selectively and free of charge; article 11a: the ESMA
European Rating Platform) is for personal, non-commercial use, and that redistribution needs a
licence. ESMA's own platform terms license only ESMA's material and defer to the agencies'
terms for the ratings (docs/esma-erp-terms.md). Whether a single rating is protectable at all
is doubtful in law - a short opinion is not a literary work, and a list of all ratings has
little claim to copyright or database right - but the agencies enforce by contract and demand
letter rather than by suing, and nobody has been found who republished agency ratings in bulk
and won. A treasury adviser who publishes rating tables pays Fitch, Moody's and S&P for the
right.

An average and a count worked out from a public register are this site's own work. That is the
line drawn here: the site republishes nothing attributable, and shows what a treasurer needs.

## What is shown

- **Average**: the mean of the long-term ratings Fitch, S&P and Moody's hold on the name, each
  read on one scale (1 = AAA ... 17 = CCC), over whichever of the three rate it. A half rounds
  to the weaker notch. Agencies outside the three are not averaged in: a treasury policy is
  written around the three, and a fourth agency that rates a handful of names would move the
  average of some banks and not others.
- **Weakest**: the lowest of the three.
- **Outlooks**: one mark per agency, worst first - watch negative, negative, watch positive,
  positive, stable - with no name on any mark.
- **Count**: how many of the three rate the name, so a letter backed by one agency is never
  mistaken for one backed by three.
- **History**: the average and the weakest on every day either moved since the register opened
  on 1 July 2015, and a lane counting how many of the three held each outlook or watch on every
  day that changed. Every move is listed as "upgrade by one of the three, 1 notch", with the
  average after it.
- **Rating actions** in the events feed read "One of the three agencies upgraded its long-term
  rating"; the agency's name, its rating type wording and its symbol are all left off, and an
  action by an agency outside the three is not shown.
- **Sovereigns**: the same average and weakest over the three, as context beside a bank.

The letters are the site's own notation for a position on the scale. An A3 is shown as A-, and
nothing on the page says whose A- it was.

## What is not shown

Which agency holds which rating; any agency's own symbol; short-term ratings (each agency's
short-term scale names the agency); rating types by the agencies' names; per-agency history.

## Where it lives

- `bankcredit/composite.py`: the scale, the tones, `composite()`, `describe()`, `public_action()`.
- `bankcredit/timeline.py`: the average, the weakest and the tone counts on every day they changed.
- `bankcredit/export.py`: `public_events()` strips every rating event once, where the table is
  read, so nothing downstream can publish an attributed action; `_composite()` is the record a
  page shows.
- `bankcredit/summaries.py`: the written summaries say "rated A on average across all three";
  the check refuses an agency name or symbol.
- `bankcredit/site/components.py`: the chart.

## What the repository still holds

The raw tables (`data/ratings.parquet`, `data/rating_actions.parquet`,
`data/withdrawn_ratings.parquet`, `data/sovereign_ratings.parquet`) carry the agencies' names,
because the average has to be worked out from them. The repository is public, so those files
are public too. Moving them out of the public repository - a private data repository, or a
workflow artefact - is the remaining step if the line drawn above is to hold everywhere and
not only on the site.

## Reversing it

Every page reads the composite record; the per-agency layout lives in the git history before
this change (`git log --all -- bankcredit/site/components.py`, the `rating_timeline` with a band
per agency). With a licence from the three agencies, the attributed layout can be restored
from there.
