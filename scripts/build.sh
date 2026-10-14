#!/usr/bin/env bash
# Builds "ELMS to Reminders.shortcut" from src/elms-to-reminders.cherri:
# compile with Cherri, fix up the plist, check it, then sign it.
#
#   scripts/build.sh            # sign with `shortcuts sign` on a Mac, else HubSign
#   CHERRI=/path/to/cherri scripts/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."

CHERRI="${CHERRI:-cherri}"
OUT="ELMS to Reminders.shortcut"

rm -rf build && mkdir build
cp src/elms-to-reminders.cherri build/
(cd build && "$CHERRI" elms-to-reminders.cherri --skip-sign --debug --no-ansi > cherri.log 2>&1) \
  || { tail -20 build/cherri.log; exit 1; }

python3 scripts/postprocess.py "build/ELMS to Reminders.plist" build/unsigned.shortcut
python3 test/verify.py build/unsigned.shortcut
python3 test/scenarios.py build/unsigned.shortcut > build/scenarios.log \
  || { cat build/scenarios.log; exit 1; }
echo "Checks passed."

if command -v shortcuts > /dev/null; then
  shortcuts sign --mode anyone --input build/unsigned.shortcut --output "$OUT"
else
  # RoutineHub's signing service, the one Cherri uses off macOS. The file
  # holds no ELMS link: that's asked for on import.
  python3 -c 'import json, plistlib, sys
d = plistlib.load(open("build/unsigned.shortcut", "rb"))
json.dump({"shortcutName": "ELMS to Reminders", "shortcut": plistlib.dumps(d).decode()}, sys.stdout)' \
    > build/hubsign.json
  curl -fsS -X POST -H 'Content-Type: application/json' \
    --data-binary @build/hubsign.json -o "$OUT" https://hubsign.routinehub.services/sign
fi
echo "Signed: $OUT"
