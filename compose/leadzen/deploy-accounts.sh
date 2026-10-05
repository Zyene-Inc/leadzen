#!/usr/bin/env bash
# Validate the controlled candidate before an explicitly authorized release.
# The historical in-place installer overwrote source/environment before it could
# establish complete recovery and worker-drain proof. It is no longer safe for
# the expanded multi-employee application.
set -euo pipefail
umask 077
if [[ $# != 2 ]]; then
  echo 'Release blocked: provide CANDIDATE_DIRECTORY CHECKS_JSON. Follow docs/production-release.md for the authorized deployment and rollback procedure.' >&2
  exit 2
fi
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
repository=$(cd -- "$script_dir/../.." && pwd)
python="${LEADZEN_RELEASE_PYTHON:-$repository/.venv/bin/python}"
"$python" -m leadzen.operations.release gate "$1" --checks "$2"
echo 'Candidate checks passed. Execute the reviewed controlled-release runbook only with fresh deployment authorization; no live service or data was changed.'
