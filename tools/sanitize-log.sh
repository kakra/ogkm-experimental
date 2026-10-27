#!/bin/bash
# Remove private data from logs before they are added to evidence/.
#
# Usage: tools/sanitize-log.sh [-n] <file>...
#
# Edits the files in place (.xz files are decompressed and recompressed) and
# prints every replaced line to stderr for review. With -n, only reports.
#
# Replaced: the host name, the user name and home directory, mail
# addresses, MAC addresses, file system and partition UUIDs, serial numbers
# (dmidecode, nvidia-smi, USB, disk), the machine id and Steam user ids.
# Add more with SANITIZE_EXTRA, a file of
# "pattern<TAB>replacement" lines (Perl regex).

set -euo pipefail

dry=
if [[ ${1-} == -n ]]; then
	dry=1
	shift
fi
(($#)) || {
	echo "usage: ${0##*/} [-n] <file>..." >&2
	exit 2
}

export SAN_HOST=${SANITIZE_HOST:-$(hostname -s)}
export SAN_USER=${SANITIZE_USER:-$(id -un)}
export SAN_HOME=${SANITIZE_HOME:-$HOME}
export SAN_EXTRA=${SANITIZE_EXTRA:-}

# shellcheck disable=SC2016
filter='
BEGIN {
	@rules = (
		[qr/\Q$ENV{SAN_HOME}\E/, q{~}],
		[qr/\/home\/\Q$ENV{SAN_USER}\E\b/, q{~}],
		[qr/\b\Q$ENV{SAN_HOST}\E\b/i, q{host}],
		[qr/(?<!github\.com\/)\b\Q$ENV{SAN_USER}\E\b/, q{user}],
		[qr/[\w.+-]+@(?!\d)[\w-]+(?:\.[\w-]+)+/, q{user\@example.org}],
		[qr/\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b/i, q{00:00:00:00:00:00}],
		[qr/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i,
			q{00000000-0000-0000-0000-000000000000}],
		[qr/((?:Serial(?: Number)?|serial|SerialNumber|iSerial|ID_SERIAL(?:_SHORT)?)\s*[:=]\s*)\S.*$/,
			q{${1}REDACTED}],
		[qr/((?:UUID|PARTUUID|md\.uuid|machine[-_]id)[=:]\s*)[0-9a-f:-]{8,}/i, q{${1}REDACTED}],
		[qr/\b7656119\d{10}\b/, q{STEAMID}],
	);
	if ($ENV{SAN_EXTRA} ne "") {
		open my $fh, "<", $ENV{SAN_EXTRA} or die "$ENV{SAN_EXTRA}: $!\n";
		while (<$fh>) {
			chomp;
			next if /^\s*(#|$)/;
			my ($p, $r) = split /\t/, $_, 2;
			push @rules, [qr/$p/, $r];
		}
	}
}
my $orig = $_;
for my $r (@rules) {
	my ($p, $s) = @$r;
	s/$p/"qq{$s}"/gee;
}
if ($_ ne $orig) {
	chomp(my $o = $orig);
	chomp(my $n = $_);
	print STDERR "$ARGV:$.: $o\n  => $n\n";
}
close ARGV if eof;
'

for f in "$@"; do
	case $f in
	*.xz)
		tmp=$(mktemp "$f.XXXXXX")
		xz -dc -- "$f" | perl -ne "$filter; print" >"$tmp"
		if [[ -n $dry ]]; then rm -f "$tmp"; else xz -9 -c "$tmp" >"$f" && rm -f "$tmp"; fi
		;;
	*)
		if [[ -n $dry ]]; then
			perl -ne "$filter" -- "$f"
		else
			perl -i -pe "$filter" -- "$f"
		fi
		;;
	esac
done
