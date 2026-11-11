# Local Development — Gotchas Worth Knowing First

`BUILD_GUIDE.md` covers standing the project up from nothing. This file covers the things
that waste an hour once you already have it running. Every item below was hit for real and
verified by running the command — none of it is recalled or assumed.

---

## Pushing to `origin`

**The repository is private, and GitHub answers `404`, not `403`, for a private repo your
credentials cannot see.** So this message:

```
remote: Repository not found.
fatal: repository 'https://github.com/<owner>/<repo>.git/' not found
```

almost never means the repo is missing. It usually means the wrong account is active. If
`gh` holds more than one account, check which one is live and switch:

```bash
gh auth status
```

```bash
gh auth switch --user <account-with-access>
```

## Pushes that touch `.github/workflows/`

GitHub rejects any OAuth-app push whose commits modify a workflow file unless the token
carries `workflow` scope:

```
! [remote rejected] refusing to allow an OAuth App to create or update workflow
  `.github/workflows/ci.yml` without `workflow` scope
```

Grant it, then push again:

```bash
gh auth refresh -h github.com -s workflow
```

`gh auth refresh` has **no `-u`/`--user` flag** (as of v2.96) — it refreshes whichever
account is currently active, so `gh auth switch` first if you need a different one.

## Credential caching on Windows

Git's default `manager` helper caches **per host, not per account**, so it can keep handing
git the previous account's credentials even after `gh auth switch` — producing the same
misleading 404 above. Make git follow `gh` instead, scoped to this clone only:

```bash
git config --local --replace-all credential.helper ""
```

```bash
git config --local --add credential.helper "!gh auth git-credential"
```

Undo with `git config --local --unset-all credential.helper`.

---

## Running the backend

There is **no virtualenv** — `api/` runs against system Python. Run the test suite from
`api/`, with the package importable:

```bash
cd api && PYTHONPATH=. python -m pytest -q
```

## Redis is often not running

Without Redis, `POST /api/scans` cannot enqueue and the worker path cannot be exercised
end to end. The API still serves already-completed scans straight from SQLite, so dashboard
and read-path work is verifiable without it: seed a scratch database, point `DATABASE_URL`
at it, and run the API against that. Note the API refuses to boot outside development
without `API_KEY` set, so pass `ENVIRONMENT=development` when doing this locally.

## The CLI scanner takes its path positionally

```bash
cd api && PYTHONPATH=. python -m app.cli_scan <path> --offline --json
```

There is no `--path` flag. `--offline` skips the network-backed checks (registry, OSV,
license), which is what you want for a fast local pass.

## Console encoding

Terminal output here is cp1252 and renders em-dashes as `?`. Before concluding that a file
is corrupted, check the file itself — the bytes on disk are usually fine and only the
console rendering is lossy.

---

## Things that are gitignored on purpose

`CLAUDE.md`, `Instructions.md`, `CODEBASE_REVIEW_BRIEF.md`, `PROMPT_improve_detection.md`
and the design assets sit under an explicit *"Internal / design / scratch — NOT part of the
shipped product (never push)"* block in `.gitignore`. They exist on maintainer machines and
will not be in your clone, so any cross-reference to them from a tracked document is a dead
link. Anything a contributor genuinely needs belongs in `docs/`.
