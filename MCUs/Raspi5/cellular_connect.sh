#!/bin/bash
# cellular_connect.sh -- Bring up and KEEP UP SIM7600G-H cellular via QMI
#
# This script:
#   1. Establishes the initial QMI data session on wwan0
#   2. Runs a watchdog loop that checks connectivity every 15 seconds
#   3. If wwan0 loses its connection (cell tower handover, signal drop),
#      it automatically re-establishes the data session
#
# Usage:
#   sudo bash cellular_connect.sh              # Default APN (super)
#   sudo bash cellular_connect.sh fast.t-mobile.com  # Custom APN
#   sudo bash cellular_connect.sh stop         # Disconnect
#
# After this is running in one terminal, open another and run:
#   python3 live_gps.py --cellular
#
# Prerequisites:
#   sudo apt install libqmi-utils udhcpc

set -euo pipefail

APN="${1:-super}"
QMI_DEV="/dev/cdc-wdm0"
IFACE="wwan0"
CHECK_INTERVAL=15   # seconds between connectivity checks
MAX_RETRIES=5       # max consecutive reconnect attempts before waiting longer
PING_TARGET="8.8.8.8"

# -- Stop mode ----------------------------------------------------------------
if [ "${1:-}" = "stop" ]; then
    echo "[cellular] Stopping..."
    sudo qmi-network "$QMI_DEV" stop 2>/dev/null || true
    sudo ip link set "$IFACE" down 2>/dev/null || true
    echo "[cellular] Stopped."
    exit 0
fi

# -- Prerequisite checks ------------------------------------------------------
echo "============================================================"
echo "  SIM7600G-H Cellular -- QMI with Auto-Reconnect"
echo "  APN: $APN"
echo "  QMI: $QMI_DEV"
echo "  Interface: $IFACE"
echo "  Check interval: ${CHECK_INTERVAL}s"
echo "============================================================"
echo ""

if [ ! -c "$QMI_DEV" ]; then
    echo "[ERROR] $QMI_DEV not found."
    echo "  Is the SIM7600G-H HAT powered on and USB connected?"
    echo "  Check: lsusb | grep -i qualcomm"
    echo "  Try:   sudo modprobe qmi_wwan"
    exit 1
fi

if ! command -v qmicli &>/dev/null; then
    echo "[ERROR] qmicli not found. Run: sudo apt install libqmi-utils"
    exit 1
fi

if ! command -v udhcpc &>/dev/null; then
    echo "[ERROR] udhcpc not found. Run: sudo apt install udhcpc"
    exit 1
fi

# -- Functions -----------------------------------------------------------------

check_signal() {
    # Print signal info (non-fatal if it fails)
    echo "[cellular] Checking signal..."
    local sig
    sig=$(sudo qmicli -d "$QMI_DEV" --nas-get-signal-strength 2>/dev/null || echo "(no signal info)")
    # Extract just the dBm line
    local dbm
    dbm=$(echo "$sig" | grep "Network 'lte'" | head -1 | awk '{print $3, $4}' || echo "unknown")
    echo "[cellular]   Signal: $dbm"

    local net
    net=$(sudo qmicli -d "$QMI_DEV" --nas-get-home-network 2>/dev/null | grep "Description" | awk -F"'" '{print $2}' || echo "unknown")
    echo "[cellular]   Network: $net"
}

start_data_session() {
    # Full sequence to bring up cellular data on wwan0
    echo "[cellular] Starting data session..."

    # Step 1: Ensure modem is online
    sudo qmicli -d "$QMI_DEV" --dms-set-operating-mode='online' 2>/dev/null || true
    sleep 1

    # Step 2: Bring down wwan0, set raw-ip, bring up
    #   raw-ip mode is required because cellular sends raw IP packets,
    #   not ethernet frames. Can only be set while interface is down.
    sudo ip link set "$IFACE" down 2>/dev/null || true
    echo 'Y' | sudo tee "/sys/class/net/$IFACE/qmi/raw_ip" > /dev/null 2>&1 || {
        echo "[cellular]   WARNING: Could not set raw_ip"
    }
    sudo ip link set "$IFACE" up

    # Step 3: Start QMI network data session
    #   This tells the modem: "connect to the cellular network using this APN"
    #   The modem authenticates with the tower, establishes a PDP context,
    #   and starts routing data packets through wwan0.
    #   --client-no-release-cid keeps the session alive after qmicli exits.
    local result
    result=$(sudo qmicli -p -d "$QMI_DEV" \
        --device-open-net='net-raw-ip|net-no-qos-header' \
        --wds-start-network="apn='$APN',ip-type=4" \
        --client-no-release-cid 2>&1) || true

    if echo "$result" | grep -q "Network started"; then
        echo "[cellular]   QMI network started"
    else
        echo "[cellular]   QMI start result: $result"
        # Try stopping any stale session and retry
        echo "[cellular]   Retrying after stop..."
        sudo qmi-network "$QMI_DEV" stop 2>/dev/null || true
        sleep 2
        sudo ip link set "$IFACE" down 2>/dev/null || true
        echo 'Y' | sudo tee "/sys/class/net/$IFACE/qmi/raw_ip" > /dev/null 2>&1 || true
        sudo ip link set "$IFACE" up
        result=$(sudo qmicli -p -d "$QMI_DEV" \
            --device-open-net='net-raw-ip|net-no-qos-header' \
            --wds-start-network="apn='$APN',ip-type=4" \
            --client-no-release-cid 2>&1) || true
        echo "[cellular]   Retry result: $result"
    fi

    # Step 4: Get IP via DHCP
    #   The modem has a data session but wwan0 has no IP yet.
    #   udhcpc asks the cellular network for an IP address.
    echo "[cellular]   Requesting IP via DHCP..."
    sudo udhcpc -i "$IFACE" -q -f -n 2>&1 || {
        echo "[cellular]   udhcpc failed, trying dhclient..."
        sudo dhclient "$IFACE" -timeout 10 2>&1 || {
            echo "[cellular]   WARNING: DHCP failed"
            return 1
        }
    }

    # Check result
    local ip
    ip=$(ip -4 addr show "$IFACE" 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "")
    if [ -z "$ip" ]; then
        echo "[cellular]   ERROR: No IP on $IFACE"
        return 1
    fi

    echo "[cellular]   IP: $ip"
    return 0
}

check_connectivity() {
    # Returns 0 if wwan0 can reach the internet, 1 if not
    local ip
    ip=$(ip -4 addr show "$IFACE" 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "")

    if [ -z "$ip" ]; then
        return 1
    fi

    # Ping through wwan0 specifically (2 pings, 3s timeout each)
    if ping -c 2 -W 3 -I "$IFACE" "$PING_TARGET" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# -- Initial connection --------------------------------------------------------

check_signal

if ! start_data_session; then
    echo "[cellular] Initial connection failed. Will keep retrying..."
fi

# Verify
if check_connectivity; then
    local_ip=$(ip -4 addr show "$IFACE" 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "none")
    echo ""
    echo "============================================================"
    echo "  Cellular is UP!"
    echo "  Interface: $IFACE"
    echo "  IP: $local_ip"
    echo ""
    echo "  Now open another terminal and run:"
    echo "    python3 live_gps.py --cellular"
    echo ""
    echo "  This terminal will monitor the connection."
    echo "  Press Ctrl+C to stop."
    echo "============================================================"
    echo ""
else
    echo ""
    echo "[cellular] WARNING: Initial ping failed. Will keep retrying..."
    echo ""
fi

# -- Watchdog loop -------------------------------------------------------------
# Checks connectivity every CHECK_INTERVAL seconds.
# If wwan0 loses connection (cell tower handover, signal drop, etc.),
# it re-runs the full QMI data session setup.

echo "[cellular] Watchdog started (checking every ${CHECK_INTERVAL}s)..."

consecutive_failures=0

cleanup() {
    echo ""
    echo "[cellular] Stopping watchdog..."
    sudo qmi-network "$QMI_DEV" stop 2>/dev/null || true
    sudo ip link set "$IFACE" down 2>/dev/null || true
    echo "[cellular] Cleaned up."
    exit 0
}
trap cleanup SIGINT SIGTERM

while true; do
    sleep "$CHECK_INTERVAL"

    if check_connectivity; then
        if [ "$consecutive_failures" -gt 0 ]; then
            echo "[cellular] Connection restored after $consecutive_failures failures"
        fi
        consecutive_failures=0
        # Print a dot every check so you know it's alive
        local_ip=$(ip -4 addr show "$IFACE" 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "?")
        echo -n "."
    else
        consecutive_failures=$((consecutive_failures + 1))
        echo ""
        echo "[cellular] Connection lost! (failure #$consecutive_failures)"

        if [ "$consecutive_failures" -ge "$MAX_RETRIES" ]; then
            echo "[cellular] $MAX_RETRIES consecutive failures. Waiting 60s before next attempt..."
            sleep 60
            consecutive_failures=0
        fi

        echo "[cellular] Reconnecting..."
        check_signal

        if start_data_session; then
            if check_connectivity; then
                echo "[cellular] Reconnected successfully!"
            else
                echo "[cellular] Session started but ping failed. Will retry..."
            fi
        else
            echo "[cellular] Reconnect failed. Will retry in ${CHECK_INTERVAL}s..."
        fi
    fi
done
