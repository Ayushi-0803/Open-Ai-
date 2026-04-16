#!/usr/bin/env bash
set -euo pipefail

if [ -z "${TARGET_PATH:-}" ]; then
  echo "TARGET_PATH is not set"
  exit 1
fi

if [ ! -d "${TARGET_PATH}" ]; then
  echo "Target path does not exist: ${TARGET_PATH}"
  exit 1
fi

echo "api-contract: target path present"
