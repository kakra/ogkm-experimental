# PAT and sysmem latency after moving non-cached frees to a kthread (2026-10-27)

## Setup

- System: see `docs/system.md`
- Driver: 615.78.08 with patches 1 to 44 of `patches/615.78.08/`. Compared
  to `2026-10-26-gotg-explicit-pagesize` this adds patches 42 ("nvidia:
  retry explicit big-page sysmem allocations with smaller pages"), 43
  ("nvidia: don't retry high-order kmalloc in os_alloc_mem()") and 44
  ("nvidia: free non-cached system memory from a kthread")
- Kernel: 6.18.58, boot 2026-10-26 23:11:59, capture about 3 h after boot
- Workload: Guardians of the Galaxy again, **without** the
  `dxgi.maxDeviceMemory` workaround (VRAM runs full), Chrome in the background
- Times are local (CET, UTC+1).

## Steps

1. Boot, start the game.
2. `sudo bpftrace -o nv-pat-after.log tools/trace/nv-pat-latency.bt` during
   play, Ctrl+C at the end (prints the histograms).
3. Save the kernel log of the boot.

## Files

| File | Content |
|---|---|
| `nv-pat-after.log` | Live lines (frees over 2 ms) and histograms of `nv-pat-latency.bt`, all values in µs |
| `kernel-boot.log.xz` | Kernel log of the boot, 23:12 to 02:15 |

## Result

### Frees: moved out of the application thread

- `@wb_comm`: all 5153 write-back resets (`set_pages_array_wb`) ran in the
  `nv_free_queue` kthread, none in an application thread.
- 136 frees over 2 ms (maximum 6.3 ms), all in `nv_free_queue`. Before the
  change, these ran in the freeing thread under the GPU lock and the RW API
  lock (see `analysis/2026-10-26-lock-stalls.md`).
- From 01:42 on, one or two slow frees every minute at :21 with growing
  duration (2.2 ms to 6.3 ms). A periodic alloc/free cycle of some client;
  the growth fits a growing PAT memtype tree. Not analyzed further.

### Allocation side: the next candidate

- `@uc_us` (`set_pages_array_uc` on allocation): 128 calls of 8 to 16 ms, 17
  calls of 32 to 64 ms.
- `@alloc_us` (`nv_alloc_system_pages`): 152 calls of 8 to 16 ms, 17 of 32 to
  64 ms, one of 256 to 512 ms.
- This runs synchronously in the allocating thread (the game) under the RO API
  lock, which holds off writers. It matches stutter when assets stream in. No
  histogram of the earlier run exists, so there is no direct before/after
  comparison; the two lock stall patches do not touch this path.

### VRAM pressure

- 6144 `Failed to allocate NVKMS memory of size 3342336 for scanout GEM object`
  (23:41 to 00:19, up to 300 per minute), plus 24 fallbacks from video to
  system memory and 24 "retrying without compression" from the GEM retry
  patch. Each failed attempt is an RM allocation under the locks. The log has
  no process name for these.

### Sysmem fallback

- 8 `sysmemConstruct_IMPL: Sysmem alloc of 0x1000000 bytes with page size
  0x10000 failed, retrying with page size 0x1000.` (first at 23:40:49): the
  explicit requests that killed the game on 2026-10-26 use 64 KB pages, and
  the 4 KB fallback succeeded every time. No follow-up error, no Xid, no PAT
  flood, the game kept running.

### Other

- `gpu_vaspace.c` blocks ("can't update VA space") are still there: 65 blocks
  in 3 h (baseline before PR [#1483][pr-1483]: 29 in 32 h). The PR does not
  remove them.
- `compact_stall` 73 and `compact_fail` 61 in 3 h; a fresh boot, so this says
  little about the `os_alloc_mem()` change.

## Open questions

- Who allocates the 3.2 MB scanout GEM objects that fail: bpftrace on
  `nv_drm_gem_alloc_nvkms_memory_ioctl` with `comm`.
- A pool of pages that already have the WC/UC memtype would save the PAT
  change on both alloc and free.
- Whether the 64 KB to 4 KB fallback has a GPU-side cost (TLB, mapping) in
  long sessions.

[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
