# Ambiente hardware: KiCad 10 (CLI + pcbnew Python), ngspice, Freerouting, kicad-happy, firewall in uscita.
#
# Perché non l'immagine kicad/kicad: su Docker Hub i tag 10.0.x sono pubblicati solo per amd64
# (su un Mac M1 girerebbero emulati e lenti). Il PPA ufficiale di KiCad ha invece build arm64 per Ubuntu 24.04.
ARG UBUNTU_IMAGE=ubuntu:24.04
FROM ${UBUNTU_IMAGE}

ARG KICAD_VERSION=10.0.8
ARG FREEROUTING_VERSION=2.5.0
ARG KICAD_HAPPY_REF=v3.0.2
ARG INSTALL_3D_MODELS=false

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Utente 'kicad' (uid 1000): l'immagine Ubuntu ha già 'ubuntu' con uid 1000, lo rinominiamo.
RUN usermod -l kicad -d /home/kicad -m ubuntu \
 && groupmod -n kicad ubuntu \
 && usermod -s /bin/bash kicad

# Pacchetti di base
# firewall: iptables ipset dnsutils aggregate iproute2 | datasheet: poppler-utils
# simulazione: ngspice | Freerouting 2.5: Java 25 (openjdk-25 è in noble-updates)
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates gnupg software-properties-common jq sudo less nano zip unzip sqlite3 ripgrep \
      poppler-utils ngspice openjdk-25-jre-headless python3 python3-venv python3-pip \
      iptables ipset dnsutils aggregate iproute2 procps shellcheck \
    && rm -rf /var/lib/apt/lists/*

# KiCad dal PPA ufficiale, versione esatta (deve coincidere con l'app sul Mac).
# Se il PPA non ha più quella versione, la build si ferma con un messaggio chiaro.
RUN add-apt-repository -y ppa:kicad/kicad-10.0-releases \
 && apt-get update \
 && KVER="$(apt-cache madison kicad | awk -v v="${KICAD_VERSION}" '$3 ~ "^"v"([~+-]|$)" {print $3; exit}')" \
 && if [ -z "$KVER" ]; then \
      echo "ERRORE: KiCad ${KICAD_VERSION} non è disponibile nel PPA. Versioni presenti:"; apt-cache madison kicad; \
      echo "Aggiorna l'app KiCad sul Mac e poi KICAD_VERSION in devcontainer.json."; exit 1; \
    fi \
 && echo "Installo kicad=${KVER}" \
 && apt-get install -y --no-install-recommends "kicad=${KVER}" kicad-symbols kicad-footprints kicad-templates \
 && if [ "${INSTALL_3D_MODELS}" = "true" ]; then apt-get install -y --no-install-recommends kicad-packages3d; fi \
 && apt-mark hold kicad \
 && rm -rf /var/lib/apt/lists/*

# Venv che vede anche il modulo di sistema 'pcbnew'
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir easyeda2kicad kicad-skip
ENV PATH=/opt/venv/bin:/workspace/tools:${PATH}

# Se pcbnew o kicad-cli mancano, o la versione non è quella attesa, la build fallisce subito
RUN python3 -c "import pcbnew; print('pcbnew', pcbnew.Version())" \
 && kicad-cli version \
 && kicad-cli version | grep -q "^${KICAD_VERSION}" \
 && java -version

RUN curl -fsSL -o /opt/freerouting.jar \
      "https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VERSION}/freerouting-${FREEROUTING_VERSION}.jar" \
 && chmod 644 /opt/freerouting.jar

RUN git clone https://github.com/aklofas/kicad-happy /opt/kicad-happy \
    && git -C /opt/kicad-happy -c advice.detachedHead=false checkout "${KICAD_HAPPY_REF}" \
    && git config --system --add safe.directory /opt/kicad-happy

# Firewall: file di root. L'utente kicad può solo eseguirli con sudo, non modificarli.
# Nome 'hw-init-firewall.sh': la feature claude-code installa DOPO il Dockerfile un suo /usr/local/bin/init-firewall.sh
# (che sovrascriverebbe il nostro); quello della feature resta inutilizzato e kicad non può lanciarlo con sudo.
COPY init-firewall.sh /usr/local/bin/hw-init-firewall.sh
COPY fw-allow.sh /usr/local/bin/fw-allow
COPY allowed-domains.txt /etc/hw-firewall/allowed-domains.txt
RUN chmod 755 /usr/local/bin/hw-init-firewall.sh /usr/local/bin/fw-allow \
 && chmod 644 /etc/hw-firewall/allowed-domains.txt \
 && echo "kicad ALL=(root) NOPASSWD: /usr/local/bin/hw-init-firewall.sh, /usr/local/bin/fw-allow" > /etc/sudoers.d/hw-firewall \
 && chmod 0440 /etc/sudoers.d/hw-firewall \
 && visudo -cf /etc/sudoers.d/hw-firewall

# Cartelle dei volumi con il proprietario giusto
RUN mkdir -p /home/kicad/.claude /data/jlcparts /commandhistory \
 && chown -R kicad:kicad /home/kicad /data/jlcparts /commandhistory

USER kicad
