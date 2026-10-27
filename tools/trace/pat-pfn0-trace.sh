#!/bin/bash
# Finds the source of the "x86/PAT: freeing invalid memtype [mem 0x0-0xfff]" messages.
# Run as root while playing; event lines show up live, full stacktraces go to the log.
# Stop with Ctrl+C.
#
# Key question: does the PFN-0 entry come from remap_pfn_range (the driver maps
# phys 0, i.e. an uninitialized/empty page_table entry), or does the
# pfnmap_track_ctx only hold pfn 0 at release time (corruption / use-after-free)?
set -uo pipefail
T=/sys/kernel/tracing
OUT=${1:-./pat-pfn0-trace-$(date +%Y%m%d-%H%M%S).txt}
EVENTS="pfn0_remap pfn0_release pfn0_memfree"

cleanup() {
	echo 0 > $T/tracing_on
	echo 0 > $T/options/stacktrace
	for e in $EVENTS; do
		echo 0 > $T/events/kprobes/$e/enable 2>/dev/null
		echo "-:$e" >> $T/kprobe_events 2>/dev/null
	done
	echo
	echo "Trace saved to $OUT ($(grep -c 'pfn0_' "$OUT") events)"
	grep -o 'pfn0_[a-z]*' "$OUT" | sort | uniq -c
}

if [ "$(id -u)" != 0 ]; then
	echo "Must run as root" >&2
	exit 1
fi

echo 0 > $T/tracing_on
echo > $T/trace
echo 65536 > $T/buffer_size_kb

# remap_pfn_range(vma=%di, addr=%si, pfn=%dx, size=%cx, prot=%r8)
echo 'p:pfn0_remap remap_pfn_range addr=%si:x64 pfn=%dx:u64 size=%cx:u64' >> $T/kprobe_events
# pfnmap_track_ctx_release(ref=%di); struct pfnmap_track_ctx { kref; pfn @+8; size @+16 }
echo 'p:pfn0_release pfnmap_track_ctx_release pfn=+8(%di):u64 size=+16(%di):u64' >> $T/kprobe_events
# memtype_free(start=%di, end=%si) - who else frees the [0,0x1000) entry?
echo 'p:pfn0_memfree memtype_free start=%di:u64 end=%si:u64' >> $T/kprobe_events

echo 'pfn == 0' > $T/events/kprobes/pfn0_remap/filter
echo 'pfn == 0' > $T/events/kprobes/pfn0_release/filter
echo 'start == 0' > $T/events/kprobes/pfn0_memfree/filter

echo 1 > $T/options/stacktrace
for e in $EVENTS; do echo 1 > $T/events/kprobes/$e/enable; done

trap cleanup EXIT
trap 'exit 0' INT TERM
echo 1 > $T/tracing_on
echo "Tracing into $OUT - start the game; Ctrl+C to stop."
# Full output incl. stacktraces into the log, only the event lines to the terminal
cat $T/trace_pipe | tee "$OUT" | grep --line-buffered 'pfn0_'
