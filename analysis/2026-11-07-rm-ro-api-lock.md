# Read-only RM API lock (`RmRoApiLock`)

- **Status:** registry key in use on 620.70.06 with the series since
  2026-11-12; no regressions observed so far (see Results)
- **Source:** NVIDIA's answer in egl-wayland issue [#164][egl-164]
  ([comment][egl-164-c]), which recommends
  `NVreg_RegistryDwords=RmRoApiLock=0x27a` and says that a read-only default
  "is being worked on in the development branches now"
- **Related:** [lock stalls](2026-10-26-lock-stalls.md),
  `docs/driver-internals.md` (Locks)

## How the API lock mode is chosen

The RM API lock is an rwsem. For each API, the lock mode comes from a mask,
`pSys->apiLockMask`, copied to `g_resServ.roTopLockApiMask`
(`src/nvidia/src/kernel/core/system.c`, `_sysRegistryOverrideResourceServer`).

- Without the registry key the mask is `NVBIT(RS_API_CTRL)` only.
- With the key, the mask is built from its bits and **replaces** the default,
  so bit 9 (CTRL) has to be set again.

| Bit | Field (`nvrm_registry.h`) | API | 0x27a |
|---|---|---|---|
| 1 | `ALLOC_RESOURCE` | allocation | on |
| 2 | `FREE_RESOURCE` | free | off |
| 3 | `MAP` | CPU mapping (`mapping_cpu.c`) | on |
| 4 | `UNMAP` | CPU unmapping | on |
| 5 | `INTER_MAP` | DMA (GPU VA) mapping (`mapping.c`) | on |
| 6 | `INTER_UNMAP` | DMA unmapping | on |
| 7 | `COPY` | dup | off |
| 8 | `SHARE` | share | off |
| 9 | `CTRL` | controls | on (default) |

What each bit does in the lock lookups:

- **ALLOC** (`serverAllocResourceLookupLockFlags`, `rmapi/alloc_free.c`):
  a class flagged `RS_FLAGS_ACQUIRE_RO_API_LOCK_ON_ALLOC` gets the read lock
  only if this bit is set. Without it, **every** allocation takes the API
  lock for write, including `SystemMemory` (71 entries in
  `resource_list.h` carry the flag in 620.70.06). The same holds for
  615.78.08.
- **MAP, UNMAP, INTER_MAP, INTER_UNMAP, FREE:** the bit alone decides read or
  write.
- **CTRL** (`rmapi/control.c`): a control takes the read lock only if the
  bit is set *and* the control is flagged `RMCTRL_FLAGS_API_LOCK_READONLY`.
  Controls without that flag stay write-locked.

## Consequence for the sysmem paths

Earlier analyses assumed that sysmem allocation runs under the read lock.
That is only true with the ALLOC bit. In stock configuration, the PAT change
to UC/WC and the zeroing of fresh pages run under the write-locked API lock
and stop every other RM client, including the compositor. With 0x27a, they
only stop writers (frees, and allocations of unflagged classes).

## Overlap with the series (620.70.06)

| Patch | Covered by 0x27a? |
|---|---|
| nvidia: take the API lock for read for DMA map and unmap | yes, same as INTER_MAP/INTER_UNMAP (the patch says so) |
| nvidia: take the API lock for read for GET_SURFACE_INFO | no: the control lacks `RMCTRL_FLAGS_API_LOCK_READONLY`, the CTRL bit does not apply |
| nvidia: don't take the API lock for NO_API_LOCK controls' GPU reference | no (no lock at all instead of a read lock) |
| nvidia: don't take the API lock for semaphore surface UNREGISTER_WAITER | no |
| nvidia: free uncached and write-combined sysmem from a worker | no, FREE stays write-locked |
| nvidia: keep uncached and write-combined sysmem pages uncached in a pool | no, the pool avoids the PAT change itself |

New with 0x27a and not in the series: read lock for allocations of flagged
classes, and for CPU map/unmap.

## Risks

NVIDIA states: "For alloc, there are some known race conditions you are
unlikely to hit. For map/unmap, it should be entirely safe." Possible reasons
the read lock is not the default yet (reasoning from the code, not confirmed
by NVIDIA):

- With a read lock, allocations of different clients run in parallel. A
  constructor that touches shared state without its own lock (heaps,
  cross-client references through dup/share, GPU instance data) races.
- Work moves from the API lock to the GPU lock, client locks and internal
  mutexes; lock order problems hidden by the big lock can surface.
- Configurations not covered here: multiple GPUs, MIG, vGPU, GPUs without
  GSP. Allocations there often involve several GPUs.
- `RS_FLAGS_FORCE_ACQUIRE_RO_API_LOCK_ON_ALLOC_FREE` together with
  `PDB_PROP_SYS_ENABLE_FORCE_SHARED_LOCK` suggests a per-class, switchable
  rollout.

Where to look for problems while testing: several clients starting or
exiting at the same time (a game starting while a browser and OBS run), new
Xids, rendering errors, hangs.

## Results (620.70.06, kernel 7.3.4)

- The key is active: `/proc/driver/nvidia/params` shows
  `RegistryDwords: "RmRoApiLock=0x27a"`.
- Several gaming sessions over multiple boots without Xid, hang or rendering
  errors. The kernel log of 2026-11-07 to 2026-11-14 holds no Xid at all.
- The key is active since the boot of 2026-11-12 01:07 (the modprobe option
  was set on 2026-11-07 22:36, after the boot before). The only RM errors are
  the known `can't update VA space` triples (`gpu_vaspace.c:4088`): 35 before
  the key (boot of 2026-11-07), 2 with the key (boot of 2026-11-12 01:07: 0,
  boot of 2026-11-12 20:55: 2, boot of 2026-11-14: 0), the same signature as
  before; they come from the user space driver (see
  [vaspace overlap](2026-10-28-vaspace-overlap.md)) and are not related to the
  API lock mode.
- Not measured yet: the latency effect (`tools/trace/nv-pat-latency.bt`) and
  stalls while several clients start or exit at the same time.

## Detecting a new default upstream

Checked on every new release (see `docs/workflow.md`):

```sh
grep -n 'apiLockMask = ' src/nvidia/src/kernel/core/system.c
grep -n 'RS_API_\(ALLOC_RESOURCE\|MAP\|UNMAP\|INTER_MAP\|INTER_UNMAP\)' \
    src/nvidia/src/kernel/rmapi/alloc_free.c \
    src/nvidia/src/kernel/rmapi/mapping.c \
    src/nvidia/src/kernel/rmapi/mapping_cpu.c
grep -n 'READONLY_API_LOCK_.*_DEFAULT' src/nvidia/interface/nvrm_registry.h
```

In 620.70.06 the first line is `pSys->apiLockMask = NVBIT(RS_API_CTRL);`
in the branch without registry key. Once more bits appear there (or the
lookups hardcode the read lock), drop the DMA map/unmap patch and stop
recommending the registry key.

## Options for the series (after the test)

1. Keep everything; the DMA map/unmap patch is then redundant on systems with
   the key, which does no harm.
2. Drop the DMA map/unmap patch once NVIDIA ships the new default.
3. Replace it with a patch that extends the default mask by the bits NVIDIA
   calls safe (MAP, UNMAP, INTER_MAP, INTER_UNMAP). ALLOC stays opt-in through
   the registry key and is not enabled by the series.

[egl-164]: https://github.com/NVIDIA/egl-wayland/issues/164
[egl-164-c]: https://github.com/NVIDIA/egl-wayland/issues/164#issuecomment-6712349084
