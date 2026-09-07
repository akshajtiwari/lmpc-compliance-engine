#!/usr/bin/env bash
# Fetch a SECOND rule family — Legal Metrology (General) Rules and Government Approved
# Test Centre Rules. Used to prove the compiler is not overfit to Packaged Commodities,
# and to exercise the G.S.R. number collision that only appears across a longer span.
set -euo pipefail
DIR="${1:-corpus_general}"; mkdir -p "$DIR"; B=https://consumeraffairs.gov.in/public/upload/files
while read -r name path; do
  [ -f "$DIR/$name" ] || curl -sk -m 90 -o "$DIR/$name" "$B/$path"
done <<'LIST'
gen-2012.pdf 6(ii)_0_1732709637.pdf
gen-2016.pdf 6(iii)_1732709674.pdf
gen-2021.pdf LM_General_Amendment_Rules2021_1732709906.pdf
gen-2022.pdf 239353_1732709948.pdf
gen-2025-radar.pdf Radar%20Equipment%20Gen%20Rules%20Amendment%20(1)_1746001628.pdf
gen-2025-gas.pdf 2025.4.21%20Gas%20Meter%20General%20Rules_1746001659.pdf
gen-2025-sphyg.pdf Sphygmomanomneters%20General%20Rules_1754973919.pdf
gen-2025-moisture.pdf Gen%20Rule-%20Moisture%20Meters_1755669735.pdf
gen-2025-thermo.pdf Gen%20Rules%205th%20Amendment%20Thermometers_1756975842.pdf
gen-2025-breath.pdf Gen%20Rules%206th%20Amendment%20Breath%20Analyser_1764862018.pdf
gen-2025-7th.pdf 2025.12.18%20Gen%20Rules%207th%20Amendment%202%20yr%20verification%20period_1766504014.pdf
gen-2026-1st.pdf LM_General_Rule_Amendment_2026_1768192719.pdf
gen-2026-2nd.pdf Continuous_Electrical_Thermometer_1771307283.pdf
gen-2026-3rd.pdf GSR%20175(E)_1777015860.pdf
gatc-2021.pdf 2021%20GATC%20amendment_1732710258.pdf
gatc-2025.pdf 267111_1761404639.pdf
gatc-2026a.pdf GATC_Amendment_Rules_2026_1778476324.pdf
gatc-2026b.pdf GATC_2nd_Amendment_1782108671.pdf
LIST
echo "$DIR: $(ls "$DIR"/*.pdf 2>/dev/null | wc -l) instruments"
