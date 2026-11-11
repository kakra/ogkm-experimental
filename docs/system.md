# Test system

All evidence in this repository was captured on this system unless an
evidence README says otherwise. State as of 2026-11-12.

| Component | Details |
|---|---|
| CPU | Intel Core i7-12700K (20 threads), Intel UHD 770 iGPU without outputs |
| GPU | GeForce RTX 3080 Ti (GA102, Ampere), 12 GiB VRAM, PCIe 4.0, Resizable BAR (BAR1 16 GiB), GSP firmware, VBIOS 94.02.71.40.4c, link at 16 GT/s x16 |
| RAM | 31 GiB, 31 GiB swap; in daily use memory is heavily fragmented (often no free blocks of order 8 or higher in the Normal zone) |
| Displays | 2x 3840x2160 via DisplayPort; 2560x2880 via HDMI (LG SDQHD, TMDS); Samsung TV (2020) via HDMI, FRL up to 10G x4, DSC, 4K120 VRR, usually disabled; the newer monitors run with VRR enabled |
| Distribution | Gentoo Linux |
| Kernel | 7.3.4-gentoo with the patch series from [kakra/linux-patches](https://github.com/kakra/linux-patches) (since 2026-11-12, 7.3.3 since 2026-11-07, 6.18.60 kept as fallback; 6.18.x before), `CONFIG_PREEMPT_LAZY=y`, `CONFIG_HZ=300`, THP `madvise`, `vm.compaction_proactiveness=60` (default 20) |
| Kernel command line | `mitigations=off nvidia-drm.modeset=1 nvidia-drm.fbdev=1 intel_iommu=on iommu=pt` |
| Driver | `x11-drivers/nvidia-drivers-620.70.06` (since 2026-11-05, 615.78.08 before), open kernel modules, built with the series from this repository |
| Desktop | KDE Plasma 6.8.2 on Wayland (KWin) |
| Use | Gaming via Steam/Proton (Vulkan through DXVK/VKD3D-Proton), web browsers, desktop |

## Notes

- Before 2026-10-23 the stock 615.78.08 modules were running. Evidence
  captured before that date shows the unpatched driver.
- The kernel carries the `bcache`, `btrfs`, `gaming` and `platform` series
  from [kakra/linux-patches](https://github.com/kakra/linux-patches). Boot
  options that only belong to those series (such as the btrfs read policy)
  are not listed in the table above; they do not touch the NVIDIA driver.
  The `gaming` series includes working set protection (le9uo), which
  changes page reclaim and can affect memory fragmentation, and with it
  the sysmem fallback behaviour seen in the evidence. The 6.18.59 and
  6.18.60 kernels used before carried it as well (series `memory`), plus
  the BORE scheduler, which 7.3 no longer carries.
- `nvidia_drm.vblank` is left at its default unless an evidence README says
  otherwise.
- The workload that triggers most sysmem problems is a game started after
  several days of uptime, when the page allocator has few high-order blocks
  left. A fresh boot usually does not reproduce them.
