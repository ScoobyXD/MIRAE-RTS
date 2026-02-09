#!/bin/bash
# cellular_connect.sh — Bring up SIM7600G-H cellular data via QMI (wwan0)
#
# This uses the QMI interface (/dev/cdc-wdm0) instead of PPP.
# The SIM7600's qmi_wwan kernel driver creates wwan0 automatically.
# We just need to configure raw-ip mode, start the network, and get an IP.
#
# Usage:
#   sudo bash cellular_connect.sh              # Default APN (super)
#   sudo bash cellular_connect.sh broadband    # Custom APN
#   sudo bash cellular_connect.sh stop         # Disconnect
#
# After running this, wwan0 will have an IP and internet.
# Then run: python3 live_gps.py
#
# Prerequisites:
#   sudo apt install libqmi-utils udhcpc

set -e

APN="${1:-super}"
QMI_DEV="/dev/cdc-wdm0"
IFACE="wwan0"

# ── Stop mode ──
if [ "$1" = "stop" ]; then
    echo "Stopping cellular..."
    sudo qmi-network "$QMI_DEV" stop 2>/dev/null || true
    sudo ip link set "$IFACE" down 2>/dev/null || true
    echo "Cellular stopped."
    exit 0
fi

echo "============================================================"
echo "  SIM7600G-H Cellular Data — QMI Mode"
echo "  APN: $APN"
echo "  QMI: $QMI_DEV"
echo "  Interface: $IFACE"
echo "============================================================"

# ── Step 0: Check prerequisites ──
echo ""
echo "[0/7] Checking prerequisites..."

if [ ! -c "$QMI_DEV" ]; then
    echo "ERROR: $QMI_DEV not found."
    echo ""
    echo "This means the qmi_wwan driver is not loaded or the SIM7600"
    echo "is not detected. Check:"
    echo "  1. Is the SIM7600G-H HAT powered on?"
    echo "  2. Is the USB cable connected?"
    echo "  3. Run: lsusb | grep -i qualcomm"
    echo "  4. Run: ls /dev/cdc-wdm*"
    echo "  5. Try: sudo modprobe qmi_wwan"
    exit 1
fi

if ! command -v qmicli &>/dev/null; then
    echo "ERROR: qmicli not found. Install with:"
    echo "  sudo apt install libqmi-utils"
    exit 1
fi

if ! command -v udhcpc &>/dev/null; then
    echo "ERROR: udhcpc not found. Install with:"
    echo "  sudo apt install udhcpc"
    exit 1
fi

echo "  Prerequisites OK"

# ── Step 1: Set modem online ──
echo ""
echo "[1/7] Setting modem to online mode..."
sudo qmicli -d "$QMI_DEV" --dms-set-operating-mode='online' 2>/dev/null || true
sleep 1

MODE=$(sudo qmicli -d "$QMI_DEV" --dms-get-operating-mode 2>/dev/null || echo "unknown")
echo "  Mode: $MODE"

# ── Step 2: Check signal and network ──
echo ""
echo "[2/7] Checking signal and network..."
SIGNAL=$(sudo qmicli -d "$QMI_DEV" --nas-get-signal-strength 2>/dev/null | head -5 || echo "  (could not read signal)")
echo "$SIGNAL"

HOME_NET=$(sudo qmicli -d "$QMI_DEV" --nas-get-home-network 2>/dev/null || echo "  (could not read network)")
echo "  Network: $HOME_NET"

# ── Step 3: Confirm wwan0 interface name ──
echo ""
echo "[3/7] Checking wwan interface..."
WWAN=$(sudo qmicli -d "$QMI_DEV" -w 2>/dev/null | grep -oP 'wwan\d+' || echo "")
if [ -z "$WWAN" ]; then
    echo "  WARNING: Could not determine interface name, assuming wwan0"
    WWAN="wwan0"
else
    echo "  Interface: $WWAN"
    IFACE="$WWAN"
fi

# ── Step 4: Configure raw-ip mode ──
echo ""
echo "[4/7] Configuring raw-ip mode on $IFACE..."
sudo ip link set "$IFACE" down 2>/dev/null || true
echo 'Y' | sudo tee "/sys/class/net/$IFACE/qmi/raw_ip" > /dev/null 2>&1 || {
    echo "  WARNING: Could not set raw_ip (file may not exist)"
    echo "  This might still work without it"
}
sudo ip link set "$IFACE" up

echo "  $IFACE configured"

# ── Step 5: Start QMI network connection ──
echo ""
echo "[5/7] Starting QMI network (APN: $APN)..."
sudo qmicli -p -d "$QMI_DEV" \
    --device-open-net='net-raw-ip|net-no-qos-header' \
    --wds-start-network="apn='$APN',ip-type=4" \
    --client-no-release-cid

echo "  Network started"

# ── Step 6: Get IP via DHCP ──
echo ""
echo "[6/7] Getting IP address via DHCP..."
sudo udhcpc -i "$IFACE" -q -f -n 2>&1 || {
    echo "  udhcpc failed, trying dhclient..."
    sudo dhclient "$IFACE" -timeout 10 2>&1 || {
        echo "  WARNING: DHCP failed. You may need to configure IP manually."
    }
}

# Show result
IP=$(ip -4 addr show "$IFACE" 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "none")
echo "  IP: $IP"

# ── Step 7: Verify connectivity ──
echo ""
echo "[7/7] Testing connectivity..."

# Ping through wwan0 specifically
if ping -c 2 -W 5 -I "$IFACE" 8.8.8.8 &>/dev/null; then
    echo "  Ping 8.8.8.8 via $IFACE: OK"
else
    echo "  Ping 8.8.8.8 via $IFACE: FAILED"
    echo "  (Routing might need adjustment, but interface is up)"
fi

# Show routing
echo ""
echo "  Routes:"
ip route show | grep "$IFACE" | head -3
echo ""

echo "============================================================"
echo "  Cellular data is UP!"
echo "  Interface: $IFACE"
echo "  IP: $IP"
echo ""
echo "  To route ALL traffic through cellular (disable WiFi):"
echo "    sudo ip link set wlan0 down"
echo ""
echo "  To route ONLY rover traffic through cellular:"
echo "    sudo ip route add \$(dig +short miraeopus.com | head -1)/32 dev $IFACE"
echo ""
echo "  To stop cellular:"
echo "    sudo bash cellular_connect.sh stop"
echo ""
echo "  Now run your rover:"
echo "    python3 live_gps.py"
echo "============================================================"
