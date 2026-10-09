# Disclaimer

Read this before using anything in this repository to prepare, support, or
substantiate a tax filing.

## This is not tax advice

This software computes figures from payroll data according to rules encoded in
this repository. **Microsoft is not a tax advisor and provides no tax, legal, or
accounting advice.** Nothing produced by this software is a professional opinion
on eligibility, entitlement, or the correct treatment of any credit.

Every output must be reviewed by a qualified tax professional before it is used
in a filing, an amendment, a claim, or any representation to a tax authority.

## This is prototype software

This code was built as a working prototype to demonstrate an approach. It is
provided **"AS IS"** under the terms in [LICENSE](LICENSE), without warranty of
any kind, and without any commitment to maintain, support, or correct it.

It has not been through the review, hardening, or operational readiness process
that Microsoft applies to its commercial products, and it should not be treated
as one.

## Known limits of the calculation

Stated plainly, so no one has to discover them:

- **One programme is reconciled.** The Georgia Jobs Tax Credit headcount
  calculation has been reconciled against a partner's independent methodology on
  a shared reference dataset. **Credit *values* are not certified** — they depend
  on county tier, industry eligibility, and base-year comparison, which are not
  fully represented here.
- **Other jurisdictions are prototypes.** Rule packs for states other than
  Georgia, and the federal WOTC pack, are illustrative. Do not rely on them.
- **Statutory rates change.** Rules are frozen per tax year under
  [ADR-005](docs/architecture/ADR-005-year-versioned-rules.md) so historical runs
  replay exactly. A tax year with no authored rule pack is declined by name — it
  is never estimated from an adjacent year. Verify that the year you need is
  authored and current before relying on any figure.
- **Source data completeness is assumed, not verified.** The calculation reports
  the boundaries of what it was given. It does not manufacture missing payroll,
  and a gap in the source becomes a gap in the answer.
- **Open methodology questions remain.** These are tracked in the repository and
  are not settled. They are documented rather than silently resolved.

## Data in this repository

All payroll data committed here is **synthetic**. Social Security numbers use the
900–999 range, which the Social Security Administration has never issued, and
email addresses use the IANA-reserved `.example` domain.

**No real payroll, no real employee data, and no personally identifiable
information is committed to this repository.** Real reference data used during
development is excluded by `.gitignore` and has never been tracked.

If you connect this software to real payroll, you become responsible for the
handling, protection, retention, and lawful processing of that data.

## Trademarks

This project may contain trademarks or logos for projects, products, or services.
Authorized use of Microsoft trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must
not cause confusion or imply Microsoft sponsorship. Any use of third-party
trademarks or logos is subject to those third parties' policies.
