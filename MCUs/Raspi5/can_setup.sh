#!/bin/bash
# can_setup.sh -- Bring up MCP2515 CAN bus interface on Raspberry Pi 5
#
# One-time kernel config (add to /boot/firmware/config.txt then reboot):
#   dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
#   dtoverlay=spi0-0cs
#
# After reboot, run this script to activate the CAN interface:
#   sudo bash can_setup.sh
#
# Or just run the command directly:
#   sudo ip link set can0 up type can bitrate 500000

set -euo pipefail

IFACE="can0"
BITRATE=500000

echo "[CAN] Setting up $IFACE at ${BITRATE}bps"

# Check if can0 interface exists
if ! ip link show "$IFACE" &>/dev/null; then
    echo "[CAN] ERROR: $IFACE not found."
    echo ""
    echo "  Make sure /boot/firmware/config.txt has these lines:"
    echo "    dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25"
    echo "    dtoverlay=spi0-0cs"
    echo ""
    echo "  Then reboot: sudo reboot"
    echo ""
    echo "  After reboot, check: dmesg | grep -i mcp"
    echo "  You should see: mcp251x spi0.0 can0: MCP2515 successfully initialized."
    exit 1
fi

# Bring down first (in case it's already up with wrong settings)
sudo ip link set "$IFACE" down 2>/dev/null || true

# Set bitrate and bring up
sudo ip link set "$IFACE" up type can bitrate "$BITRATE"

echo "[CAN] $IFACE is UP at ${BITRATE}bps"

# Show interface status
ip -details link show "$IFACE"

echo ""
echo "[CAN] Ready. You can now run:"
echo "  python3 can_bridge.py             # standalone test"
echo "  sudo python3 live_gps.py --cellular --can  # with GPS + cellular"
echo ""
echo "To monitor CAN traffic:"
echo "  candump can0"
echo "  cansend can0 2FF#01              # send ping to STM32"
