# Market overlay secret

The public score is fully published. The market overlay (ratings, CDS, volatility, drawdown) is private: its
weights live only in the GitHub Actions secret `COUNTERPARTY_OVERLAY`, read at build time by `bankcredit/export.py`.
Without the secret the overlay is neutral (all adjustments zero), so a public checkout of this repo reproduces
the public score exactly and nothing else.

Set the secret to a JSON object with any of these keys (unset keys keep the neutral default):

```json
{
  "cds_bands": [[40, 4], [60, 2], [90, 0], [150, -3], [1e9, -6]],
  "cds_change_widen_bp": 15, "cds_change_widen_adj": -2,
  "cds_change_tighten_bp": -10, "cds_change_tighten_adj": 1,
  "vol_high": 45, "vol_high_adj": -2, "vol_low": 25, "vol_low_adj": 1,
  "drawdown_adj_threshold": -25, "drawdown_adj": -3,
  "rating_grades": {"AAA": 5, "AA": 4, "A": 3, "BBB": 1, "BB": -3, "B": -6},
  "cap": 10
}
```

`cds_bands` is a list of `[upper bound in bp, adjustment]` pairs applied to the five-year senior CDS level;
`rating_grades` adds the grade's value averaged across the agencies that rate the bank; `cap` bounds the total.
The example above is a starting point only; choose your own values before setting the secret, since this example
is public.
