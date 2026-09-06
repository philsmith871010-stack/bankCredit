"""Counterparty score, version one. Public pillars with published weights; market overlay bounded.

Each metric is turned into a 0..100 sub-score by piecewise-linear interpolation against
absolute thresholds (chosen from Basel minimums and typical ranges), then pillars are
averaged with weights. Missing metrics do not score zero: the pillar weight is re-scaled
over what is available and the coverage fraction is reported so the site can show
"insufficient data" honestly. Bands: A 80+, B 65+, C 50+, D 35+, E below.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# (metric, thresholds as [(value, score), ...] ascending in value)
PILLARS = {
    "capital": (30, {
        "cet1_ratio": [(4.5, 0), (8.0, 30), (11.0, 55), (14.0, 80), (18.0, 95), (25.0, 100)],
        "leverage_ratio": [(3.0, 0), (4.0, 40), (5.0, 70), (6.5, 90), (9.0, 100)],
        "total_capital_ratio": [(8.0, 0), (12.0, 40), (16.0, 70), (20.0, 90), (26.0, 100)],
    }),
    "liquidity": (20, {
        "lcr": [(100, 0), (120, 40), (140, 65), (170, 85), (220, 100)],
        "nsfr": [(100, 0), (110, 40), (125, 70), (140, 90), (160, 100)],
    }),
    "asset_quality": (20, {
        "npl_ratio": [(0.2, 100), (1.0, 85), (2.0, 65), (4.0, 40), (8.0, 10), (15.0, 0)],
    }),
    "profitability": (15, {
        "roe": [(-5.0, 0), (2.0, 30), (6.0, 55), (10.0, 75), (15.0, 90), (25.0, 100)],
        "roa": [(-0.5, 0), (0.2, 30), (0.6, 55), (1.0, 75), (1.5, 90), (2.5, 100)],
        "efficiency_ratio": [(40.0, 100), (55.0, 80), (65.0, 60), (75.0, 35), (90.0, 10), (110.0, 0)],
    }),
    "stability": (15, {
        # headroom of CET1 over overall requirement, in percentage points
        "cet1_headroom": [(0.0, 0), (1.5, 35), (3.0, 60), (5.0, 80), (8.0, 100)],
    }),
}
BANDS = [(80, "A"), (65, "B"), (50, "C"), (35, "D"), (0, "E")]
OVERLAY_CAP = 10.0


def interp(value: float, points: list[tuple[float, float]]) -> float:
    pts = sorted(points)
    if value <= pts[0][0]:
        return pts[0][1]
    if value >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return pts[-1][1]


@dataclass
class ScoreResult:
    public_score: float | None
    coverage: float
    pillars: dict = field(default_factory=dict)      # pillar -> (score or None, weight used)
    overlay: float = 0.0
    final_score: float | None = None
    band: str = ""
    inputs: dict = field(default_factory=dict)


def band_for(score: float | None) -> str:
    if score is None:
        return ""
    for floor, b in BANDS:
        if score >= floor:
            return b
    return "E"


def compute(latest: dict[str, float], overlay: float = 0.0) -> ScoreResult:
    """latest: metric code -> latest value. overlay: signed adjustment from the private layer, capped."""
    latest = dict(latest)
    if "cet1_ratio" in latest and "overall_capital_requirement" in latest and "cet1_headroom" not in latest:
        # approximate CET1 headroom as CET1 ratio minus overall requirement (KM1 row) when a CET1-specific requirement is absent
        latest["cet1_headroom"] = latest["cet1_ratio"] - latest["overall_capital_requirement"]
    if "cet1_ratio" in latest and "cet1_requirement" in latest:
        latest["cet1_headroom"] = latest["cet1_ratio"] - latest["cet1_requirement"]
    pillars, weighted, weight_used, inputs = {}, 0.0, 0.0, {}
    for name, (weight, metrics) in PILLARS.items():
        subs = []
        for m, pts in metrics.items():
            if m in latest and latest[m] is not None:
                s = interp(float(latest[m]), pts)
                subs.append(s)
                inputs[m] = (latest[m], round(s))
        if subs:
            p = sum(subs) / len(subs)
            pillars[name] = (round(p, 1), weight)
            weighted += p * weight
            weight_used += weight
        else:
            pillars[name] = (None, 0)
    total_weight = sum(w for w, _ in PILLARS.values())
    coverage = weight_used / total_weight
    if weight_used == 0:
        return ScoreResult(None, 0.0, pillars, 0.0, None, "", inputs)
    public = weighted / weight_used
    ov = max(-OVERLAY_CAP, min(OVERLAY_CAP, overlay))
    final = max(0.0, min(100.0, public + ov))
    band = band_for(final) if coverage >= 0.5 else "?"
    return ScoreResult(round(public, 1), round(coverage, 2), pillars, ov, round(final, 1), band, inputs)
