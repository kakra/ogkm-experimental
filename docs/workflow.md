# Workflow

## Branches and history

This repository lives on the edge on purpose:

- The fork branch `ogkm/<release>` always holds the clean current state of
  the series. It is rewritten and force-pushed whenever a patch changes:
  corrections to own patches are folded in, fixes to other authors' patches
  are separate commits directly after the patch they fix (with a `Fixes:`
  trailer). There are no reverts.
- `main` of this repository only moves forward. Every export is a normal
  commit, and the history of `patches/<release>/` is the durable record of
  how the series changed.
- Older commits of `main` pin the submodule to fork commits that are no
  longer on any branch after a force-push. GitHub may drop such commits, so
  `git submodule update` can fail on old states. Use the exported patches of
  that commit instead.

## Changing the current series

1. Work in `driver/` (or any clone of the fork) on `ogkm/<release>`. Keep the
   branch linear on top of the upstream tag `<release>`; no merges.
2. Commit messages explain cause, effect and fix. Cherry-picks from other
   branches or pull requests use `git cherry-pick -x`; keep the original
   author.
3. Add or update the line for the patch in `patches/<release>/sources.tsv`
   (patch subject, tab, source as Markdown).
4. Run `tools/export-series.sh --summary` and `tools/check-series.sh --build`.
5. Commit the submodule pin together with the export. `--summary` wrote a
   message to `build/export-message.txt` that lists the added, removed and
   changed patches since the last pin; edit its subject (e.g.
   `patches: add <topic> to the <release> series`) and commit with
   `git commit -F build/export-message.txt`. Record the change in
   `HISTORY.md`.

## Moving to a new driver release

Only the current release is maintained. On a new upstream release `<new>`:

1. Fetch the upstream tag into the fork: `git -C driver fetch
   https://github.com/NVIDIA/open-gpu-kernel-modules.git tag <new>`.
2. Create the new branch from the old one and rebase it:
   `git -C driver switch -c ogkm/<new> ogkm/<old>` and
   `git -C driver rebase --onto <new> <old>`.
3. Drop patches that landed upstream (`git cherry` or the upstream
   changelog), and re-check the open pull requests the series carries.
   Resolve conflicts in the fork, one commit at a time.
4. Point the submodule at the new branch:
   `git config -f .gitmodules submodule.driver.branch ogkm/<new>`.
5. `cp patches/<old>/sources.tsv patches/<new>/` (create the directory),
   remove lines of dropped patches, then export and check as above.
6. Update the release table in `README.md`, add a section to `HISTORY.md`
   listing what was dropped and why.
7. `patches/<old>/` and `ogkm/<old>` stay as they are. They are history and
   are not updated any more.

## Adding evidence

1. Create `evidence/<date>-<topic>/` from `evidence/TEMPLATE.md`.
2. Copy the raw files in, run `tools/sanitize-log.sh -n` on them, review the
   output, then run it without `-n`. Compress large logs with `xz -9`.
3. Write down the exact steps and commands, the driver and series revision,
   and the result, including what is not yet verified.
4. If the evidence leads to a conclusion, write or update an analysis in
   `analysis/` and link both ways.
