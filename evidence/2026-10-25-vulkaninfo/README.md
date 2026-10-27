# vulkaninfo profile of 615.78.08 (2026-10-25)

## Setup

- System: see `docs/system.md`, driver 615.78.08 with the series
- Captured with `vulkaninfo --json` (Vulkan profiles format), GPU device only

## Files

| File | Content |
|---|---|
| `vulkaninfo-profile.json.xz` | Full device profile. `deviceUUID` was replaced by zeros. |

## Result

The driver exposes `VK_EXT_pageable_device_local_memory` (feature
`pageableDeviceLocalMemory` enabled), `VK_EXT_memory_priority` and
`VK_EXT_memory_budget`. Pageable device-local memory means the driver itself
may move device-local allocations to system memory. Since the open kernel
modules contain no eviction code for graphics allocations (no TTM), this
placement is decided in the user-space driver, which then allocates system
memory through `RmDeprecatedVidHeapControl` → `sysmemConstruct`. See
`analysis/2026-10-23-dmemcg.md`.
