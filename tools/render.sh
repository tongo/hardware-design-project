#!/bin/bash
# Render PNG del PCB (sopra e sotto) e PDF/PNG dello schema, in build/render/.
# Uso: tools/render.sh [dir-progetto] [--width 1200] [--no-sch] [--no-pcb]
# Stampa solo l'elenco dei file creati. Log in build/render/render.log.
set -uo pipefail

TOOLS="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$TOOLS")"
DIR=""; W=1200; DO_SCH=1; DO_PCB=1
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --width) W="$2"; shift 2 ;;
    --no-sch) DO_SCH=0; shift ;;
    --no-pcb) DO_PCB=0; shift ;;
    *) DIR="$1"; shift ;;
  esac
done

eval "$(python3 "$TOOLS/hwproj.py" --shell ${DIR:+"$DIR"})" || exit 2
OUT="$REPO/build/render"
mkdir -p "$OUT"
LOG="$OUT/render.log"
: > "$LOG"
H=$(( W * 3 / 4 ))
created=()
rc=0

if [ "$DO_PCB" = 1 ] && [ -n "$PRJ_PCB" ]; then
  for side in top bottom; do
    f="$OUT/pcb-$side.png"
    rm -f "$f"
    if kicad-cli pcb render "$PRJ_PCB" --side "$side" --width "$W" --height "$H" \
         --quality basic --background opaque --floor -o "$f" >>"$LOG" 2>&1 && [ -s "$f" ]; then
      created+=("$f")
    else
      echo "ERRORE: render $side non riuscito (vedi $LOG)"; rc=1
    fi
  done
fi

if [ "$DO_SCH" = 1 ] && [ -n "$PRJ_SCH" ]; then
  pdf="$OUT/schema.pdf"
  rm -f "$pdf" "$OUT"/schema-*.png
  if kicad-cli sch export pdf "$PRJ_SCH" -o "$pdf" >>"$LOG" 2>&1 && [ -s "$pdf" ]; then
    created+=("$pdf")
    pdftoppm -r 70 -png "$pdf" "$OUT/schema" >>"$LOG" 2>&1 || { echo "ERRORE: pdftoppm"; rc=1; }
    for f in "$OUT"/schema-*.png; do [ -e "$f" ] && created+=("$f"); done
  else
    echo "ERRORE: esportazione PDF dello schema non riuscita (vedi $LOG)"; rc=1
  fi
fi

for f in "${created[@]}"; do realpath --relative-to="$REPO" "$f"; done
exit $rc
