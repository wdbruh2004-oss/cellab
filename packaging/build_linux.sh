#!/usr/bin/env bash
# Build and verify the Linux one-folder bundle: build/CellLab-<version>-linux-x86_64.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
uv run python scripts/gen_notices.py
uv run pyinstaller packaging/cellab.spec --noconfirm --distpath build/dist --workpath build/work
cp THIRD_PARTY_NOTICES.md README.md docs/USER_MANUAL.md build/dist/CellLab/
RUN=(build/dist/CellLab/CellLab --self-test --report build/self_test.json)
if [ -z "${DISPLAY:-}" ]; then RUN=(xvfb-run -a -s "-screen 0 1600x1000x24" "${RUN[@]}"); fi
"${RUN[@]}" > /dev/null
version=$(uv run python -c "import cellab; print(cellab.__version__)")
tar -C build/dist -czf "build/CellLab-${version}-linux-x86_64.tar.gz" CellLab
echo "built build/CellLab-${version}-linux-x86_64.tar.gz"
