# Kernel and driver settings

Settings that made a measurable difference on the test system
(`docs/system.md`), or that follow from the driver internals
(`docs/driver-internals.md`). Each entry says how well it is backed. None of
them replaces the patches: they reduce how often a big sysmem allocation
fails, they cannot guarantee free order-4 or order-9 blocks after days of
uptime.

## Memory management

| Setting | Value | Why | Backed by |
|---|---|---|---|
| `vm.watermark_scale_factor` | 200 | kswapd starts earlier and keeps more free memory, fewer direct reclaim stalls in the driver's allocations | measured 2026-10-18: a game ran 2 h past its usual crash point with 0 failed sysmem allocations and flat `compact_stall` (together with the next line) |
| THP `shmem_enabled` | `advise` (not `within_size`/`always`) | Wine backs anonymous sections with memfd (shmem). With `within_size`, 354301 `thp_file_fallback` vs. 36753 `thp_file_alloc`, each fallback waking kswapd/kcompactd | measured 2026-10-18 |
| THP `enabled` / `defrag` | `madvise` / `defer+madvise` | no synchronous compaction for applications that did not ask for it | in use, not compared |
| `vm.compaction_proactiveness` | 40 to 80 | kcompactd keeps the order-9 fragmentation score lower in the background; only helps for movable pages | in use (60), effect not measured |
| `vm.watermark_boost_factor` | keep the default (15000) | reacts to pageblock stealing by unmovable allocations | reasoning only |
| `vm.min_free_kbytes` | moderate (262144 here) | raising it further does not help: free pages are not the problem, contiguous ones are | observed |
| `vm.defrag_mode` | 0 | 1 caused a compaction storm on this system | observed 2026-10-05 |
| `movablecore=` | do not use | the driver's sysmem is unmovable and cannot live in ZONE_MOVABLE; a movable zone shrinks the space it can use | reasoning only |
| `init_on_alloc` | 0 is possible with the series | The driver zeroes its GPU system memory itself as long as `NVreg_InitializeSystemMemoryAllocations` stays at its default of 1, and the series zeroes the RM heap (`os_alloc_mem()`, patch 45). The nvidia-uvm and nvidia-modeset heaps are not covered; no bug from that is known | code reading, not yet run with 0 | code reading |

`echo 1 > /proc/sys/vm/compact_memory` before starting a game does not reach
order 9 once Unmovable pageblocks are spread over the zone
(`evidence/2026-10-26-gotg-explicit-pagesize/`). A reboot does.

## Driver module options

| Option | Recommendation | Why |
|---|---|---|
| `NVreg_InitializeSystemMemoryAllocations=0` | remove | GPU system memory is then not zeroed by the driver. UVM's channel error notifier comes from such memory, and `uvm_channel.c` treats any non-zero status as an error: a likely cause of spurious "uvm encountered global fatal error" plus Xid 154 seen shortly after boot with driver 580 and this option (code reading) |
| `NVreg_UsePageAttributeTable=1` | remove | does not exist any more, only logs "unknown parameter" |
| `nvidia-drm.modeset=1`, `nvidia-drm.fbdev=1` | keep | required for Wayland compositors |
| `nvidia_drm.vblank` | default | on by default with the series, off upstream; `1` enables the RG vblank callbacks under `nvkms_lock` (see `docs/driver-internals.md`), `0` turns them off |
| `nvidia_drm.deadline_boost` | default | only exists with the series (patch 2); `0` turns the deadline boost off |

## Games

| Setting | Effect |
|---|---|
| `DXVK_CONFIG="dxgi.maxDeviceMemory = <MB>"` (D3D12 via vkd3d-proton reads it too) | lowers the VRAM budget the game sees, so it fills VRAM later and needs sysmem less often. It does not limit what the driver really allocates (11.9 of 12.3 GB were in use with 7000) |
| `VKD3D_CONFIG=no_upload_hvv` | moves upload heaps out of ReBAR VRAM; a game ran 24 min instead of 1.5 min before the same failure |
| Hardware acceleration off in background browsers/chat clients | frees VRAM (about 4 GB were in use by the desktop before a game started) |

With the patches of the 615.78.08 series, the tested game ran a 3 hour
session without the budget workaround; the explicit page size fallback
triggered 8 times (`evidence/2026-10-27-lock-stall-remeasure/`). One session
is not proof that the workaround is no longer needed.

## dmem cgroups

If a tool protects the foreground game with dmem cgroups, it has to use
`dmem.min` for the NVIDIA driver; `dmem.low` is ignored. Do not set a small
`dmem.max` on the compositor's slice: a full Plasma session uses about
1000 MiB of VRAM. See `analysis/2026-10-23-dmemcg.md`.

## Diagnosis

- `/proc/buddyinfo`: free blocks per order. Zone Normal with zeros from
  order 8 or 9 on means big sysmem allocations will fail or stall.
- `/proc/pagetypeinfo` (root): Unmovable vs. Movable pageblocks.
- `grep -E 'compact_(stall|fail|success)|allocstall' /proc/vmstat`
- `journalctl -k | grep -E 'NVRM|x86/PAT|Xid'`
- `tools/trace/nv-pat-latency.bt` for PAT and sysmem latency,
  `tools/trace/nv-sysmem-fail-trace.sh` for failing allocations with their
  order.
