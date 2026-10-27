# Xid 109 in Cyberpunk 2077: not a regression of the series

- **Status:** classified, no fix
- **Evidence:** kernel log in `evidence/2026-10-26-gotg-explicit-pagesize/kernel-boot.log.xz`
  (01:06:45)

## Event

First start of Cyberpunk 2077 (Steam app 1091500, Proton Experimental,
vkd3d-proton) after the 2.5 game update and after the reboot into the series
(at 41 patches, `nvidia_drm.vblank=1`):

```
01:06:45 NVRM: Xid (PCI:0000:01:00): 109, pid=22417, name=GameThread, channel 0x00000028,
         errorString CTX SWITCH TIMEOUT, Info 0x23c030
```

The game hung on the GPU after the shader compile phase and was killed by
hand. No vkd3d-proton error, no device lost, no segfault, no flip timeout. The
first Xid on this system since the journal started (2026-09-14). Game
settings: DLSS Ultra Performance, ray tracing on (no path tracing), Reflex
enabled + boost, no frame generation.

## Comparison

- open-gpu-kernel-modules issue [#1282][issue-1282] (Cyberpunk 2077 with DLSS
  on, driver 610.57.04): the open modules log `gpu_vaspace` "can't update VA
  space" errors, the proprietary ones end with `Xid 109, name=GameThread, CTX
  SWITCH TIMEOUT`. Same signature, reported before any of the patches here
  existed.
- The NVIDIA forum thread "615 release feedback & discussion" has several Xid
  109 reports on 615.x, all with Proton (vkd3d-proton or DXVK) and
  GameThread/MainThread channels, some with internal bug numbers and internal
  reproductions (Monster Hunter Wilds, Plague Tale Requiem, God of War
  Ragnarök, 007 First Light with path tracing).
- A Proton issue ([ValveSoftware/Proton#4450][proton-4450]) reports a shader
  compiler crash (SIGILL in `libnvidia-gpucomp.so`) for a new compute shader of
  the 2.5 update on Turing. Different symptom (no SIGILL here); a link is
  unproven.

## Conclusion

The Xid 109 matches the known Cyberpunk ray tracing/DLSS hang, documented on
610.57.04 before the series. The patches of the series act on display, flip,
memory allocation and lock paths; an Xid 109 in a GameThread channel is a
graphics context switch timeout. Not treated as a regression. Next time:
`PROTON_LOG=1 VKD3D_DEBUG=warn` to see the last pipeline before the hang, and
a run on the stock driver.

[issue-1282]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1282
[proton-4450]: https://github.com/ValveSoftware/Proton/issues/4450
