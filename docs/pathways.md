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
  the pathways down the side, the page in the rest. Every bank profile and the admin page sit in
  the same frame.

## The pathways, which are the sidebar

| Group | Items | What opens |
|---|---|---|
| Build your strategy | Start here · Weightings · Choose names | the three-step panel; the weightings dialog; the table every name is on |
| Monitor | Your counterparties · Events | the list with what moved since each name was approved; rating actions and headlines |
| Compare | Alternatives · Analysis · Ratings | names at least as strong as your weakest at each tenor; any names side by side; the universe by the average and the weakest of the three |
| Reference | Overview · Method · Data status | the landing page; the method; what ran and when |

The groups are the three jobs a reader arrives with, in the order the jobs come, and the
reference last because it is read second. The sidebar is defined once, in `components.NAV`,
and the item for the open panel is marked by `app.js`; the two items that open a dialog rather
than a panel are never marked.

## Build your strategy

Three numbered steps, the way PWLBreports numbers its passes, each saying where the reader has
got to: the weightings line (step one, with the dialog behind Change), the table every name is
on (step two, with the count of names on the list), and the tenors (step three, with the range
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

- `bankcredit/site/components.py`: `PRODUCT`, `STRAP`, `TOOL`, `NAV`, `sidebar()`, `shell()`.
- `bankcredit/site/build.py`: `page_landing()`, `page_tool()`, `strategy_panel()`, `panel_head()`.
- `bankcredit/site/assets/landing.css`: the landing page's own stylesheet.
- `bankcredit/site/assets/site.css`: the shell, the sidebar, the strategy steps (at the end).
- `bankcredit/site/assets/app.js`: the sidebar's mark and the phone toggle (at the end).
- `bankcredit/site/assets/policy.js`: `paintStrategy()`, and the open-on-the-list rule in `init()`.
