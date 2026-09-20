#!/usr/bin/env bash
# Generic live first-run test for an Omarchy plugin that touches the network.
#
# The normal rig lane intercepts or seeds network data, so it cannot see a dead
# host, an undersized response bound, or a broken fetch. This builds a throwaway
# copy of the plugin whose `curl` is a PASS-THROUGH wrapper: it runs the real
# curl with the plugin's exact argv against the real host and records, per call,
# the URL, curl's exit code and the body size. Nothing is seeded.
#
# Usage: live-first-run.sh <plugin-tree> <label> [min-calls] [wait-seconds]
#   OMARCHY_RIG_HOST / OMARCHY_RIG_CONTAINER select the rig (defaults match the entry repos).
#   A per-call trace (START / KILLED / END with timestamps) is printed after the
#   summary. A START with no END means the plugin stopped its own fetch mid-flight.
# Exit 0 only if at least <min-calls> fetches happened and EVERY one exited 0
# with a non-empty body, and the shell loaded without QML warnings.
set -uo pipefail
src="$(cd "$1" && pwd)"; label="$2"; min_calls="${3:-1}"; wait_s="${4:-45}"
WORK="${LIVE_FIRST_RUN_WORKDIR:-${TMPDIR:-/tmp}/omarchy-live-first-run}"
HOST="${OMARCHY_RIG_HOST:-intent-ops-buzz}"; CONTAINER="${OMARCHY_RIG_CONTAINER:-omarchy-rig}"
T="$WORK/$label"; rm -rf "$T"; mkdir -p "$T"
( cd "$src" && git ls-files -z | xargs -0 -I{} cp --parents -f {} "$T/" )
cd "$T" || exit 9
LOG="/tmp/live-first-run-$label.log"

# 1. No fixtures, no seeded state, no fixture assertions.
rm -rf e2e/bin; mkdir -p e2e/bin
rm -f e2e/rig-after-open.sh
cat > e2e/bin/curl <<WRAP
#!/bin/sh
# Pass-through: the plugin's real argv, the real curl, the real host.
out=\$(mktemp)
url=""
for a in "\$@"; do case "\$a" in https://*|http://*) url="\$a";; esac; done
# A START line with no matching finish means the process was killed mid-flight.
printf 'START %s t=%s\n' "\${url%%\\?*}" "\$(date +%s.%N | cut -c1-14)" >> "$LOG.trace"
trap 'printf "KILLED %s t=%s\n" "\${url%%\\?*}" "\$(date +%s.%N | cut -c1-14)" >> "$LOG.trace"; rm -f "\$out"; exit 143' TERM INT HUP
/usr/bin/curl "\$@" > "\$out" &
cpid=\$!; wait \$cpid; rc=\$?
printf 'END   %s rc=%s t=%s\n' "\${url%%\\?*}" "\$rc" "\$(date +%s.%N | cut -c1-14)" >> "$LOG.trace"
printf '%s rc=%s bytes=%s\n' "\${url%%\\?*}" "\$rc" "\$(wc -c < "\$out")" >> "$LOG"
cat "\$out"; rm -f "\$out"
exit \$rc
WRAP
chmod +x e2e/bin/curl

cat > e2e/rig-before-shell.sh <<HOOK
#!/bin/sh
# First-run user: no cache, no state. Plugin settings from render-settings.json
# still apply, because a first-run user does pick a team or a feed.
set -eu
rm -f "$LOG"
rm -rf "\$HOME/.local/state/omarchy" "\$HOME/.cache/omarchy"
mkdir -p "\$HOME/.local/state/omarchy" "\$HOME/.config/omarchy/plugins"
HOOK

cat > e2e/rig-before-capture.sh <<HOOK
#!/bin/sh
# Give the plugin time to make its first-run fetches, then judge every one.
n=0
while [ \$n -lt $wait_s ]; do
  [ -s "$LOG" ] && [ "\$(wc -l < "$LOG")" -ge $min_calls ] && break
  n=\$((n + 1)); sleep 1
done
sleep 6
echo "curl=\$(/usr/bin/curl --version | head -1 | cut -d' ' -f2) waited=\${n}s" >> "$LOG.meta"
[ -s "$LOG" ] || { echo "LIVE FAIL: the plugin made no network call" >&2; exit 1; }
bad=\$(grep -vcE ' rc=0 bytes=[1-9][0-9]*\$' "$LOG" || true)
[ "\$(wc -l < "$LOG")" -ge $min_calls ] || { echo "LIVE FAIL: fewer than $min_calls fetches" >&2; exit 1; }
[ "\$bad" = "0" ] || { echo "LIVE FAIL: \$bad fetch(es) failed" >&2; exit 1; }
HOOK
chmod +x e2e/rig-before-shell.sh e2e/rig-before-capture.sh

# 2. Make sure the render script puts e2e/bin on PATH (some variants already do).
if ! grep -q 'e2e/bin' scripts/rig-render.sh; then
  sed -i '0,/^qs -p \/root\/omarchy\/shell >/s##export PATH="\\$PLUGIN_DIR/e2e/bin:\\$PATH"\n&#' scripts/rig-render.sh
  grep -q 'e2e/bin' scripts/rig-render.sh || { echo "could not inject PATH hook"; exit 9; }
fi

git init -q . && git add -A > /dev/null 2>&1 && git -c user.email=t@t -c user.name=t commit -qm "live $label" > /dev/null
ssh -o BatchMode=yes "$HOST" "docker exec $CONTAINER sh -c 'rm -f $LOG $LOG.meta $LOG.trace'" 2>/dev/null
t0=$SECONDS
timeout 600 bash scripts/rig-render.sh . "$T/live.png" > "$T/render.log" 2>&1; rc=$?
echo "== $label: rig-render rc=$rc ($((SECONDS - t0))s)"
ssh -o BatchMode=yes "$HOST" "docker exec $CONTAINER sh -c 'cat $LOG.meta 2>/dev/null; echo ---; sort $LOG 2>/dev/null | uniq -c; echo --- trace; cat $LOG.trace 2>/dev/null'" 2>/dev/null | tee "$T/calls.txt" | cut -c1-170
grep -aE 'LIVE FAIL|loaded clean|no QML|warning|coverage|passed' "$T/render.log" | tail -4 | cut -c1-200
exit $rc
