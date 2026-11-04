# Metrics audit, 4 November 2026

After Headroom turned out to compare CET1 with a total-capital requirement (docs/headroom.md),
every collected metric was checked against its source template and the stored figures were
checked against each other. What was wrong, and what was done.

## Scoring

- **Old figures scored as current.** Today's score took each metric's latest point whatever its
  age: UK majors were scored on June 2020 NPL ratios, about 40 EU banks on June 2024 ones, and a
  few banks on profitability from 2021-22. Each figure now counts only while under 550 days old,
  the rule the score history already used (`export.scoring_inputs`).
- **Headroom across periods.** A requirement is now used only beside a total capital ratio from
  the same period (up to 120 days earlier). Four building societies were setting 2025 capital
  against 2022-23 requirements.
- **Requirements on the wrong basis.** An overall requirement under 10.5% (8% plus the conservation
  buffer) is a CET1-basis figure and is not used: Standard Chartered disclosed one until March 2026.
  A requirement whose total SREP figure is 8.0% leaves out Pillar 2A, and Headroom is left out for
  that bank rather than overstated.
- **US requirements.** No US filing states one, so the Federal Reserve's published stress capital
  buffers and GSIB surcharges are held in `data/reference/us-capital-requirements.json` (holding
  companies), with 8% plus 2.5% for the insured banks. US holding companies now get a Headroom
  score like everyone else, on the standardised approach.
- **Subsidiaries and the group's market.** A subsidiary's overlay is now worked from its own
  market evidence only. The group's share price and CDS are still shown, named as the group's.

## Collection

- **Pillar 3 (km1.py, pillar3.py):** thousands written as "AED 000s" and similar, and a "bn" in
  prose above the table, gave amounts 1000 times off; misread dates, mostly a footnote digit glued
  to the year; earlier columns read as the current period; leverage rows that fail their own
  arithmetic; requirement rows taken as the leverage ratio; bounds that dropped genuine high
  ratios at small subsidiaries. A bank-specific CET1 requirement is now built from rows 7a/7b and
  11.
- **Annual reports (esef.py, fundamentals.py):** concepts are taken in their declared order of
  preference, not filing order; ROE is owners' profit over owners' equity; cost-to-income no
  longer uses income net of loan-loss charges; NIM only from a like-for-like interest pair.
  Macquarie Bank and Investec plc no longer carry their groups' accounts.
- **EBA:** the 2025 Transparency Exercise (the last) is read, so EU NPL ratios run to June 2025;
  a hub filing already in millions is no longer divided again.
- **US:** Citigroup's LCR had come from Citibank Europe's Pillar 3 since late 2024; capital tables
  are read from one approach column, the standardised one, throughout.

## Display

- An amount series keeps one currency, the bank's own; Transparency Exercise euros no longer
  interleave with SEK or GBP.
- US Tier 1 leverage is shown as itself, compared only with other US Tier 1 leverage figures,
  and has its own tile against the 4% US minimum.
- The CET1 and total capital tiles use the requirement in force for that period.

## Not changed, deliberately

- **Custody banks' leverage.** State Street, BNY and Northern Trust score lower on bank-level Tier 1
  leverage than their groups do on the supplementary leverage ratio, which by statute excludes
  their central-bank deposits. The bank-level figure is the stricter one and is kept.
- **NPL definitions** differ by region (Stage 3 at amortised cost, FDIC noncurrent loans). No
  common measure is published; the difference is stated on the Method page.
- **CDS seniority.** US holding-company senior CDS references structurally subordinated debt;
  EU senior CDS references preferred senior. The bands are not split by region: the overlay is
  capped and the difference is a few basis points for most names.
- **Citigroup's total capital** binds on the advanced approach by its own footnote; Headroom uses
  the standardised ratio and requirement throughout, which slightly overstates Citi's.
