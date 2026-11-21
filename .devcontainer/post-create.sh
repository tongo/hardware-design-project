#!/bin/bash
# Eseguito una volta dopo la creazione del container (postCreateCommand).
set -uo pipefail
cd /workspace || exit 1

git config --global --add safe.directory /workspace

chmod +x tools/*.sh tools/*.py 2>/dev/null || true
mkdir -p build docs/datasheets docs/components docs/reports hardware sim production

# Tabelle globali delle librerie KiCad (simboli e footprint di sistema), come al primo avvio dell'app
KCFG="$HOME/.config/kicad/$(kicad-cli version 2>/dev/null | cut -d. -f1,2)"
mkdir -p "$KCFG"
for t in sym-lib-table fp-lib-table; do
  [ -f "$KCFG/$t" ] || cp /usr/share/kicad/template/$t "$KCFG/$t"
done

echo "=== Versioni ==="
echo "kicad-cli : $(kicad-cli version 2>/dev/null || echo 'NON TROVATO')"
echo "pcbnew    : $(python3 -c 'import pcbnew; print(pcbnew.Version())' 2>/dev/null || echo 'NON TROVATO')"
echo "ngspice   : $(ngspice --version 2>/dev/null | grep -m1 -o 'ngspice-[0-9.]*' || echo 'NON TROVATO')"
echo "java      : $(java -version 2>&1 | head -1)"
echo "freerouting: $(basename "$(readlink -f "${FREEROUTING_JAR:-/opt/freerouting.jar}")") $( [ -f "${FREEROUTING_JAR:-/opt/freerouting.jar}" ] && echo OK || echo MANCANTE)"
echo "kicad-happy: $(git -C "${KICAD_HAPPY_DIR:-/opt/kicad-happy}" describe --tags --always 2>/dev/null || echo 'NON TROVATO')"
echo "claude    : $(claude --version 2>/dev/null || echo 'NON TROVATO')"

case "$(kicad-cli version 2>/dev/null)" in
  10.0.*) ;;
  *) echo "ATTENZIONE: kicad-cli non è 10.0.x: i file potrebbero non aprirsi con l'app sul Mac." ;;
esac

echo
DB="${JLC_DB_DIR:-/data/jlcparts}/jlcpcb-components.sqlite3"
if [ -s "$DB" ]; then
  echo "Database JLC presente: $DB ($(du -h "$DB" | cut -f1))"
else
  echo "Database JLC non ancora scaricato (circa 500 MB, condiviso tra tutti i progetti)."
  echo "Per scaricarlo: tools/jlc_parts.py update"
fi
