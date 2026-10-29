#!/bin/bash
# Run the frozen analysis (commit 1b7f776 in the scratch checkout) with the clone's venv.
A=<frozen-checkout>
cd "$A" || exit 1
[ "$(git rev-parse --short HEAD)" = 1b7f776 ] && [ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "scratch checkout is not a clean 1b7f776" >&2; exit 1; }
export PYTHONPATH="$A/src"
exec "<review-clone>/.venv/bin/python" -m fplp.cli "$@"
