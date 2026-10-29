#!/usr/bin/env bash
# Design → repo: build the sidebar .riv from the Rive project and copy it here.
#
#   ./update-riv.sh          build the local homy-design project as it is
#   ./update-riv.sh --pull   first pull the latest version from the Rive editor
#                            (overwrites local, unpushed edits in homy-design)
#
# Then commit sidebar.riv and rebuild NixOS. Needs the Rive CLI (`rive`).
set -euo pipefail

PROJECT="${HOMY_DESIGN_PROJECT:-$HOME/Documents/Management/10_Projects/personal/homy-design/Neo_Button}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ "${1:-}" == "--pull" ]]; then
  rive pull "$PROJECT" --yes
fi
rive "$PROJECT" --once
cp "$PROJECT/build/$(basename "$PROJECT").riv" "$HERE/sidebar.riv"
echo "updated $HERE/sidebar.riv"
