# ogkm-experimental

Experimental patches for the
[NVIDIA open GPU kernel modules](https://github.com/NVIDIA/open-gpu-kernel-modules),
together with the measurements, traces and analyses that motivated them.

The patches are tested on one desktop system in daily use (gaming, a Wayland
compositor, several 4K displays). Every change is meant to be understandable
and reproducible on its own: each patch has a commit message explaining cause,
effect and fix, and the evidence for a problem lives next to the patch series.

**Status:** experimental. Use at your own risk. Only the series for the
current driver release is maintained; older series stay in the repository as
history and are not updated. The fork branches are force-pushed whenever the
series changes; the exported patches in this repository are the durable
history (see [docs/workflow.md](docs/workflow.md)).

## Disclaimer

These patches change a kernel driver. Only use them if you know what you are
doing and how to recover your system: if it no longer boots or the display
stays black, you need to be able to fix that yourself, e.g. by booting another
kernel or reinstalling the stock driver from a rescue system. There is no
support for this, neither for installing the patches nor for recovering from
them.

The patches are provided as is, without warranty of any kind (see
[LICENSE](LICENSE)). The author is not responsible for any damage, including
the unlikely cases of data corruption or damage to hardware. Use at your own
risk. No backup, no mercy. ;-)

## Current release

| Driver release | Series | Fork branch |
|---|---|---|
| 615.78.08 | [`patches/615.78.08/`](patches/615.78.08/) | [`ogkm/615.78.08`](https://github.com/kakra/open-gpu-kernel-modules/tree/ogkm/615.78.08) |

## Layout

| Path | Content |
|---|---|
| `driver/` | Submodule: [fork](https://github.com/kakra/open-gpu-kernel-modules) of the upstream repository, one branch `ogkm/<release>` per driver release |
| `patches/<release>/` | The series exported from the fork branch, applicable with `git am` to the upstream tag `<release>` |
| `evidence/` | Raw data per investigation: logs, traces, memory statistics, with the exact steps to capture them |
| `analysis/` | Summaries and evaluations that tie evidence, code paths and patches together |
| `docs/` | Workflow, building, test system, patch reviews |
| `tools/` | Export, check and log sanitizing scripts; `tools/trace/` holds the tracing scripts used for the evidence |
| `HISTORY.md` | What changed in the series per driver release, and why |

## Using a series

On a clone of the upstream repository:

```sh
git checkout -b ogkm 615.78.08
git am /path/to/ogkm-experimental/patches/615.78.08/*.patch
make modules -j$(nproc)
```

Or check out the fork branch directly (`git submodule update --init driver`).
The modules must be used with the GSP firmware and user-space components of
the same driver release, see the upstream README. How to integrate the series
into a distribution package is described in [docs/installing.md](docs/installing.md),
written so that an AI coding agent can follow it as well.

## Background

- [docs/driver-internals.md](docs/driver-internals.md): how the parts of the
  driver involved here work (sysmem allocation, PAT, locks, scanout memory,
  reading the kernel log)
- [docs/tuning.md](docs/tuning.md): kernel and driver settings that helped,
  and how well each is backed by measurements
- [docs/xid-errors.md](docs/xid-errors.md): every Xid seen on the test
  system, what NVIDIA documents about it, and whether the series helps

## Patch sources

The series combines patches from several sources: open upstream pull
requests, the patch set maintained by Tom Englund
([gulafaran/open-gpu-kernel-modules](https://github.com/gulafaran/open-gpu-kernel-modules),
branch `patches`), and own fixes. Authorship is preserved in every patch;
`patches/<release>/README.md` lists the source of each one.

## How this was made

Analysis, tracing and most of the patches were done with the help of an AI
coding assistant (Claude by Anthropic), as the `Co-Authored-By` trailers in the
commits show. Every change was reviewed, built and run on real hardware by a
human before it went into a series, and results are reported as measured,
including what is still unverified.

## Reporting problems

Please use the issue templates. For problems that also occur with the
unpatched driver of the same release, report them to
[NVIDIA/open-gpu-kernel-modules](https://github.com/NVIDIA/open-gpu-kernel-modules/issues)
instead.

## License

Patches are derived from the NVIDIA open GPU kernel modules and are under the
same terms (MIT, dual MIT/GPLv2 when linked into a Linux kernel module).
Everything else in this repository is under the same terms, see
[LICENSE](LICENSE).
