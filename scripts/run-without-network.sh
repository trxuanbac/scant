#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: run-without-network.sh <command> [args...]" >&2
  exit 2
fi

if [ "$(uname -s)" != "Linux" ]; then
  if [ "${SCANT_REQUIRE_NETWORK_NAMESPACE:-0}" = "1" ]; then
    echo "strict network isolation requires Linux" >&2
    exit 1
  fi
  exec "$@"
fi

if [ "${SCANT_INSIDE_NETWORK_NAMESPACE:-0}" = "1" ]; then
  ip link set lo up
  exec "$@"
fi

exec sudo --preserve-env=PATH unshare --net env \
  SCANT_INSIDE_NETWORK_NAMESPACE=1 "$0" "$@"
