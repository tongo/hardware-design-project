#!/bin/bash
# ERC (+ DRC con parità schema–PCB, se esiste il PCB) con riassunto compatto.
# Uso: tools/check.sh [dir-progetto] [--max N]
# Report completi: build/reports/erc.json, build/reports/drc.json
# Uscita: 0 = nessun errore, 1 = errori trovati, 2 = problema di esecuzione.
set -uo pipefail

TOOLS="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$TOOLS")"
DIR=""
MAX=15
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --max) MAX="$2"; shift 2 ;;
    *) DIR="$1"; shift ;;
  esac
done

eval "$(python3 "$TOOLS/hwproj.py" --shell ${DIR:+"$DIR"})" || exit 2
OUT="$REPO/build/reports"
mkdir -p "$OUT"
rm -f "$OUT/erc.json" "$OUT/drc.json"

[ -n "$PRJ_SCH" ] || { echo "ERRORE: schema $PRJ_NAME.kicad_sch non trovato in $PRJ_DIR"; exit 2; }

echo "Progetto: $PRJ_NAME ($(realpath --relative-to="$REPO" "$PRJ_DIR"))  kicad-cli $(kicad-cli version)"
if [ -z "$PRJ_DRU" ]; then
  echo "ATTENZIONE: manca $PRJ_NAME.kicad_dru: le regole JLC non sono applicate al DRC."
  echo "            Copia: cp rules/jlcpcb-2layer.kicad_dru $(realpath --relative-to="$REPO" "$PRJ_DIR")/$PRJ_NAME.kicad_dru"
fi

ARGS=("$OUT/erc.json")
if ! kicad-cli sch erc "$PRJ_SCH" --format json --severity-all --units mm -o "$OUT/erc.json" >"$OUT/erc.log" 2>&1; then
  if [ ! -s "$OUT/erc.json" ]; then echo "ERRORE: ERC non eseguito, vedi build/reports/erc.log"; tail -5 "$OUT/erc.log"; exit 2; fi
fi

if [ -n "$PRJ_PCB" ]; then
  if ! kicad-cli pcb drc "$PRJ_PCB" --format json --severity-all --schematic-parity --units mm -o "$OUT/drc.json" >"$OUT/drc.log" 2>&1; then
    if [ ! -s "$OUT/drc.json" ]; then echo "ERRORE: DRC non eseguito, vedi build/reports/drc.log"; tail -5 "$OUT/drc.log"; exit 2; fi
  fi
  ARGS+=("$OUT/drc.json")
else
  echo "(PCB non presente: solo ERC)"
fi

python3 "$TOOLS/report_summary.py" --max "$MAX" "${ARGS[@]}"
