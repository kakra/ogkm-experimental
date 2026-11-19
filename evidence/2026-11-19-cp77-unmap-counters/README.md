# Cyberpunk 2077 under video memory pressure, unmap counters stay at zero (2026-11-19)

## Setup

- System: see `docs/system.md` (RTX 3080 Ti, 12 GiB video memory).
- Driver: 620.73.04, series `ogkm/620.73.04` at `7ab1b2c6` (157 patches).
  An intermediate state of the series, not exported: it already contains
  veldenb's unmap of the client remainder of a server fragment that starts
  in a hole, veldenb's check against unmapping another resource's DMA
  mapping, the leftover free in `virtmemDestruct()` and the
  `dma_unmap_unregistered` counter (patches 153 to 156 of the series at
  `cee76fcb`). The code of these four patches differs from `cee76fcb` only
  in the leftover free of kernel and P2P mappings and in the counter
  skipping orphaned server fragments (see
  [the series review](../../analysis/2026-11-19-series-review.md)).
- Kernel: 7.3.5-gentoo, booted 2026-11-19 21:07:44, module loaded 21:07:45.
- Workload: Cyberpunk 2077 (Steam app 1091500).
  - Proton Experimental `experimental-11.0-20261112`,
    `PROTON_USE_NTSYNC=1`.
  - `VKD3D_CONFIG=force_bindless_texel_buffer,no_descriptor_heap`
    (descriptor heap path of vkd3d-proton off, unlike
    [the session of the morning](../2026-11-19-cp77-world-loads-620.73.04/)).

## Steps

1. Started the game at 21:27:36 and played until it exited at 22:11:43
   (44 minutes of wall clock time).
2. Afterwards, read the kernel log of the boot and
   `/proc/driver/nvidia/vram_pressure` (22:14:01). Nothing was traced or
   sampled during the session; no frame times were recorded.

## Files

| File | Content |
|---|---|
| `kernel-nvrm-2127-2212.log.xz` | `journalctl -k -o short-iso`, all NVRM and nvidia lines from 21:27 to 22:12 (472 lines) |
| `vram_pressure.txt` | `/proc/driver/nvidia/vram_pressure` at 22:14:01 |

## Result

Measured:

- No Xid in the whole boot. The game ran 44 minutes and exited normally.
- 116 `can't update VA space` failures, each with the same chain:

  ```
  NVRM: nvCheckFailedNoLog: Check failed: status != NV_OK @ gpu_vaspace.c:4088
  NVRM: nvCheckOkFailedNoLog: Check failed: Invalid argument to call [NV_ERR_INVALID_ARGUMENT] (0x0000001F) returned from _gvaspaceMappingInsert(pGVAS, pGpu, pVASBlock, vaLo, vaHi, flags) @ gpu_vaspace.c:1804
  NVRM: nvCheckFailedNoLog: Check failed: NV_OK == status @ virt_mem_allocator_gm107.c:2481
  NVRM: dmaAllocMapping_GM107: can't update VA space for mapping @vaddr=0x291dc0000
  ```

  - First at 22:04:02, last at 22:11:36; none in the first 36.5 minutes
    of the session.
  - Per minute: 22:04 4, 22:05 20, 22:06 19, 22:07 10, 22:08 4, 22:09 18,
    22:10 17, 22:11 24.
  - 49 distinct VAs; some failed repeatedly (0x230000000 10 times,
    0x2a12c0000 and 0x277d00000 8 times each).
- 8 sysmem retries from 64 KiB to 4 KiB pages (7.5 to 16 MiB); the first
  two fall on the same second as the first VA failures.
- None of the messages of the new unmap paths: no "Unmap of unregistered
  DMA mapping range", no "Freeing leftover DMA mapping", no "Duplicate
  inter mapping".
- `vram_pressure`, cumulative since module load:

  | Counter | Count | Bytes | Last event |
  |---|---|---|---|
  | `vidmem_alloc_fail` | 4088 | 120962224128 | 22:11:42 |
  | `sysmem_page_retry` | 8 | 108331008 | 22:09:35 |
  | `dma_map_fail` | 116 | 1877409792 | 22:11:36 |
  | `dma_unmap_fail` | 6036 | 0 | 22:11:43 |
  | `dma_unmap_unregistered` | 0 | 0 | |
  | `gem_*` | 0 | 0 | |

  `dma_map_fail` and `sysmem_page_retry` match the kernel log one to one.

Inferred:

- The VAs occupied at the failed maps do not come from the cases the unmap
  patches handle (a server fragment that starts in a released page, a
  descriptor of another resource found by VA, a leftover on destroy):
  those would have logged or counted.
- `dma_unmap_fail` = 6036 shows many failing unmaps for another reason.
  They appear in the counter only, not in the log. The counters carry no
  time series, so not all of them need to be from the game.

## Open questions

- What makes the 6036 unmaps fail, and whether they leave the VAs that the
  later maps collide with. A trace of the unmap ioctls with their status
  during a burst would show it (`tools/trace/nv-vaspace-ioctl.bt`).
- Whether the descriptor heap setting matters: this session ran with
  `no_descriptor_heap`, the session of the morning without it; both loaded
  the game world.
