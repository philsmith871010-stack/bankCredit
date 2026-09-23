---
name: counterparty-summary
description: Write the short summary on a bank's profile for the Counterparty site - one background sentence on who they are and what they do, and three or four sentences on what the figures add up to for a depositor - for every name whose summary is owed, from the dated paragraph the data gives and nothing else. Runs unattended on the maintainer's machine under the nightly job. Claude Code subscription; no API key anywhere.
---

# Counterparty summaries

Every profile carries a paragraph the pipeline writes from the data on each build: standing,
peers, ratings, trends, news, every figure dated. You write the two things that paragraph
cannot: who this is, and what the numbers mean. A summary is rewritten only when the inputs it
rested on have moved or it is over ninety days old, so most nights this list is empty.

## 1. What is owed

```bash
python -m bankcredit.cli summaries due
```

This writes `data/cache/summaries_todo.json`: one entry per name owed, with `id`, `name`,
`type`, `country`, `reason` (why it is owed), `brief` (the paragraph), `inputs` (the fingerprint
to record) and `previous` (the background sentence held before, if any). If it says
`0 of N summaries owed`, stop; there is nothing to do.

## 2. Write each one

For each entry, write `data/review/summaries/<id>.json`:

```json
{"id": "coventry-bs", "written": "2026-09-16",
 "background": "Coventry Building Society is a UK mutual funded by retail savings and lending on residential property, the second-largest building society after Nationwide.",
 "synthesis": "Two of the three main agencies rate the society, A on average and the weakest of them at A-, both on a stable outlook, after a one-notch upgrade by one of the three on 12 May 2026. Capital is strong on the headline measure, with CET1 of 19.6% in the top quarter of UK building societies, but leverage of 4.7% is in the bottom quarter, which is the one figure to keep an eye on. Liquidity is comfortable, with LCR of 233% and NSFR of 147% both above their medians. Since 31 Mar 2025 CET1 has fallen 1.7 points, leverage 0.6 points and LCR 21 points. Nothing has been flagged in the last 90 days.",
 "inputs": { ...copy the entry's inputs exactly... }}
```

**Background** - one sentence, at most two. What kind of institution, how it funds itself, what
it lends on or does, where it sits in its market, whose group it belongs to. General knowledge
is allowed here and only here. Keep it to what does not date: no names of officers, no
"recently", no results, no strategy announcements. If `previous` is present and still true,
keep it word for word; do not rewrite for the sake of it.

**Synthesis** - three or four sentences on what the figures add up to for a treasurer deciding
whether to place a deposit: where the strength is, where the weak spot is, what has moved and
which way, what the ratings say. Written for a professional; no hedging, no advice.

**Never name a rating agency, and never use an agency's own symbol.** The site shows the
average and the weakest of the three main agencies' ratings on one scale, and how many of the
three hold each outlook; it does not say which agency said what, because a rating with an
agency's name on it is that agency's product and republishing it needs a licence
(docs/ratings-composite.md). So: "rated A on average across all three, the weakest of them at
A-, two on a stable outlook and one on negative watch; the last move was a one-notch downgrade
by one of the three on 3 May 2026". Never "Fitch", "S&P", "Moody's", "DBRS", "KBRA", "Scope",
"JCR"; never "A2", "Aa3", "Baa1". The check refuses both.

The one rule that matters: **every figure in the synthesis comes from `brief`**, as it is
written there, with the same dates. Nothing from memory, nothing from anywhere else. A number
the check cannot find in the paragraph fails the whole summary and it is not published.

Three things the check allows today but will fail tomorrow, so leave them out:

- **The peer medians.** Say "above the peer median", never "above the 16.4% median": the
  median moves whenever any peer reports, and a quoted one is owed a rewrite the next morning.
- **Dates of older headlines.** The paragraph shows only the newest three flagged items, so
  cite the newest by date at most and the rest in words.
- **The site's score or band.** They depend on weightings the reader may have changed. The
  check refuses them outright.

`written` is today's date. `inputs` is the entry's `inputs`, unchanged - it is how the site
knows, later, what has moved since you wrote this.

## 3. Check

```bash
python -m bankcredit.cli summaries check
```

It holds every summary against today's paragraph: a stray figure, a wrong length, a dated word.
Fix anything it names and run it again until it passes. The nightly job pushes `data/review`
afterwards; you do not push.

Report in one or two sentences: how many were owed, how many you wrote, and whether the check
passed. If the todo file was empty, say so and stop.
