# The agencies' own ratings, quoted beside the average

Decided 23 September 2026. The public site shows the average and the weakest of the three main
agencies (docs/ratings-composite.md). Beside it, each profile now also shows the agencies' own
current ratings, with the agency named. This note says on what basis, in what shape, and how to
put it behind a login later.

## The basis

- Article 10(1) of the Credit Rating Agencies Regulation requires every rating and outlook to be
  disclosed "on a non-selective basis and in a timely manner". Article 13 requires the information
  disclosed on the agencies' websites and the European Rating Platform to be "made available free
  of charge". Recital 31 of the 2013 amendment created the platform so that investors can "easily
  compare all credit ratings that exist with regard to a specific rated entity".
- ESMA's opinion of 22 September 2021 (ESMA80-196-5819) found that the three largest agencies'
  website terms had "prohibited the use of credit ratings for any internal or external purposes",
  that after ESMA raised it they "agreed to make changes to the terms of use of their websites to
  clarify that individual credit ratings could be downloaded for internal use and regulatory
  reporting purposes", and recommended that the law say what must be disclosed free and that
  licences be on fair, reasonable and non-discriminatory terms. From January 2028 the EU will
  publish ratings information on the European Single Access Point, machine-readable and free.
- A single rating is a short statement of opinion, not a literary work, and courts have refused
  copyright in analogous single ratings and in Moody's own bond data (Feist; Financial
  Information v Moody's). In the UK, section 30(1ZA) of the Copyright, Designs and Patents Act
  allows quotation from a work made available to the public where the dealing is fair, the
  extent is no more than the purpose requires and the source is acknowledged, and section 30(4)
  makes a contract term that tries to prevent such a quotation unenforceable.
- Banks' investor pages, councils' treasury reports, Wikipedia's country lists and the press all
  show attributed ratings without a licence notice, and no case has been found where a
  republisher of individual current ratings was sued.

This is our own reading of the law and of the agencies' terms. It has not been agreed with any
agency, and it is not legal advice. The exposure that remains is contractual (the agencies'
click-through terms) and the database right, and the agencies enforce by letter rather than by
suit. If a letter arrives, the view is withdrawn; nothing else on the site depends on it.

## The shape, which is the point

What keeps this a quotation rather than a copy of the agencies' database:

- current ratings only: the headline long-term rating and outlook and the latest short-term
  rating each of Fitch, S&P and Moody's holds today; no other agency;
- one record per agency per name, dated, with the agency acknowledged and a link to the
  agency's site and to the ESMA register;
- no history by agency (the history on the site is the average and the weakest);
- no download, no table across names, no attributed data in the public JSON the pages read;
- the basis shown beside the ratings, on every profile and on the Method page, saying that the
  view may be withdrawn and that onward use is the reader's own responsibility.

A disclaimer cannot move the risk of publishing onto the reader; an objection would land on the
publisher. What it can do is state the basis in good faith, say that the view may go, and make
clear that the reader's onward use is theirs.

## Where it lives

- `bankcredit/attributed.py`: `rows()` builds the record per name, `write()` writes
  `site/members/ratings.json` with the basis text, and `BASIS` is the text shown.
- `bankcredit/site/build.py`: `attributed_block()` puts the frame and the basis on each profile;
  `build()` writes the members file when `COUNTERPARTY_ATTRIBUTED` is set; the Method page
  carries the basis.
- `bankcredit/site/assets/app.js` fills the frame from the members file; `policy.js` adds one
  line to the card dialog.
- `.github/workflows/pipeline.yml` sets `COUNTERPARTY_ATTRIBUTED=1` for the beta site.

## Putting it behind a login later

Everything attributed is in one file, `members/ratings.json`, fetched by the pages. To gate it,
protect that one path at the host (an access rule on `/members/` in front of the site); the pages
already handle a refused fetch by saying the view is not available. GitHub Pages cannot protect a
path, so a login means serving the site from a host that can. Unsetting
`COUNTERPARTY_ATTRIBUTED` in the workflow removes the file from the build altogether.
