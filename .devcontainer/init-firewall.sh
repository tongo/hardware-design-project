#!/bin/bash
# Firewall in uscita del container (eseguito come root a ogni avvio, da postStartCommand).
# Consente solo: DNS, loopback, rete dell'host, intervalli IP di GitHub e i domini di
# /etc/hw-firewall/allowed-domains.txt. Tutto il resto viene rifiutato.
# Basato sul devcontainer di riferimento di Claude Code.
set -euo pipefail
IFS=$'\n\t'

DOMAINS_FILE=/etc/hw-firewall/allowed-domains.txt
IPSET=allowed-domains

log()  { echo "[firewall] $*"; }
warn() { echo "[firewall] ATTENZIONE: $*" >&2; }
die()  { echo "[firewall] ERRORE: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "va eseguito come root (sudo)."
[ -r "$DOMAINS_FILE" ] || die "file dei domini mancante: $DOMAINS_FILE"

# 1. Salva le regole NAT del DNS interno di Docker (127.0.0.11, solo sulle reti definite dall'utente)
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

iptables -P INPUT ACCEPT
iptables -P OUTPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy "$IPSET" 2>/dev/null || true

if [ -n "$DOCKER_DNS_RULES" ]; then
  log "ripristino le regole del DNS interno di Docker"
  iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
  iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
  echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
fi

# 2. DNS e loopback
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A INPUT  -p udp --sport 53 -j ACCEPT
iptables -A INPUT  -p tcp --sport 53 -j ACCEPT
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# 3. ipset + intervalli di GitHub
ipset create "$IPSET" hash:net

log "scarico gli intervalli IP di GitHub"
gh_ranges=$(curl -fsS --connect-timeout 10 https://api.github.com/meta || true)
if [ -z "$gh_ranges" ] || ! echo "$gh_ranges" | jq -e '.web and .api and .git' >/dev/null 2>&1; then
  warn "impossibile leggere https://api.github.com/meta: proseguo risolvendo solo i domini GitHub dell'elenco"
else
  n=0
  while read -r cidr; do
    [[ "$cidr" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ ]] || die "intervallo non valido da GitHub: $cidr"
    ipset add "$IPSET" "$cidr" -exist
    n=$((n + 1))
  done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | grep -v ':' | aggregate -q)
  log "aggiunti $n intervalli di GitHub"
fi

# 4. Domini consentiti
ok=0; ko=0
while read -r domain; do
  ips=$(dig +short +time=3 +tries=2 A "$domain" | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' || true)
  if [ -z "$ips" ]; then
    warn "non riesco a risolvere $domain: lo salto"
    ko=$((ko + 1))
    continue
  fi
  while read -r ip; do
    ipset add "$IPSET" "$ip" -exist
  done <<< "$ips"
  ok=$((ok + 1))
done < <(sed -e 's/#.*//' -e 's/[[:space:]]//g' "$DOMAINS_FILE" | grep -v '^$')
log "domini risolti: $ok, non risolti: $ko"

# 5. Rete dell'host (gateway di default /24), necessaria a VS Code
HOST_IP=$(ip route | awk '/^default/ {print $3; exit}')
[ -n "$HOST_IP" ] || die "gateway di default non trovato"
HOST_NETWORK=$(echo "$HOST_IP" | sed 's/\.[0-9]*$/.0\/24/')
log "rete dell'host: $HOST_NETWORK"
iptables -A INPUT  -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# 6. Politiche di default
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
iptables -A INPUT  -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set "$IPSET" dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# IPv6: l'ipset è solo IPv4, quindi in IPv6 si blocca tutto tranne il loopback
# (altrimenti un host raggiungibile in IPv6 aggirerebbe il firewall).
if command -v ip6tables >/dev/null 2>&1 && ip6tables -L >/dev/null 2>&1; then
  ip6tables -F || true
  ip6tables -A INPUT  -i lo -j ACCEPT
  ip6tables -A OUTPUT -o lo -j ACCEPT
  ip6tables -A INPUT  -m state --state ESTABLISHED,RELATED -j ACCEPT
  ip6tables -A OUTPUT -j REJECT 2>/dev/null || true
  ip6tables -P INPUT DROP
  ip6tables -P FORWARD DROP
  ip6tables -P OUTPUT DROP
  log "IPv6 bloccato"
else
  warn "ip6tables non disponibile: IPv6 non filtrato (di solito il container non ha IPv6)"
fi

# 7. Verifica
if curl -s --connect-timeout 5 https://example.com >/dev/null 2>&1; then
  die "verifica fallita: https://example.com è raggiungibile, il firewall non funziona"
fi
log "verifica: example.com bloccato (corretto)"
if curl -s --connect-timeout 5 https://api.github.com/zen >/dev/null 2>&1; then
  log "verifica: api.github.com raggiungibile (corretto)"
else
  warn "api.github.com non raggiungibile: controlla la rete"
fi
log "firewall attivo"
