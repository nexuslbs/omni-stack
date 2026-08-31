#!/bin/sh
# Vector log-pipeline verification (omni-stack/services/vector).
#
# 1. Validates the real pipeline config (sources/transforms/sinks.toml).
# 2. Concatenates the REAL transforms.toml with the test fragment
#    (tests/level_token_test.toml) into one combined config and runs
#    `vector test` against it - so the suite exercises the shipped transform,
#    never a copy.
#
# Run inside a container with the services/vector dir mounted at /etc/vector-test
# (see tests/README.md for the exact docker invocation):
#   sh /etc/vector-test/tests/run_tests.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
VECTOR_BIN="${VECTOR_BIN:-/usr/bin/vector}"

echo "==> Validating pipeline config (sources/transforms/sinks.toml)"
"$VECTOR_BIN" validate --no-environment \
  "$DIR/../sources.toml" "$DIR/../transforms.toml" "$DIR/../sinks.toml"

COMBINED="$(mktemp /tmp/vector-level-test.XXXXXX.toml)"
trap 'rm -f "$COMBINED"' EXIT
cat "$DIR/../transforms.toml" "$DIR/level_token_test.toml" > "$COMBINED"

echo "==> Running vector tests (combined config: transforms.toml + tests/level_token_test.toml)"
"$VECTOR_BIN" test "$COMBINED"
echo "==> All vector tests passed"
