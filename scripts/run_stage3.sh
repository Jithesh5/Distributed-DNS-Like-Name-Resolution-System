#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$HOME/Downloads/distributed_dns_sdn_stage2"
RESULT_DIR="$PROJECT_DIR/results"

cd "$PROJECT_DIR"
mkdir -p "$RESULT_DIR"

echo "======================================"
echo " Project 22 - Stage 3 SDN Test Launcher"
echo "======================================"

if [[ ! -x ./dns_client || ! -x ./dns_server ]]; then
    echo "Building DNS client and server..."
    make
fi

echo
echo "Make sure the OS-Ken controller is running in a separate terminal."
read -r -p "When the controller is ready, press Enter to continue..."

echo
echo "Cleaning up old Mininet state..."
sudo mn -c

echo
echo "Starting Mininet topology..."
echo "At the Mininet prompt, enter: pingall"
echo "To exit Mininet, enter: exit"

sudo mn \
    --custom topology/dns_topology.py \
    --topo dns \
    --controller=remote,ip=127.0.0.1,port=6653 \
    --switch ovsk,protocols=OpenFlow13
