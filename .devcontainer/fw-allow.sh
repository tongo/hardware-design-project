#!/bin/bash
# Consente temporaneamente (fino al prossimo riavvio del container) uno o più domini.
# Uso, dal terminale:   sudo fw-allow <dominio> [altro-dominio ...]
# Per renderlo permanente: aggiungere il dominio a .devcontainer/allowed-domains.txt e fare "Rebuild Container".
set -euo pipefail
IPSET=allowed-domains

if [ "$#" -eq 0 ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Uso: sudo fw-allow <dominio> [altro-dominio ...]"
  echo "Consente il dominio fino al prossimo riavvio del container."
  echo "Per renderlo permanente: aggiungerlo a .devcontainer/allowed-domains.txt e fare Rebuild."
  exit 0
fi
[ "$(id -u)" -eq 0 ] || { echo "[fw-allow] va lanciato con sudo: sudo fw-allow $*" >&2; exit 1; }
ipset list -n 2>/dev/null | grep -qx "$IPSET" || { echo "[fw-allow] firewall non attivo (ipset $IPSET mancante)" >&2; exit 1; }

rc=0
for raw in "$@"; do
  # accetta anche un URL incollato: https://www.esempio.com/percorso -> www.esempio.com
  domain=$(echo "$raw" | sed -E 's#^[a-zA-Z]+://##; s#[/:?].*$##')
  if [[ ! "$domain" =~ ^[A-Za-z0-9.-]+$ ]] || [[ "$domain" != *.* ]]; then
    echo "[fw-allow] nome di dominio non valido: $raw" >&2; rc=1; continue
  fi
  ips=$(dig +short +time=3 +tries=2 A "$domain" | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' || true)
  if [ -z "$ips" ]; then
    echo "[fw-allow] non riesco a risolvere $domain" >&2; rc=1; continue
  fi
  while read -r ip; do ipset add "$IPSET" "$ip" -exist; done <<< "$ips"
  echo "[fw-allow] consentito $domain ($(echo "$ips" | tr '\n' ' ' | sed 's/ $//')) fino al prossimo riavvio"
done
exit $rc
