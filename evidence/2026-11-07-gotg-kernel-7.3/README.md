# Guardians of the Galaxy on kernel 7.3 with driver 620.70.06 (2026-11-07)

First GotG run after two changes at once: driver 620.70.06 (installed
2026-11-05) and kernel 7.3.3 (installed 2026-11-07). Compared with the runs
on 615.78.08 and kernel 6.18 in `evidence/2026-10-26-gotg-explicit-pagesize/`
and the run of 2026-10-29 (journal kept locally, summarized below).

## Setup

- System: see `docs/system.md`; differences: kernel 7.3.3-gentoo with the
  maintainer's bcache, btrfs, platform and gaming series (the gaming series
  sets `kernel.split_lock_mitigate=0` and enables working set protection),
  sched_ext scheduler scx_lavd
- Driver: 620.70.06, series `ogkm/620.70.06` at `7e584fe8` (built
  2026-11-07 18:19)
- Kernel: 7.3.3, boot at 19:12; uptime at capture: 2 h 53 min
- Workload: Marvel's Guardians of the Galaxy (Steam app 1088850), D3D12 via
  vkd3d-proton, without `dxgi.maxDeviceMemory` and without
  `VKD3D_CONFIG=no_upload_hvv`. Proton version and graphics settings were
  not recorded. Chrome and the Plasma desktop ran in the background.

## Steps

1. Started the game at 20:21:32, played until 21:53:02 (1 h 31 min,
   8.1 GiB memory peak of the scope).
2. After the run: `journalctl -k`, `journalctl --user` (Steam and the game
   scope), `/proc/buddyinfo`, `/proc/meminfo`, `/proc/vmstat`,
   `/proc/pressure/*` at 22:06.

## Files

| File | Content |
|---|---|
| `kernel-2015-2155.log` | `journalctl -k -o short-iso`, 20:15 to 21:55 |
| `steam-2021-2153.log` | `journalctl --user`, lines of the game scope and Fossilize |
| `host-state-2206.txt` | uptime, buddyinfo, meminfo, vmstat, PSI at 22:06 |

## Result

No crash, a few stutters. Counts from `kernel-2015-2155.log`, against the
run of 2026-10-29 (615.78.08, kernel 6.18.59):

| Message | 2026-11-07 | 2026-10-29 |
|---|---|---|
| `Failed to allocate NVKMS memory ... for scanout GEM object` (Chrome) | 6 | 17,336 |
| `Sysmem alloc ... page size 0x10000 failed, retrying with page size 0x1000` | about 40 (20:29 to 20:36) | about 37 |
| `poolAllocate` out of memory | 0 | 3 |
| `can't update VA space` | 8 (`gpu_vaspace.c:4088`) | 16 (`gpu_vaspace.c:4502`) |

```
20:24:50 NVRM: dmaAllocMapping_GM107: can't update VA space for mapping @vaddr=0x29720000
20:29:27 NVRM: GPU0 sysmemConstruct_IMPL: Sysmem alloc of 0x800000 bytes with page size 0x10000 failed, retrying with page size 0x1000.
20:46:47 [nvidia-drm] ... Failed to allocate NVKMS memory of size 3342336 for scanout GEM object of Chrome_ChildIOT[4846]
20:55:06 NVRM: dmaAllocMapping_GM107: can't update VA space for mapping @vaddr=0x57a00000
```

- The explicit page size fallback worked every time: no `system_mem.c:460`
  error, so order-4 memory was short for a few minutes but no allocation
  failed. No NVIDIA message after 20:55.
- The VA space errors are the user space driver issue of
  `evidence/2026-10-28-gotg-vaspace-overlap/`; the line number moved with
  the driver release.
- Memory at 22:06 (after the game had exited): Normal zone order 7/8/9/10
  = 382/15/6/3 free blocks; compaction 36 stalls, 1 failure for the boot.
  On 6.18.58 after 20 h 39 min: order 7..10 = 1/0/0/0 and 7844 stalls with
  6207 failures. The uptimes differ too much for a fair comparison.

Inferred, not measured:

- The fewer messages cannot be attributed: driver, kernel and possibly
  Proton changed between the runs.
- The stutters are likely shader compilation: the NVIDIA merged shader
  cache of the game (`nvidiav1/`) was created on 2026-11-05 with the driver
  update, Steam has not replayed it since, and the game recorded 14 MiB of
  new pipelines into its Fossilize cache during the run.

## Open questions

- Is the improvement the driver or the kernel? Run once on 6.18.60 with
  620.70.06 (the fallback kernel), at a similar uptime.
- Do the stutters go away after Steam's next Fossilize replay?
