#!/usr/bin/env bash
# homy-design → device repo: build every UI surface and copy its .riv into riv/.
#
#   ./sync.sh          build the local homy-design projects as they are
#   ./sync.sh --pull   first pull each one from the Rive editor (overwrites
#                      local, unpushed edits in homy-design)
#
# homy-design holds one folder per design (a complete look: homy-ui, surfaces,
# assets); HOMY_DESIGN_THEME picks which one is built (default: "default").
#
# Then commit riv/ and rebuild NixOS. Needs the Rive CLI (`rive`).
# homy-neo-hmi is the whole screen (top, side and bottom bar in one file).
set -euo pipefail

DESIGN="${HOMY_DESIGN:-$HOME/Documents/Management/10_Projects/personal/homy-design}/${HOMY_DESIGN_THEME:-default}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SURFACES=(homy-neo-hmi)

for s in "${SURFACES[@]}"; do
  project="$DESIGN/$s"
  if [[ "${1:-}" == "--pull" ]] && grep -q '^push:' "$project/rive.yaml"; then
    rive pull "$project" --yes
  fi
  rive "$project" --once
  cp "$project/build/$s.riv" "$HERE/riv/$s.riv"
  echo "  $s.riv  $(wc -c < "$HERE/riv/$s.riv") bytes"
done
