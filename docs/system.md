# Test system

All evidence in this repository was captured on this system unless an
evidence README says otherwise. State as of 2026-10-27.

| Component | Details |
|---|---|
| CPU | Intel Core i7-12700K (20 threads), Intel UHD 770 iGPU without outputs |
| GPU | GeForce RTX 3080 Ti (GA102, Ampere), 12 GiB VRAM, PCIe 4.0, Resizable BAR (BAR1 16 GiB), GSP firmware |
| RAM | 31 GiB, 31 GiB swap; in daily use memory is heavily fragmented (often no free blocks of order 8 or higher in the Normal zone) |
| Displays | 2x 3840x2160 via DisplayPort; 2560x2880 via HDMI (LG SDQHD, TMDS); Samsung TV (2020) via HDMI, FRL up to 10G x4, DSC, 4K120 VRR, usually disabled |
| Distribution | Gentoo Linux |
| Kernel | 6.18.58-gentoo, `CONFIG_PREEMPT_LAZY=y`, `CONFIG_HZ=300`, THP `madvise` |
| Kernel command line | `mitigations=off nvidia-drm.modeset=1 nvidia-drm.fbdev=1 intel_iommu=on iommu=pt` |
| Driver | `x11-drivers/nvidia-drivers-615.78.08`, open kernel modules, built with the series from this repository |
| Desktop | KDE Plasma 6.8.1 on Wayland (KWin) |
| Use | Gaming via Steam/Proton (Vulkan through DXVK/VKD3D-Proton), web browsers, desktop |

## Notes

- Before 2026-10-23 the stock 615.78.08 modules were running. Evidence
  captured before that date shows the unpatched driver.
- `nvidia_drm.vblank` is left at its default unless an evidence README says
  otherwise.
- The workload that triggers most sysmem problems is a game started after
  several days of uptime, when the page allocator has few high-order blocks
  left. A fresh boot usually does not reproduce them.
