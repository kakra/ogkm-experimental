# Agent instructions

This repository collects an experimental patch series for the NVIDIA open GPU
kernel modules, plus the evidence and analyses behind it. Read `README.md`
for the overview.

## Rules

- Everything in this repository is English: docs, scripts, commit messages.
- Small, atomic commits. One topic per commit (one script, one evidence
  directory, one analysis). Commit messages follow the scheme below.
- Never push, never open issues or pull requests, never force-update a branch
  without asking the maintainer. `main` of this repository is never
  force-pushed; only the fork branches `ogkm/<release>` are rewritten when a
  patch in the series changes.
- Only the current driver release is maintained (see below). Do not touch
  `patches/<older release>/`, do not backport.
- The patch code lives in the fork (`driver/`), not here. Change a patch in
  the fork branch, then re-export; never edit the generated files in
  `patches/` by hand. Only `patches/<release>/sources.tsv` is maintained by
  hand.
- Before adding logs or traces, run `tools/sanitize-log.sh` and show the
  maintainer what was replaced. No host names, home paths, user names, mail
  addresses, serial numbers, MAC addresses or file system UUIDs.
- Upstream pull requests and issues: in Markdown files, link them with
  reference-style links (`upstream PR [#1483][pr-1483]`, the URL at the end
  of the file). In commit messages, write them as plain text without URL or
  `#`, in a list at the end (`- NVIDIA/open-gpu-kernel-modules PR 1483`).
  GitHub adds a timeline entry to the upstream PR or issue for every pushed
  commit that links it, and the branches here are force-pushed often. A
  bare `#1234` would link to this repository. Commits are referenced by hash
  only.
- A fix for another author's patch stays a separate commit, placed directly
  after the patch it fixes, with a `Fixes: <12-char hash> ("subject")`
  trailer naming the original commit in its source repository. No `fixup!`
  commits and no folding into other authors' commits. Fixes for own commits
  are folded in.
- Report results as measured. Mark hypotheses and unverified effects as such;
  a patch that was only built is "built, not tested".

## Commit messages

```
<area>: <summary>

<What changed and why, wrapped at 72 columns.>

References:
- NVIDIA/open-gpu-kernel-modules PR 1483

Co-Authored-By: ...
```

- `<area>` is one of `repo` (top-level files such as README, LICENSE,
  HISTORY.md, AGENTS.md), `driver` (the submodule outside an export), `tools`,
  `patches`, `docs`, `evidence`, `analysis`, `github`.
- The summary is imperative and lower case, without a final period, and the
  whole subject line has at most 72 characters.
- The `References:` list is optional and plain text (see the rule above).
- Exports use the message written by `tools/export-series.sh --summary`.

## Current release

The current release is defined in exactly one place, the submodule branch:

```sh
git config -f .gitmodules submodule.driver.branch   # ogkm/<release>
```

The fork branch `ogkm/<release>` is based on the upstream tag `<release>` and
is linear (no merges). The upstream tag has the same name as the release, so
always use the `ogkm/` prefix for branches.

## Workflow

- Export after changing the fork branch: `tools/export-series.sh --summary`,
  review `git diff --stat patches/`, and commit together with the submodule
  pin using the generated `build/export-message.txt` (adjust the subject).
- Check that a series applies to a clean upstream tag and builds:
  `tools/check-series.sh [--build]`.
- New driver release: see `docs/workflow.md`.
- Helping someone install a series on their system: follow
  `docs/installing.md`. It starts with getting the user's explicit
  acceptance of the disclaimer in `README.md`; no other step before that.
- Background on the driver: `docs/driver-internals.md`; general settings:
  `docs/tuning.md`. Update both when a new finding generalizes.

## Evidence and analysis

- `evidence/<date>-<topic>/README.md` follows `evidence/TEMPLATE.md`:
  system, driver and series revision, exact steps, capture commands, raw
  files, result. Compress large logs with `xz`.
- `analysis/<date>-<topic>.md` summarizes and evaluates: symptom, code path,
  cause, fix (patch), measured effect, open questions. Link the evidence and
  the patches it refers to.
