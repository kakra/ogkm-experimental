#!/bin/bash
# Logs failed NVIDIA sysmem allocations (nv_alloc_system_pages) with their
# block order, size and caching type, plus a /proc/buddyinfo snapshot at the
# moment of failure. Run as root while playing; stop with Ctrl+C.
#
# Question: which block size (order) do the allocations that fail right
# before the game crashes request?
set -uo pipefail
T=/sys/kernel/tracing
OUT=${1:-./nv-sysmem-fail-$(date +%Y%m%d-%H%M%S).txt}
EVENTS="nvsys_fail"

# struct nv_alloc_s offsets (pahole -C nv_alloc_s /sys/kernel/btf/nvidia, 615.78.08):
#   flags @24 (contig = bit 0), cache_type @28, num_pages @32, order @36
# nv_alloc_system_pages(nv_state_t *nv, nv_alloc_t *at): at = $arg2
FIELDS='order=+36($arg2):u32 num_pages=+32($arg2):u32 cache_type=+28($arg2):u32 flags=+24($arg2):x16'

cleanup() {
	echo 0 > $T/tracing_on
	for e in $EVENTS; do
		echo '!stacktrace if ret != 0' > $T/events/kprobes/$e/trigger 2>/dev/null
		echo 0 > $T/events/kprobes/$e/enable 2>/dev/null
		echo "-:$e" >> $T/kprobe_events 2>/dev/null
	done
	echo
	echo "Trace saved to $OUT ($(grep -c 'nvsys_fail:' "$OUT") failed allocations)"
	grep -o 'order=[0-9]*' "$OUT" | sort | uniq -c
}

if [ "$(id -u)" != 0 ]; then
	echo "Must run as root" >&2
	exit 1
fi
if [ "$(cat /sys/module/nvidia/version)" != 615.78.08 ]; then
	echo "Warning: struct offsets were taken from 615.78.08, check them with pahole" >&2
fi

echo 0 > $T/tracing_on
echo > $T/trace
echo 16384 > $T/buffer_size_kb

# Return probe with access to the entry arguments ($argN in return probes, 6.10+)
if ! echo "r:nvsys_fail nv_alloc_system_pages ret=\$retval:x32 $FIELDS" >> $T/kprobe_events; then
	echo "Kernel does not support \$argN in return probes" >&2
	exit 1
fi
echo 'ret != 0' > $T/events/kprobes/nvsys_fail/filter
# Triggers ignore the event filter, so the trigger needs its own condition
echo 'stacktrace if ret != 0' > $T/events/kprobes/nvsys_fail/trigger
echo 1 > $T/events/kprobes/nvsys_fail/enable

trap cleanup EXIT
trap 'exit 0' INT TERM
echo 1 > $T/tracing_on
echo "Tracing into $OUT - start the game; Ctrl+C to stop."
{
	echo "# start $(date '+%F %T')"
	cat /proc/buddyinfo
} >> "$OUT"

# Full output incl. stacktraces into the log; terminal shows one line per
# failure (with block size) and a buddyinfo snapshot at most once per second
last=0
while IFS= read -r line; do
	printf '%s\n' "$line" >> "$OUT"
	case "$line" in
	*nvsys_fail:*)
		order=${line##*order=}; order=${order%% *}
		pages=${line##*num_pages=}; pages=${pages%% *}
		printf '%s  %s  block=%dK total=%dM\n' "$(date +%T)" "${line#*nvsys_fail: }" \
			$((4 << order)) $((pages * 4 / 1024))
		now=$(date +%s)
		if [ "$now" != "$last" ]; then
			last=$now
			{ echo "# buddyinfo $(date '+%F %T')"; cat /proc/buddyinfo; } | tee -a "$OUT"
		fi
		;;
	esac
done < $T/trace_pipe
