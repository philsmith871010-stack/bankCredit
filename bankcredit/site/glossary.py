"""Plain-English definitions for every number and word the site puts in front of a reader.

A treasury officer meeting these terms for the first time should be able to read any page without
leaving it. One entry per term: the name as it is written on screen, a single sentence that says
what the number is, and two or three more that say how it is built and what a normal value looks
like. Nothing here is advice and nothing sets a threshold - where a range is given it describes
what the universe on this site actually shows, so a reader can tell an ordinary figure from an
unusual one.

Every page carries the whole glossary as JSON, so the definitions are the same in a server-rendered
table heading and in a card the browser draws after the data arrives. Keep them short: this is read
in a popover beside the number, not as an article.
"""
from __future__ import annotations

import json

# key -> (title, one-sentence answer, the rest)
TERMS: dict[str, tuple[str, str, str]] = {
    # ---- capital ---------------------------------------------------------------------------
    "cet1_ratio": (
        "CET1 ratio",
        "The bank's best capital, measured against the risks it is carrying.",
        "Common Equity Tier 1 is the money that takes losses first: shares the bank has issued and "
        "profits it has kept rather than paid out. The ratio divides that by risk-weighted assets, so "
        "a bank lending to governments needs less of it than one lending to small businesses. "
        "Most banks here sit between 12% and 20%; regulators set each bank its own minimum, "
        "typically around 9% to 11% once buffers are counted.",
    ),
    "tier1_ratio": (
        "Tier 1 ratio",
        "CET1 plus a layer of bonds that convert to shares if the bank gets into trouble.",
        "Additional Tier 1 instruments count here: perpetual bonds that stop paying, or turn into "
        "equity, when capital falls far enough. It is always at least as high as the CET1 ratio, "
        "usually by one or two percentage points.",
    ),
    "total_capital_ratio": (
        "Total capital ratio",
        "All the capital a bank can count, against its risk-weighted assets.",
        "Tier 1 plus Tier 2 - mainly dated subordinated bonds, which absorb losses only once the "
        "bank has failed rather than while it is running. It is the widest of the three capital "
        "ratios and typically runs three to six points above CET1.",
    ),
    "leverage_ratio": (
        "Leverage ratio",
        "Capital against everything the bank owns, with no adjustment for risk.",
        "The deliberately blunt check: it ignores risk weights entirely, so it catches a bank that "
        "looks strong only because its assets are treated as safe. Most banks here report between "
        "4% and 7%. US banks report a different version on average assets, and the site says so "
        "where that is the figure being shown.",
    ),
    "rwa": (
        "Risk-weighted assets",
        "The bank's lending and trading, scaled up or down by how risky each part is.",
        "A loan to a government may count for nothing, a mortgage for a fraction of its value, an "
        "unsecured business loan for all of it. Every capital ratio on this site is divided by this "
        "number, which is why two banks of the same size can need very different amounts of capital.",
    ),
    "overall_capital_requirement": (
        "Capital requirement",
        "The minimum ratio this particular bank must hold, set by its regulator.",
        "It is not the same for every bank: a common minimum, plus an add-on for the risks the "
        "supervisor sees in that bank, plus buffers. The gap between the requirement and what the "
        "bank actually holds is its headroom - the room it has before restrictions begin.",
    ),
    "headroom": (
        "Headroom",
        "How far the bank's capital sits above the minimum its regulator requires.",
        "Measured in percentage points. Fall into it and the bank faces limits on dividends, "
        "bonuses and coupon payments long before there is any question about deposits.",
    ),

    # ---- liquidity -------------------------------------------------------------------------
    "lcr": (
        "LCR",
        "Whether the bank holds enough cash-like assets to survive a month of money leaving.",
        "The Liquidity Coverage Ratio compares assets it could sell or pledge immediately against "
        "the outflows a 30-day stress would produce. 100% means it exactly covers that month; the "
        "legal minimum is 100% and banks here typically report 130% to 200%.",
    ),
    "nsfr": (
        "NSFR",
        "Whether long-term lending is funded by money that will stay for the long term.",
        "The Net Stable Funding Ratio looks a year out rather than a month, and asks whether "
        "mortgages and term loans are paid for with deposits and term debt rather than borrowing "
        "that has to be rolled every week. The minimum is 100%; most banks report 110% to 140%.",
    ),
    "deposits": (
        "Deposits",
        "Money customers hold at the bank.",
        "The cheapest and usually the stickiest funding a bank has. A bank funded mostly by "
        "household deposits behaves very differently in a stress from one funded in wholesale "
        "markets.",
    ),
    "total_assets": (
        "Total assets",
        "Everything the bank owns, before any risk weighting.",
        "The plain measure of size: loans, securities, cash at the central bank. Useful for "
        "comparing scale, not strength.",
    ),

    # ---- ratings ---------------------------------------------------------------------------
    "rating": (
        "Credit rating",
        "An agency's opinion of how likely the bank is to pay what it owes, on time.",
        "Written as letters: AAA is the strongest, then AA, A, BBB and downwards, with + and - "
        "steps inside each. BBB- and above is called investment grade; below that is sub-investment "
        "grade, and many local authority policies stop there. The ratings here come from the "
        "European Rating Platform, the public register agencies must file to.",
    ),
    "composite": (
        "Composite rating",
        "The site's single letter, taken from all the agencies that rate the bank.",
        "Where two or three agencies disagree, the composite sits at the middle of their opinions "
        "rather than the best of them. It is shown with a count of the agencies behind it, so a "
        "letter backed by one agency is never mistaken for one backed by three.",
    ),
    "outlook": (
        "Outlook",
        "Which way the agency expects the rating to move over the next year or two.",
        "Positive, stable or negative. It is not a change of rating - it is a signal that one is "
        "being considered. A negative outlook is a reason to look, not a reason to act.",
    ),
    "short_term_rating": (
        "Short-term rating",
        "The same opinion, for debts due inside a year.",
        "Written on its own scale: F1+, A-1+, P-1 and so on for the strongest. It matters most for "
        "money-market deposits, which is where a lot of local authority cash actually sits.",
    ),
    "idr": (
        "Issuer default rating",
        "The rating of the institution itself, rather than of one bond it has issued.",
        "This is the one the site uses, because a local authority deposit is a claim on the bank, "
        "not on a particular security.",
    ),
    "unrated": (
        "Unrated",
        "No agency currently publishes a rating for this entity.",
        "Usually a smaller building society or a subsidiary that funds itself through its parent, "
        "so it never needed one. It is not a judgement about the entity - but a name with no rating "
        "cannot be scored on this site, because the rating carries 40% of the score.",
    ),
    "withdrawn": (
        "Rating withdrawn",
        "The bank had a rating and the agency has stopped publishing it.",
        "Agencies withdraw for ordinary commercial reasons - the bank stopped paying for the "
        "service - as often as for anything worrying. A withdrawn rating is kept out of the score "
        "entirely rather than left to go stale.",
    ),

    # ---- the score -------------------------------------------------------------------------
    "score": (
        "Counterparty score",
        "This site's 0-100 summary of a bank's published standing.",
        "Ratings carry 40% of it and published ratios the other 60%: capital, liquidity, stability, "
        "asset quality and profitability. It is worked out from public data with a method you can "
        "read, and it is deliberately not a probability of default or a recommendation.",
    ),
    "band": (
        "Band",
        "The score sorted into five groups, A the strongest through to E.",
        "A band is easier to hold a policy against than a number that moves a point either way. "
        "The bands are cut at fixed scores, so a bank changes band only when its published figures "
        "or its ratings really move.",
    ),
    "percentile": (
        "Percentile",
        "Where this bank sits among its peers, from 0 to 100.",
        "80 means it scores above 80% of the banks in its peer group. It compares like with like: "
        "a small building society is measured against other small building societies, not against "
        "a global bank.",
    ),
    "peer_group": (
        "Peer group",
        "The set of banks this one is fairly compared with.",
        "Grouped by size and kind - UK majors, UK mid-sized, building societies, EU and Nordic, US, "
        "and so on. Comparing a ratio against the right group is the difference between a number "
        "that means something and one that does not.",
    ),
    "coverage": (
        "Coverage",
        "How much of the method this bank's published data actually fills.",
        "100% means every pillar the method asks for is present and current. Where a bank does not "
        "publish something, that pillar is re-scaled away rather than guessed, and the coverage "
        "figure tells you how much of the score rests on the rest.",
    ),
    "pillar": (
        "Pillar",
        "One of the five things the score is built from, each with a fixed weight.",
        "Rating 40, capital 25, liquidity 15, stability 10, asset quality and profitability 10. "
        "Each pillar is scored 0-100 on its own, then weighted. A bank's make-up shows exactly "
        "which pillar is carrying it and which is holding it back.",
    ),
    "grade_cap": (
        "Grade cap",
        "A ceiling the score cannot pass while the rating is low.",
        "Strong ratios cannot lift a BBB-rated bank above 74.9, or a sub-investment-grade one above "
        "64.9. It stops a good liquidity figure from outvoting the market's own judgement of the "
        "bank's credit.",
    ),
    "not_scored": (
        "Not scored",
        "The site will not put a number on this name yet.",
        "A score needs a current rating and a capital ratio no more than about 18 months old. Where "
        "either is missing the site shows what it does hold and says what is absent, rather than "
        "publishing a number that leans on a gap.",
    ),

    # ---- market ----------------------------------------------------------------------------
    "market_signal": (
        "Market signal",
        "What the price of the bank's own traded debt is saying about it this week.",
        "Bond yields and credit default swap levels move daily, long before a rating changes. "
        "Widening means investors are charging more to hold the bank's risk; tightening means less. "
        "The site shows the direction, not the levels, because the price data may not be "
        "redistributed.",
    ),
    "cds": (
        "CDS",
        "The market price of insuring against this bank failing to pay.",
        "A credit default swap is a contract that pays out if the bank defaults, and its cost, in "
        "basis points a year, is the cleanest live read on how risky the market thinks the bank is. "
        "Only the direction of travel is published here.",
    ),
    "bond_spread": (
        "Bond spread",
        "The extra yield investors demand to hold this bank's debt rather than a government's.",
        "Measured in basis points - a hundredth of a percentage point. It moves every day and rises "
        "when confidence falls, which makes it an early warning that a rating, updated a few times "
        "a year, cannot give.",
    ),

    # ---- asset quality and profitability ---------------------------------------------------
    "npl_ratio": (
        "Non-performing loans",
        "The share of the loan book where borrowers have stopped paying.",
        "Usually 90 days past due or judged unlikely to pay. Low single digits is ordinary for the "
        "banks here; a rising figure is one of the earliest signs that a lending decision has gone "
        "wrong.",
    ),
    "cost_of_risk": (
        "Cost of risk",
        "What the bank is setting aside this year for loans it expects to go bad.",
        "Expressed against the size of the loan book. It is the bank's own forward-looking estimate, "
        "so it moves before non-performing loans do.",
    ),
    "roe": (
        "Return on equity",
        "Profit measured against the shareholders' money in the bank.",
        "A bank that cannot earn a decent return eventually struggles to raise capital when it needs "
        "it, so profitability is a slow-moving safety measure as well as a commercial one. Very high "
        "figures can mean risk being taken rather than skill.",
    ),
    "roa": (
        "Return on assets",
        "Profit measured against everything the bank owns.",
        "Lower and steadier than return on equity, because it ignores how much the bank has borrowed "
        "to fund itself. Useful for comparing banks of very different leverage.",
    ),
    "nim": (
        "Net interest margin",
        "The gap between what the bank earns on loans and pays on deposits.",
        "The core of most banks' earnings. It widens when rates rise and narrows when competition "
        "for deposits is fierce.",
    ),
    "cost_to_income": (
        "Cost to income",
        "What it costs the bank to earn a pound of income.",
        "50% means half of income goes on running the bank. Lower is more efficient; a figure "
        "drifting upwards means costs are growing faster than the business.",
    ),

    # ---- entities --------------------------------------------------------------------------
    "holding": (
        "Holding company",
        "The parent at the top of a group, not the bank a deposit is placed with.",
        "Barclays PLC is the holding company; Barclays Bank UK PLC is where the deposit sits. The "
        "figures shown are the whole group's, and in a failure the holding company's creditors rank "
        "behind the operating bank's. Place with the entity named on your dealing ticket.",
    ),
    "subsidiary": (
        "Subsidiary",
        "A bank owned by a larger group, with its own licence and its own balance sheet.",
        "It may or may not be supported by its parent in trouble, and agencies say which they "
        "assume. Its published figures are its own, not the group's.",
    ),
    "building_society": (
        "Building society",
        "A mutual owned by its members rather than by shareholders.",
        "Funded mostly by retail savings and lending mostly on housing. They hold capital under the "
        "same rules as banks, but raise it from retained profit rather than share issues, so it "
        "builds more slowly.",
    ),
    "lei": (
        "LEI",
        "The 20-character code that identifies this exact legal entity worldwide.",
        "It is what keeps two similarly named entities in the same group apart, and it is how this "
        "site matches a bank to its filings and its ratings.",
    ),

    # ---- policy ----------------------------------------------------------------------------
    "tenor": (
        "Tenor",
        "The longest you are willing to lend to this counterparty.",
        "The limit your policy sets on maturity - overnight, 100 days, a year. Length is the part of "
        "the risk you control directly: a name you would take for a month may be one you would not "
        "take for three years.",
    ),
    "counterparty": (
        "Counterparty",
        "The institution on the other side of a deposit or loan.",
        "For a local authority treasury it is the bank holding the money. A counterparty policy is "
        "the approved list, and the limits that go with each name.",
    ),

    # ---- the data behind it ----------------------------------------------------------------
    "pillar3": (
        "Pillar 3 report",
        "The disclosure every bank must publish about its own capital and liquidity.",
        "Named after the third pillar of the Basel rules, whose whole purpose is to let outsiders "
        "check a bank's strength. It appears quarterly or half-yearly, and it is where most of the "
        "ratios on this site are read from.",
    ),
    "km1": (
        "KM1",
        "The one-page table of key metrics at the front of a Pillar 3 report.",
        "Regulators fixed its shape so every bank presents the same rows: capital ratios, leverage, "
        "LCR, NSFR, across recent quarters. It is the table this site reads.",
    ),
    "unverified": (
        "Unverified",
        "Read from a PDF, with one of the extractor's own cross-checks left unsatisfied.",
        "The usual reasons are mundane: the bank does not publish an LCR or leverage row at that "
        "level, the column header's date needs a second look, or the table labels its rows without "
        "numbering them. It does not mean the figure is wrong - it means it was not confirmed twice. "
        "The mark is there instead of hiding the figure, it still counts where it is the only "
        "reading held for that quarter, and the document it came from is one click away on the "
        "profile.",
    ),
    "as_at": (
        "As at",
        "The date the figure describes, not the date it was published.",
        "Banks report months after the quarter ends, so a figure dated 30 June may only appear in "
        "September. Every number on this site carries the date it belongs to.",
    ),
}


# The order the whole glossary is read in, and the headings it is read under. Every term belongs to
# exactly one section; a term added above and not listed here fails the site's own test rather than
# quietly falling off the end.
SECTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("Capital", ("cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio", "rwa",
                 "overall_capital_requirement", "headroom")),
    ("Liquidity and funding", ("lcr", "nsfr", "deposits", "total_assets")),
    ("Ratings", ("rating", "composite", "outlook", "short_term_rating", "idr", "unrated", "withdrawn")),
    ("The score", ("score", "band", "percentile", "peer_group", "coverage", "pillar", "grade_cap", "not_scored")),
    ("Market signals", ("market_signal", "cds", "bond_spread")),
    ("Performance and asset quality", ("npl_ratio", "cost_of_risk", "roe", "roa", "nim", "cost_to_income")),
    ("The institutions", ("holding", "subsidiary", "building_society", "lei")),
    ("Your policy", ("counterparty", "tenor")),
    ("Where the figures come from", ("pillar3", "km1", "unverified", "as_at")),
]


def ordered() -> list[tuple[str, str]]:
    """(section, key) for every term, in reading order."""
    return [(sec, k) for sec, keys in SECTIONS for k in keys]


def payload() -> str:
    """The whole glossary as compact JSON, embedded once per page: key -> [title, answer, rest, section]."""
    return json.dumps({k: [TERMS[k][0], TERMS[k][1], TERMS[k][2], sec] for sec, k in ordered()},
                      separators=(",", ":"))
