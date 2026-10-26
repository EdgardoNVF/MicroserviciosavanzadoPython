#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT"
mkdir -p evidence/lab09
BASE=${1:-python:3.12-slim-bookworm}
DEST=${2:-evidence/lab09/python-base.txt}
if [[ -s "$DEST" ]]; then
  PIN=$(cat "$DEST")
  if [[ ! "$PIN" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]]; then
    echo "ERROR: $DEST no contiene un digest valido; revisalo antes de continuar." >&2
    exit 1
  fi
  # Mantener la misma base al repetir, aunque la etiqueta remota haya cambiado.
  docker pull "$PIN" >&2
else
  docker pull "$BASE" >&2
  INSPECT=$(docker image inspect "$BASE")
  PIN=$(python3 -c 'import json,sys
items=json.load(sys.stdin)
refs=items[0].get("RepoDigests") or []
if not refs:
    raise SystemExit("ERROR: imagen sin RepoDigests; no se construira")
print(refs[0])' <<< "$INSPECT")
  if [[ ! "$PIN" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]]; then
    echo "ERROR: digest vacio o invalido para $BASE" >&2
    exit 1
  fi
  mkdir -p "$(dirname -- "$DEST")"
  printf '%s\n' "$PIN" > "$DEST"
fi
printf 'Base fijada: %s\n' "$PIN"
