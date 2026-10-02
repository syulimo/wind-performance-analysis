#!/usr/bin/env bash
# Downloads the ENGIE La Haute Borne open dataset as redistributed in NREL OpenOA (Licence Ouverte 2.0).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
curl -sL -o /tmp/lhb.zip https://raw.githubusercontent.com/NREL/OpenOA/main/examples/data/la_haute_borne.zip
unzip -oq /tmp/lhb.zip -d data -x "__MACOSX/*"
ls -lh data
