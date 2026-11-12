#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
make
echo "Build successful."
echo "Run two servers and one client as described in README.md."
