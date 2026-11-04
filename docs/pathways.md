# The site's shape: a landing page, and a tool laid out as three pathways

Decided 11 October 2026, to bring Counterparty in line with PWLBtoday and the PWLBreports
landing page.

## The two pages

- `index.html` is the landing page, in the frame PWLBreports uses for the same job: one
  question ("Who can you deal with, and for how long?"), a card of what the site holds today,
  the three pathways, how it works, what it rests on, and the way in. Dark, static, no webfont,
  no application script. A reader with a list in this browser is offered the way straight to it.
- `tool/index.html` is the tool, in the platform's own shell: the PWLBtoday wordmark and a title
  bar (PWLB + the accent word, the way PWLBpredict and PWLBbenchmark are written) across the top,
  the pathways beneath it in two rows, the page in the rest. Every bank profile and the admin
  page sit in the same frame. Nothing is drawn down the side: the site goes inside PWLBtoday,
  whose own navigation has the left of the screen.

## The pathways, in two rows across the top

| Group | Items | What opens |
|---|---|---|
| Build your strategy | Start here · Weightings · Choose names | the three steps; the weightings, as a page; the table every name is on, as a page |
| Monitor | Your counterparties | the list with what moved since each name was approved (the Events page was removed on 3 November 2026; each name's rating actions and reports are on its own profile) |
| Compare | Alternatives · Analysis · Ratings | names at least as strong as your weakest at each tenor; any names side by side; the universe by the average and the weakest of the three |
| Reference | Method · Data status | the method; what ran and when (Overview went on 3 November 2026: the PWLBtoday wordmark already leads to the landing page) |

The groups are the three jobs a reader arrives with, in the order the jobs come, and the
reference last because it is read second. They are defined once, in `components.NAV`, and
drawn by `components.topnav()` as two rows: the four groups, then the pages of the open group.
A group opens its first page. `app.js` marks the page for the open panel, its group, and shows
that group's row, as the panel changes. A page that belongs to no group, such as a bank's profile, shows the groups alone.
On a phone each row scrolls on its own and the four groups fit the width. Until 3 November 2026
the pathways were a sidebar; they moved to make room for the platform's navigation.

## Monitor: what has moved since approval

Your counterparties answers one question: since I approved this list, what got worse, what got
better and what is unchanged. Each name is compared at two dates on one basis, read from the
`hist` field every row of `policy.json` carries (`export._monitor_history`): its score recomputed
on today's method at the quarter end before the baseline, against the same score now; the three
agencies' ratings, outlooks and watches from the register's own path; its CET1 ratio and its
total-capital headroom over the overall requirement, period to period.

| Tier | Signals |
|---|---|
| Red | a downgrade; negative watch; a lower band, or the score down 5 or more; CET1 down 1.5 points or more; total capital under 1 point over its requirement |
| Amber | outlook to negative; score down 3 to 5; CET1 down 0.75 to 1.5 points; headroom down 1 point or more |
| Green | an upgrade; outlook to positive, or positive watch; a negative outlook or watch lifted; score up 3 or more |

A downgrade stands until a later upgrade answers it, and an upgrade is undone by a later
downgrade; an outlook ended by the rating move itself is the move. Anything red or amber still
standing puts the name under Needs a look, worst then latest first; otherwise any green puts it
under Improved; the rest are Unchanged, folded to a row of names unless nothing moved at all. A
move that landed on three or more names the same day is said once above the cards, and the names
whose only change it was fold into one line. Old figures and names too thin to score are listed
apart under Data to check, because they are about our collection, not the bank, and never count
as a name getting worse.

The baseline is the reader's: since approval (each name's `added` date, which the approved-on
date sets for the whole list), since the last review (Mark reviewed stamps `reviewed`), or the
last 30 days. The example list is approved on 1 April 2026, the start of the financial year, so
it has a year of changes to show. Headroom was first set at under 2 points; UK majors run total
capital a point or two over the overall requirement by design, so that flagged them every quarter.

## Build your strategy

Three numbered steps, the way PWLBreports numbers its passes, each saying where the reader has
got to: the weightings line (step one, whose Change opens the Weightings page), the table every
name is on (step two, whose button opens the Choose names page, with the count of names on the
list), and the tenors (step three, with the range
set). The counts are painted by the list's own script on every render, so adding a name on the
table moves step two the moment it happens. A reader who already holds a list opens on the
list; a reader without one opens on the steps.

## What did not change

The panels are the same panels, the scripts the same scripts: the tab strip that used to
switch them is still in the document, because the panel loader and every link into the page
speak to it, but it is not drawn. The old addresses still resolve (`compare/`, `ratings/`,
`events/`, `policy/`, `banks/`) and carry the reader to the right panel. The data the pages
read is where it was, so PWLBbenchmarking's read of `data/policy.json` is untouched.

## Where it lives

- `bankcredit/site/components.py`: `PRODUCT`, `STRAP`, `TOOL`, `NAV`, `topnav()`, `shell()`.
- `bankcredit/site/build.py`: `page_landing()`, `page_tool()`, `strategy_panel()`, `panel_head()`.
- `bankcredit/site/assets/landing.css`: the landing page's own stylesheet.
- `bankcredit/site/assets/site.css`: the shell, the two rows of pathways, the strategy steps (at the end).
- `bankcredit/site/assets/app.js`: the pathways' mark: the open page, its group and its row (at the end).
- `bankcredit/site/assets/policy.js`: `paintStrategy()`, and the open-on-the-list rule in `init()`.

Weightings and Choose names were dialogs over the page until November 2026. They are pages of the
tool now, beside Start here, so a reader working through the steps stays on the page and the
navigation marks where they are. A name's detail still opens over the page.
