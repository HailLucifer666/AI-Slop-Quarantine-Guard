#!/usr/bin/env bash
# Prove the scanner's accuracy, and optionally scan a folder with it.
#
# Linux/macOS/CI counterpart of prove.ps1, so the pipeline runs the same gate a
# developer runs locally.
#
#   ./scripts/prove.sh                       # accuracy gate only
#   ./scripts/prove.sh /path/to/repo         # gate, then scan that folder
#   OFFLINE=1 FAIL_ON_CERTAIN=1 ./scripts/prove.sh /path/to/repo
#
# Exit: 0 clean · 1 findings · 2 bad usage · 3 CERTAIN findings · 4 accuracy gate failed
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
export PYTHONPATH="."
export PYTHONIOENCODING="utf-8"

TARGET="${1:-}"

if [ "${SKIP_ACCURACY:-0}" != "1" ]; then
  echo
  echo "=== Accuracy: measured against known answers ==="
  echo "Corpus: tests/fixtures/proof_corpus   Expectations: tests/proof_ground_truth.py"
  echo
  if ! python -m pytest tests/test_accuracy.py -v --no-header -p no:cacheprovider \
        -W "ignore::DeprecationWarning"; then
    echo
    echo "ACCURACY GATE FAILED - a rule has regressed. Do not trust scan output until this is green."
    exit 4
  fi
  echo
  echo "Accuracy gate passed: every asserted fact was detected, and no clean fixture produced a finding."
fi

if [ -n "$TARGET" ]; then
  if [ ! -d "$TARGET" ]; then
    echo "Not a directory: $TARGET"
    exit 2
  fi
  echo
  echo "=== Scanning: $TARGET ==="
  ARGS=("-m" "app.cli_scan" "$TARGET")
  [ "${OFFLINE:-0}" = "1" ] && ARGS+=("--offline")
  [ "${FAIL_ON_CERTAIN:-0}" = "1" ] && ARGS+=("--fail-on-certain")
  python "${ARGS[@]}"
  exit $?
fi
