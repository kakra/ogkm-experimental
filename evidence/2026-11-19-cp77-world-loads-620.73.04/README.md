# Cyberpunk 2077 loads into the game world again, VA space failures remain (2026-11-19)

## Setup

- System: see `docs/system.md` (RTX 3080 Ti, 12 GiB video memory).
- Driver: 620.73.04, series `ogkm/620.73.04` at `380b6ba1` (145 patches,
  including the video memory pressure counters and veldenb's no-op unmap of
  an unregistered DMA mapping range).
- Kernel: 7.3.5-gentoo, booted 2026-11-19 01:36, about 20 minutes uptime at
  the first game start.
- Workload: Cyberpunk 2077 (Steam app 1091500), game build 26161058
  (unchanged since 2026-10-23).
  - Proton Experimental `experimental-11.0-20261112` (installed 2026-11-13).
  - DXVK `v3.1.1-209-g1039f682058fa71`, read from the installed DLLs.
  - vkd3d-proton `2576c0b4ad`. Inferred, not read from the DLLs, which carry
    no version string: the Proton build tag of that date, whose DXVK hash
    matches the DLLs.
  - 3840x2160 fullscreen; DLSS super resolution Ultra Performance with the
    Transformer 2 preset; ray reconstruction and frame generation off.
  - Ray tracing on: reflections, sun and local shadows, lighting Medium.
    Path tracing off.
  - Reflex Enabled + Boost, VSync off, game frame limit off.
  - Environment: `VKD3D_CONFIG=force_bindless_texel_buffer` (set by Proton
    for this game), `PROTON_USE_NTSYNC=1`, MangoHud as a frame limiter
    only (`no_display,fps_limit=60+30+0,fps_limit_method=early`), the OBS
    Vulkan capture layer loaded.
  - In the background: Plasma desktop, Chrome, Discord, Steam.

## Steps

1. Session 1: started the game at 01:57:50, loaded a save into the game
   world, switched between the world and the menus, quit at about 02:02:29.
2. Session 2: started at 02:06:42, changed the graphics preset in the menu,
   played until 02:19:22.
3. Afterwards: read the kernel log, `/proc/driver/nvidia/vram_pressure`
   (also once during session 2) and `nvidia-smi`. Nothing was traced live
   and no frame times were recorded.

## Files

| File | Content |
|---|---|
| `kernel-nvrm-0157-0220.log.xz` | `journalctl -k -o short-iso-precise`, NVRM and nvidia-drm lines, 01:50 to 02:20 (662 lines, both sessions) |
| `game-scopes.log` | start and end of the game's systemd scopes, with CPU time and memory peak |
| `vram_pressure-snapshots.txt` | `/proc/driver/nvidia/vram_pressure` at 02:06:03, 02:10:44 and 02:23:54 |
| `host-state.txt` | kernel, driver build, `nvidia-smi` memory use and graphics clients after both sessions |

## Result

### The game world loads and runs

Measured:

- Both sessions ran without an Xid, an MMU fault or a device lost:

  | Session | Time | Duration |
  |---|---|---|
  | 1 | 01:57:50 to 02:02:30 | 4:40 |
  | 2 | 02:06:44 to 02:19:23 | 12:39 |

  The whole boot has no `Xid` line from the GPU and no coredump of the
  game; vkd3d-proton logging was off (`VKD3D_DEBUG=none`). The scopes ended
  with:

  ```
  app-steam-app1091500-30499.scope: Consumed 35min 18.596s CPU time over 4min 39.915s wall clock time, 10.9G memory peak, 35.5M memory swap peak.
  app-steam-app1091500-35695.scope: Consumed 1h 19min 15.707s CPU time over 12min 39.520s wall clock time, 9.9G memory peak, 49.2M memory swap peak.
  ```

- Before this, from 615.x through 620.70.06, the game did not survive
  loading the world (player's report). On 2026-11-06 the system ran 620.70.06 with the series
  (before patches 134 to 145) on kernel 6.18.60. Two starts that day:

  | Start | Failure | Process | Channel |
  |---|---|---|---|
  | 00:23:30 | Xid 109 at 00:25:01 | GameThread | 0x24 |
  | 19:00:45 | Xid 13, Graphics Exception, class c7c0, on all GPCs, at 19:02:06 | GameThread | 0x24 |

  Both failures came 80 to 90 s after the start. No VA space failure
  preceded them, and no Xid 31 named a fault address. The earlier Xid 109
  is classified in `analysis/2026-10-26-xid109-cyberpunk.md`. The raw logs
  of 2026-11-06 were not added here.

Not known: which change made the difference. Several changed at once since
2026-11-06:

- kernel 6.18.60 to 7.3.5;
- driver 620.70.06 to 620.73.04;
- the series, including patch 145, the no-op unmap of an unregistered DMA
  mapping range;
- vkd3d-proton, from about 3.1 (Proton Experimental of 2026-10-30, again
  inferred from the build tags) to `2576c0b4ad`. In that range vkd3d-proton
  made the descriptor heap path the default (`de580e7579`), enabled
  descriptor heap robustness by default (`f05a77108e`), discards failed
  ray tracing acceleration structure builds (`ac5c879447`) and fixed the
  initial residency check (`c0dd9bfa1f`);
- the game environment: on 2026-11-06 `VKD3D_DISABLE_EXTENSIONS` was set
  (Fossilize logged "Skipping recording due to environment rule for:
  VKD3D_DISABLE_EXTENSIONS"); it is not set now.

### The VA space failure chain at scene changes

Measured:

- The chain is the same as in the GotG sessions
  (`analysis/2026-10-28-vaspace-overlap.md`,
  `evidence/2026-11-01-gotg-vaspace-vram-pressure/`). In 620.73.04 it is
  still at line 4088:

  ```
  02:02:17.634297 NVRM: GPU0 sysmemConstruct_IMPL: Sysmem alloc of 0x5760000 bytes with page size 0x10000 failed, retrying with page size 0x1000.
  02:02:17.684291 NVRM: nvCheckFailedNoLog: Check failed: status != NV_OK @ gpu_vaspace.c:4088
  02:02:17.684877 NVRM: nvCheckOkFailedNoLog: Check failed: Invalid argument to call [NV_ERR_INVALID_ARGUMENT] (0x0000001F) returned from _gvaspaceMappingInsert(pGVAS, pGpu, pVASBlock, vaLo, vaHi, flags) @ gpu_vaspace.c:1804
  02:02:17.684905 NVRM: nvCheckFailedNoLog: Check failed: NV_OK == status @ virt_mem_allocator_gm107.c:2481
  02:02:17.685187 NVRM: dmaAllocMapping_GM107: can't update VA space for mapping @vaddr=0x280160000
  ```

  It occurs although patch 145 is in the series; that patch targets the
  "Duplicate inter mapping detected" follow-up failure, not this check.

- Session 1: all failures fell between 02:02:17 and 02:02:24, just before
  the game window closed. In total, 13 `can't update VA space` and 4 sysmem
  retries from 64 KiB to 4 KiB pages:

  | Time | Retry size | VA failures |
  |---|---|---|
  | 02:02:17 | 0x5760000 (87 MiB) | 1 |
  | 02:02:20 | 0x3fc0000 (64 MiB) | 5 |
  | 02:02:22 | 0x5760000 | 1 |
  | 02:02:23 | | 5 |
  | 02:02:24 | 0x5760000 | 1 |

- Session 2: 40 bursts (lines less than 3 s apart) with 150 VA failures.
  - Sysmem retries only once, at 02:08:30: 0x800000, 0x800000 and 0x1000000.
  - 02:08:30 to 02:09:01: four bursts (1, 2, 5, 5).
  - Then two minutes without failures.
  - From 02:11:03 to the end, a burst every 4 to 13 s with 1 to 7 failures
    each, and larger ones at 02:15:20 (12 in 4 s), 02:16:20 (13 in 3 s) and
    02:16:29 (7 in 6 s).
  - The last burst was at 02:19:10.

- When the game closed (02:19:22), nvidia-drm fell back for Xwayland:

  ```
  [nvidia-drm] [GPU ID 0x00000100] Failed to allocate compressible NVKMS video memory of size 20578304 for GEM object of Xwayland[3088], retrying without compression
  [nvidia-drm] [GPU ID 0x00000100] Failed to allocate NVKMS video memory for GEM object of Xwayland[3088], trying to fall back to sysmem
  ```

- `vram_pressure`, cumulative since boot (count / bytes):

  | Counter | 02:06:03 | 02:10:44 | 02:23:54 |
  |---|---|---|---|
  | `vidmem_alloc_fail` | 456 / 12.0 GB | 4156 / 43.2 GB | 6144 / 100.1 GB |
  | `sysmem_page_retry` | 4 | 8 | 8 |
  | `dma_map_fail` | 13 | 26 | 163 |
  | `dma_unmap_fail` | 683 | 1963 | 5010 |
  | `gem_no_compression` / `gem_sysmem_fallback` | 0 / 0 | 0 / 0 | 1 / 1 (20.6 MB) |

  `dma_map_fail` matches the `can't update VA space` lines one to one
  (13 in session 1, 13 + 150 = 163 after session 2).

- Rates per minute of game time in session 2:

  | Period | `vidmem_alloc_fail` | `dma_map_fail` | `dma_unmap_fail` |
  |---|---|---|---|
  | Start to 02:10:44, about 4 min | 790 (6.6 GB) | 2.8 | 273 |
  | 02:10:44 to the end at 02:19:23, 8.65 min | 230 (6.6 GB) | 15.8 | 352 |

  The share moved from failed video memory allocations to failed
  mappings.

- The last events of all counters fall on the end of session 2
  (`vidmem_alloc_fail` 02:19:23.0, `dma_map_fail` 02:19:14,
  `dma_unmap_fail` 02:19:23.2).

- After both sessions, without the game, `nvidia-smi` showed 3349 MiB of
  12288 MiB in use. The largest graphics clients:

  | Client | Video memory |
  |---|---|
  | Chrome GPU process | 906 MiB |
  | kwin_wayland | 407 to 487 MiB |
  | plasmashell | 347 MiB |
  | plasma-keyboard | 224 MiB |
  | steamwebhelper | 83 MiB |
  | Discord | 60 MiB |

  So the game had at most about 8.9 GiB.

Observed by the player, not measured:

- Frame pacing stutter, often at the same time as the NVRM bursts.
- After a preset change, the frame rate first stayed at about 30
  (Performance) or 40 to 45 (Ultra Performance), then rose over minutes to
  58 to 60 at 90 to 95 % GPU load (60 fps cap).

Inferred, not measured:

- Resources that fail in video memory stay in the sysmem fallback.
- The stutter is the cost of each failed allocation, fallback and failed
  mapping.
- Without frame times this is not shown.

## Open questions

- Which change fixed the world load. A split test with the current setup:
  `VKD3D_CONFIG=force_bindless_texel_buffer,no_descriptor_heap` (descriptor
  heap path off). If the crash comes back, the vkd3d-proton heap path or its
  robustness default is involved. `PROTON_LOG=1 VKD3D_DEBUG=info` would also
  record the exact vkd3d-proton version and the active descriptor path.
- Whether the stutter lines up with the VA failure bursts. A correlated
  capture would need:
  - MangoHud frame times
    (`MANGOHUD_CONFIG=autostart_log=1,log_interval=0,output_folder=<dir>`);
  - `journalctl -kf -o short-iso-precise | grep --line-buffered NVRM`;
  - `/proc/driver/nvidia/vram_pressure` sampled every 0.5 s with a time
    stamp, or `tools/vram-pressure.py` recording.
- Whether the user space driver maps a stale VA here as in the GotG case;
  `tools/trace/nv-vaspace-ioctl.bt` during a burst would show the caller.

## References

- Upstream issue [#1364][issue-1364] ("can't update VA space")

[issue-1364]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1364
