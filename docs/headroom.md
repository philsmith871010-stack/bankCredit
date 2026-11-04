# Headroom: total capital over the overall requirement

Changed 4 November 2026.

The Headroom pillar (weight 10) scores how far a bank's capital sits above what its regulator
requires. It is now the total capital ratio less the overall capital requirement, both read from
the same KM1 table (rows 3 and 11a).

Before this it was the CET1 ratio less the overall capital requirement. No scored bank reports a
CET1-specific requirement, so every headroom figure came from that fallback, and the overall
requirement is a total-capital figure: CET1, Additional Tier 1 and Tier 2 together. Comparing CET1
with it understated headroom by the bank's AT1 and Tier 2 stack, and 44 of 91 scored banks read as
having none. Barclays Bank UK, for example, holds 19.6% total capital against an 18.0% requirement
(+1.6 points) but scored 0 because its CET1 is 13.8%.

The thresholds are unchanged (0, 1.5, 3, 5, 8 points earn 0, 35, 60, 80, 100). On the 4 November
data the switch raised scores by about 5 points on average and at most about 10.5, before rating caps.

What it does not do:

- KM1 row 12 (CET1 available after meeting minimum requirements) is not used. It excludes buffers,
  is defined differently in the UK and the EU, and runs several points higher, so mixing it into the
  same pillar would score two similar banks differently. The extractor still reads it under
  `cet1_headroom`, a separate name from the scored `capital_headroom`.
- Total capital counts Tier 2 debt, so a bank with a large Tier 2 stack scores well on Headroom.
  The capital pillar scores CET1 on its own, which is the counterweight.
