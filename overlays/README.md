# Customer overlays [WL-8]

A deployment is this repo (unmodified) plus one small bundle of
customer-specific values: Terraform variables, backend environment variables,
and a brand. That bundle is a **customer overlay**, and it lives at
`overlays/<name>/` — never inside `infra/`, `backend/` or `frontend/` — so
customer configuration never has to be mixed into tracked application code to
take effect.

## What an overlay holds

```
overlays/<name>/
  infra.tfvars       # Terraform variables for this customer's deployment
  backend.env        # Backend environment variables (DATA_SOURCE, SOURCE_SCHEMA,
                      # FABRIC_*, WAREHOUSE_*, AUTH_MODE, ...)
  frontend.env        # VITE_BRAND_* overrides (name, short name, logo, favicon)
  brand-mark.svg       # Optional: the customer's own logo, replacing the
                       # neutral mark `frontend/public/brand-mark.svg` ships with.
                       # SVG only — see WL-13, no raster images in this repo.
```

`overlays/example/` shows the shape with every file named `*.example` and every
value a placeholder. Everything else under `overlays/` is `.gitignore`d (see
below): a real, filled-in overlay is customer data and must never be committed
here.

## Using an overlay

1. Copy `overlays/example/` to `overlays/<name>/`, dropping the `.example`
   suffix from each file, and fill in every `<...>` placeholder.
2. Terraform: `terraform plan -var-file=../overlays/<name>/infra.tfvars` (or
   point `azd`'s pipeline at the same file). `infra.tfvars` is the same shape
   as `infra/profiles/enterprise.tfvars.example` — start there for the full,
   current list of enterprise-profile variables, including `source_schema`.
3. Backend: `copy overlays\<name>\backend.env backend\.env` before running or
   deploying the API. See `backend/.env.example` for what each variable means.
4. Frontend: `copy overlays\<name>\frontend.env frontend\.env.local` before
   building the SPA, and drop a replacement `brand-mark.svg` into
   `frontend/public/` (or point `VITE_BRAND_LOGO` /
   `VITE_BRAND_FAVICON` somewhere else build-time reachable) if the customer
   supplies their own mark. See `frontend/src/brand.config.js`.

**What `frontend.env` covers, and what it does not.** Name, short name, logo
and favicon are env-driven (`brand.config.js`) and that is the whole of what
`frontend.env` sets. The colour palette (`brand`, `brand-deep`, `accent-2`,
`success`, …) is a separate, build-time-only half of white-labeling —
`tailwind.config.js` — and is not currently read from any environment
variable. A customer wanting their own palette edits the `colors` block in
`tailwind.config.js` directly, in their own fork.

## Where a real customer's overlay lives

**Never in this repository, including a fork's own history, if the fork is
ever shared back.** A real overlay holds genuine tenant IDs, subnet IDs,
Fabric workspace and warehouse identifiers, and a live source schema name —
exactly the kind of environment-specific value that must stay out of tracked
files. The customer:

- keeps their filled-in `overlays/<name>/` in **their own fork**, on a branch
  or location of their choosing, outside what they intend to contribute
  upstream; or
- keeps it entirely outside git, in whatever secret-aware configuration store
  their deployment pipeline already uses (Key Vault references, a deployment
  pipeline's own variable groups, etc.) — see
  `docs/architecture/DEPLOYMENT-HANDOVER.md` for the full deployment story.

This upstream repository only ever carries `overlays/README.md` (this file)
and the placeholder `overlays/example/`.
