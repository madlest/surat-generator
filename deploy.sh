#!/usr/bin/env bash
#
# Deploy di VM produksi. Dipanggil lewat alias `gitsync`:
#
#     alias gitsync='~/surat-generator/deploy.sh'
#
# Aman dijalankan berulang. Berhenti di langkah pertama yang gagal (set -e),
# jadi tidak akan me-restart service dengan skema DB yang belum dimigrasi.

set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

SERVICE="${SURAT_SERVICE:-surat-generator.service}"

echo "==> git pull --ff-only origin main"
git pull --ff-only origin main

echo "==> uv sync"
uv sync

echo "==> alembic upgrade head"
# No-op kalau DB sudah di head. WAJIB dijalankan tiap deploy — inilah langkah
# yang dulu terlewat waktu Stage A/B ternyata tidak ikut termigrasi.
uv run alembic upgrade head

echo "==> restart ${SERVICE}"
sudo systemctl restart "${SERVICE}"

sleep 1
echo "==> hasil"
systemctl is-active "${SERVICE}"
uv run alembic current
echo "OK — deploy selesai."
