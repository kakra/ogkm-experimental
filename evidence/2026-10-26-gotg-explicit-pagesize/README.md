# Guardians of the Galaxy exits after failed explicit big-page sysmem allocations (2026-10-26)

## Setup

- System: see `docs/system.md`
- Driver: 615.78.08 with patches 1 to 41 of `patches/615.78.08/` (before the
  explicit page size fallback and the lock stall fixes), `nvidia_drm.vblank=1`
- Kernel: 6.18.58, uptime 20 h 39 min at the first failure
- Workload: Marvel's Guardians of the Galaxy (Steam app 1088850), D3D12 via
  vkd3d-proton, 3840x2160. The usual workaround
  `DXVK_CONFIG="dxgi.maxDeviceMemory = 7168"` was **removed** for this test.
- Times are local (CET, UTC+1).

## Steps

1. Desktop session with Chrome and Discord running, uptime about 20 h.
2. Start the game (21:31:27) and play until it exits.
3. After the exit: save `/proc/buddyinfo`, `/proc/meminfo`,
   `/proc/pagetypeinfo` (root), the kernel log.
4. `echo 1 | sudo tee /proc/sys/vm/compact_memory`, save buddyinfo again.
5. Second run with `VKD3D_CONFIG=no_upload_hvv` while
   `sudo bpftrace tools/trace/nv-pat-latency.bt` runs.

## Files

| File | Content |
|---|---|
| `kernel-boot.log.xz` | Kernel log of the boot up to the first run (journal, `-k`) |
| `kernel-2150.log.xz` | Kernel log around the second run |
| `journal-2130-excerpt.log` | Kernel lines and the game's systemd scope from the user journal, 21:30 to 21:35 |
| `buddyinfo.txt` | `/proc/buddyinfo` right after the first failure (21:34) |
| `meminfo.txt` | `/proc/meminfo` at the same time |
| `pagetypeinfo.txt` | `/proc/pagetypeinfo` after the manual compaction |
| `buddyinfo-after-compact.txt` | `/proc/buddyinfo` after `compact_memory` |
| `buddyinfo-2221.txt` | `/proc/buddyinfo` after the second run (22:21) |
| `nv-pat-2155.log` | Output of `nv-pat-latency.bt` during the second run (live lines only; the histograms were lost because Ctrl+C also ended the `tee`. Use `bpftrace -o <file>`.) The warnings at the top come from an older version of the script; the version in `tools/trace/` has the casts. |

## Result

### First run (21:31:27 to 21:33:01)

```
21:33:00.393 NVRM: ... Out of memory ... _memdescAllocInternal(pMemDesc) @ mem_desc.c:1354
21:33:00.403 NVRM: ... Out of memory ... rmStatus @ system_mem.c:460
   (4 such pairs within 60 ms; no nv_gpu_ops.c line, no "retrying with page size")
21:33:01.486 systemd: app-steam-app1088850-553478.scope: Consumed 6min 13.677s CPU time
             over 1min 34.199s wall clock time, 6.2G memory peak.
```

No coredump, no Xid. Line mapping in the installed tree (patches 1 to 41):

- `mem_desc.c:1352` is the LEVEL_INFO print of a fail-fast attempt,
  `mem_desc.c:1354` the LEVEL_ERROR print of a normal allocation.
- `system_mem.c:444`: the last page size of RM's own retry walk failed
  (`PAGE_SIZE_DEFAULT` requests); `:456`: fail-fast attempt that the caller
  retries (LEVEL_INFO); `:460`: allocation with an explicit page size, which
  nothing retries (LEVEL_ERROR).
- A UVM allocation would add an `nv_gpu_ops.c` line.

So all four failures are allocations by a user-space RM client (the Vulkan
driver under vkd3d-proton) with an explicit big page size, through
`RmDeprecatedVidHeapControl` → `sysmemConstruct_IMPL`. They ran with
`__GFP_RETRY_MAYFAIL`, failed after reclaim and compaction, and nothing
retried them. The game exited one second later.

Release builds only print LEVEL_ERROR, so fail-fast failures (`:1352`,
`:456`) never show up in the log.

### Memory state after the failure (21:34)

```
Node 0, zone    DMA32   5320 3958 2292 1853 363 269 262 72 17  0 0
Node 0, zone   Normal 390491 207150 60832 20307 1058 50 1 1  0  0 0
```

MemFree 5.0 GB, MemAvailable 13.5 GB, no free order-9 block in any zone, order
6 and up practically empty in Normal. For the boot: `compact_stall` 7844,
`compact_fail` 6207, `compact_success` 1637. VRAM in use after the game had
exited: 5.5 of 12 GB.

vm settings: `compaction_proactiveness=60`, `extfrag_threshold=500`,
`min_free_kbytes=262144`, `watermark_scale_factor=200`,
`watermark_boost_factor=15000`; THP `madvise`, defrag `defer+madvise`.

### After `compact_memory`

Normal order 5 to 9 went from 50/1/1/0/0 to 1922/441/83/16/0: compaction
reaches order 8, never order 9. `pagetypeinfo` (Normal): 4130 Unmovable, 11017
Movable, 336 Reclaimable pageblocks. About 2.8 GB of the free memory sits in
Unmovable pageblocks (orders 1 to 6), which compaction does not touch; Movable
blocks hold only about 1.85 GB free and top out at order 8. 8 GB of Unmovable
pageblocks against about 1 GB of slab and page tables points to pageblock
stealing by unmovable allocations over the uptime. Suspects are NVIDIA sysmem
and btrfs metadata; not proven (would need `page_owner=on`).

### Second run with `VKD3D_CONFIG=no_upload_hvv` (21:56:39 to 22:20:18)

Ran 23 min 39 s (7.5 GB memory peak), then the same four
`mem_desc.c:1354` + `system_mem.c:460` pairs at 22:20:17.73; the scope ended
22:20:18.99. Buddyinfo at 22:21: Normal order 7 to 9 = 2/2/0, DMA32 order 9 =
12 (after the game had exited).

During the run, 14 blocks of `dmaAllocMapping_GM107: can't update VA space`
with `gpu_vaspace.c:4502` asserts appeared between 21:58 and 22:20, although
upstream PR [#1483][pr-1483] was already in the series.

`nv-pat-2155.log`: 17 calls of `nv_free_system_pages()` over 2 ms in about 20
minutes. Chrome: 11 of 2.0 to 3.5 ms, every 30 s to 3 min. The game
(`JobWorkerThread`): 5 frees of 3.4 to 5.7 ms in the same second 22:20:18,
about 22 ms together, which is the teardown after the failure.

## Consequences

- Fallback to smaller pages for explicit big-page requests: patch
  "nvidia: retry explicit big-page sysmem allocations with smaller pages"
  (patch 42), see `analysis/2026-10-24-sysmem-fragmentation.md`.
- The slow frees led to `analysis/2026-10-26-lock-stalls.md`.

## Open questions

- Which order the failing requests had (64 KB or 2 MB pages). The fallback
  patch logs it now.
- Whether NVIDIA sysmem is the main source of Unmovable pageblocks.

[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
