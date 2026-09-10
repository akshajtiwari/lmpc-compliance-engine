#!/usr/bin/env bash
# Fetch the live PCR corpus. Compilation is a separate step: python -m lmpc.lawc.build
# (it calls this script itself when corpus/ is empty). Requires curl only.
set -euo pipefail
DIR="${1:-corpus}"; mkdir -p "$DIR"; B=https://consumeraffairs.gov.in/public/upload/files
# NOTE: the site's TLS certificate is expired -> -k. Links on the page say http://
# but port 80 does not answer -> always rewrite to https://.
while read -r name path; do
  [ -f "$DIR/$name" ] || curl -sk -m 90 -o "$DIR/$name" "$B/$path"
done <<'LIST'
2016-a1.pdf 8(xi)_0_1732871315.pdf
2017-8xii.pdf 8(xii)_0_1732871346.pdf
2021-a1.pdf 230946_1732871433.pdf
2022-gsr226.pdf GSR226_1732871458.pdf
2022-qr.pdf Notification%20-%20%20Legal%20Metrology%20(QR%20Code)_1732871487.pdf
2022-garments.pdf 2022%203rd%20amendment%20in%20PCR%20Garments_1733228786.pdf
2022-aa.pdf PCR_1732871549.pdf
2022-nov30.pdf eGazette_30_nov_22_1732871630_1746006280.pdf
2023-jan27.pdf 2023.01.27%20amendment%20in%20amendment%20of%202023%20PCR_1732871665.pdf
2023-mar24.pdf PCR_Amendment_24March2023_1732871698.pdf
2023-jun05.pdf 2023.06.5%20amendment%20in%20amendment%20of%20PCR%20ext%20till%2030.6.2023_1732871791.pdf
2023-jun23.pdf 2023.6.23%20QR%20Code%20PCR%20amendment_1732871827.pdf
2023-jun28.pdf 2023.6.28%20amendment%20in%20amendment%20of%20PCR%20ext%20till%2031.8.2023_1733228263.pdf
2023-aug30.pdf 248432_1732871904.pdf
2023-sep30.pdf Amendment%20of%20PCR%20ext%20till%2031.12.2023%20(1)_1732871950.pdf
2023-oct06.pdf 2023.10.6%20amendment%20in%20PCR_1732871982.pdf
2025-oct24.pdf 267107_1761404707.pdf
2025-panmasala.pdf 2nd%20PCR%20Pan%20Masala_1764736734.pdf
2026-coo1.pdf 2026.02.13%20PCR%201st%20COO%20Filter%20on%20e-commerce%20websites_1771231030.pdf
2026-coo2.pdf 2026.4.27%20PCR%202nd%20COO%20from%201.7.2027_1777348487.pdf
2026-3rd.pdf PCR_3rd_29May2026_1780376045.pdf
LIST
echo "corpus in $DIR — now compile it: python -m lmpc.lawc.build"
