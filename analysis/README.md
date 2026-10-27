# Analyses

Summaries and evaluations: symptom, code path, cause, fix, measured effect,
open questions. Raw data is in `evidence/`.

| Analysis | Topic | Status |
|---|---|---|
| [2026-10-18-pat-memtype-flood](2026-10-18-pat-memtype-flood.md) | x86/PAT "freeing invalid memtype" flood after failed sysmem allocations | fixed, verified |
| [2026-10-23-dmemcg](2026-10-23-dmemcg.md) | dmem cgroup accounting, `dmem.low` ignored, events 200/201 | analysis, live test open |
| [2026-10-24-sysmem-fragmentation](2026-10-24-sysmem-fragmentation.md) | Big-page sysmem allocations under memory fragmentation | partly fixed, fallback verified |
| [2026-10-26-lock-stalls](2026-10-26-lock-stalls.md) | Lock stalls in the sysmem free/alloc and display paths | free path fixed and verified, alloc path open |
| [2026-10-26-xid109-cyberpunk](2026-10-26-xid109-cyberpunk.md) | Xid 109 in Cyberpunk 2077 | known upstream issue, not a regression |

## Open findings without an analysis yet

- `dmaAllocMapping_GM107: can't update VA space` with asserts at
  `gpu_vaspace.c:4502/4586/4594` and `intermapRegisterDmaMapping` failures
  (overlapping GPU VA mappings from user space, suspected sparse binding in
  vkd3d-proton). Upstream PR [#1483][pr-1483] is in the series but does not
  remove them: 29 blocks in a 32 h boot before, 14 in a 24 minute game session
  and 65 in 3 h after. RM rejects the mappings cleanly; no process name is
  logged.
- Failed scanout GEM allocations of 3.2 MB at up to 300 per minute while VRAM
  is full (2026-10-27); the requesting process is not known yet.

[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
