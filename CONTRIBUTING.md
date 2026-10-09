# Contributing

Thanks for your interest in this project.

## Before you start

This repository is a **prototype**, published as an independent reference
implementation — see [DISCLAIMER.md](DISCLAIMER.md) for what that means and
what it does not certify. There is no commitment to review or merge external
contributions on any particular timeline, or at all.

## The one rule that matters most

The reference dataset's certified figures
(`backend/tests/certified.py`, `backend/rules/methodology/certified-figures.json`)
are reconciled against a partner's independent methodology and are **never
edited to make a test pass**. A pull request that changes them without
re-reconciliation will not be merged. See
[`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the
full set of house rules the codebase enforces, including the architecture
rules in `backend/tests/test_architecture.py`.

## How to contribute

1. Fork the repository and create a branch for your change.
2. Run the standard gate before opening a pull request:
   ```pwsh
   cd backend ; $env:TCC_REQUIRE_PARITY=1 ; pytest tests/ -q
   cd frontend ; npm test ; npm run build
   python backend/tools/verify_reference_independent.py
   ```
   `TCC_REQUIRE_PARITY=1` only turns a missing private fixture into a loud
   error rather than a silent skip; `backend/tests/test_engine_parity_synthetic.py`
   runs either way, against the committed synthetic dataset.
3. Open a pull request describing what changed and why. Reference the
   requirement or ADR it relates to if one exists.
4. A new API route needs a matching entry in `backend/tests/route_inventory.json`
   in the same commit (`tests/test_route_inventory.py` fails the build
   otherwise). A new backend endpoint needs a corresponding `api.test.js`
   case in the frontend.

## Contributor License Agreement

This project may require you to agree to a Contributor License Agreement (CLA)
declaring that you have the right to, and actually do, grant us the rights to
use your contribution. For details, visit <https://cla.opensource.microsoft.com>.

When you submit a pull request, a CLA bot will automatically determine whether
you need to provide a CLA and decorate the PR appropriately (e.g., status
check, comment). Simply follow the instructions provided by the bot. You will
only need to do this once across all repositories using our CLA.

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](CODE_OF_CONDUCT.md).
For more information see the
[Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any
additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or
services. Authorized use of Microsoft trademarks or logos is subject to and
must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must
not cause confusion or imply Microsoft sponsorship. Any use of third-party
trademarks or logos is subject to those third parties' policies.
