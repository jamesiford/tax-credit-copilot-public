# Push checklist

**Nothing has been pushed.** The repository `origin` is a **public** GitHub repository. This checklist is for the owner **if** they
decide to publish; none of the commands below was run, and no remote was added or changed.

## Decision needed first: how to split the work

`main` was kept at `029b9ad` on purpose and the combined work sits on `feat/m365-channel` (tag `m365-channel-poc-2026-11-03`).
Pushing that branch as it is publishes the channel, the AI platform, the data layer **and** the UI revamp together, with 200+ commits
of history. The owner's plan is to split it into separate branches in a separate task. Decide before any push:

- `main` stays untouched at `029b9ad`.
- `feat/ui-modern-theme` is already UI/UX only: 10 commits off `main`, 196 files, 187 under `frontend/`. Only `README.md` and
  `.github/copilot-instructions.md` overlap with the channel work.
- A channel, AI platform and Fabric data branch is to be rebuilt off `main` without the UI merge (`58dcd53`), re-applying the later
  work. The AI platform was built on the early channel work, so they stay together.
- CH-15d (the portal chat evidence stream; it touches `frontend/src/api.js`, `frontend/tools/mock_api.py`, the Ask backend test and
  `askBackendShape.json`) depends on both, so it goes in an optional integration branch with both.
- The combined `feat/m365-channel` and the `pre-master-2026-11-03` tag remain the safety reference.

Then choose the destination: (a) the existing public repository, (b) a new **private** repository, or (c) a private fork. For a
customer-adjacent proof of concept, (b) or (c) is the safe default.

## Before any push

1. **Privacy review.** Re-run on the branch you will push: `pwsh scripts/check-whitelabel.ps1 -Enforce`,
   `python scripts/audit-export.py --enforce`, `gitleaks git --no-banner --redact --exit-code 1 .` (full history) and
   `gitleaks dir` on a clean export. Confirm no tenant, subscription, Entra, Fabric or hostname identifier of the deployment and no customer
   name appears in tracked files or **in history** (a value removed from the tip is still in an older commit). The private deployment notes list
   what to search for; read them at run time and never copy them into the repo.
2. **Never publish** `.azure/`, `channel_orchestrator/.azure/`, `overlays/`, `backend/data/payroll/**`, `.env` files, `dist/` or any PNG.
   They are gitignored; confirm with `git status --ignored` that nothing of the kind is tracked.
3. **CI that will run on push** (`.github/workflows/ci.yml`, on pushes to `main`, `feat/**` and `wp/**` and on pull requests to `main`): backend
   and frontend suites, the synthetic parity gate, a **full-history gitleaks scan** (`.gitleaks.toml` has narrow allowlists for vendored digests and
   one made-up record token) and the Terraform job (fmt, validate, tflint, test). The private reference fixtures are absent on a runner, so only the
   synthetic gate runs there. `deploy.yml` deploys to Azure; do not enable it for a new destination without its secrets and variables.
4. Decide what happens to the 39 `wp/*` and 10 `jamesiford-*` branches: push none of them, or push only the branches you intend to keep. Pushing
   with `--all` or `--tags` publishes every one.

## Commands per destination (do not run until decided)

```pwsh
# (a) the existing public repository: one branch, no tags
git push origin <branch>:<branch>

# (b) a new private repository
git remote add private https://github.com/<owner>/<new-private-repo>.git
git push private <branch>:<branch>
git push private m365-channel-poc-2026-11-03          # a single tag

# (c) a private fork
git remote add fork https://github.com/<owner>/<private-fork>.git
git push fork <branch>:<branch>
```

For the split branches, create each from `main` first (for example `git switch -c feat/m365-channel-platform main`) and re-apply its
commits with `git cherry-pick -m 1` or `git merge --no-ff` of the relevant `wp/*` branches, run the gate on each, then push it by name.

## If a push goes wrong

- Nothing was force-pushed, and none of the above needs `--force`. If a wrong branch reached a **private** destination, delete the remote branch
  (`git push <remote> --delete <branch>`) and, for a leaked value, treat it as exposed: rotate it, because deleting a branch does not remove
  cached clones or forks.
- If a wrong branch or a secret reached the **public** repository, make the repository private first (or remove the branch), then rotate every
  exposed value, then ask GitHub support to purge cached views if needed. History rewriting and force-pushes are the owner's decision and are not
  covered here.
- The local safety references are unchanged by any push: `main` (`029b9ad`), `feat/m365-channel` and the tags `pre-master-2026-11-03`,
  `pre-final-run-2026-11-03`, `pre-consolidation-2026-11-03` and `m365-channel-poc-2026-11-03`.
