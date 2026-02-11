#!/usr/bin/env python3
"""
can_bridge.py -- CAN bus bridge between Raspberry Pi and STM32.

Reads telemetry from STM32 (heartbeat, IMU, encoders) over CAN bus via MCP2515.
Sends navigation commands to STM32 over CAN bus.

The MCP2515 module connects to the Pi via SPI0 and appears as a SocketCAN
interface (can0) after kernel driver setup.

Setup (one-time, add to /boot/firmware/config.txt):
    dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
    dtoverlay=spi0-0cs

Then after reboot (or in can_setup.sh):
    sudo ip link set can0 up type can bitrate 500000

Usage:
    This module is imported by live_gps.py. It can also run standalone for testing:
    python3 can_bridge.py              # Print received CAN data
    python3 can_bridge.py --send-ping  # Send a ping and wait for heartbeat

Prerequisites:
    pip3 install python-can
"""

import struct
import threading
import time
import logging
import logging.handlers
import os

try:
    import can
except ImportError:
    can = None

# -- CAN Message IDs (must match STM32 MCP2515.h) ----------------------------
CAN_ID_HEARTBEAT = 0x100
CAN_ID_IMU_AG    = 0x101
CAN_ID_IMU_AG2   = 0x102
CAN_ID_ENCODER   = 0x103
CAN_ID_STATUS    = 0x104

CAN_ID_NAV_CMD   = 0x200
CAN_ID_STOP_CMD  = 0x201
CAN_ID_SPEED_CMD = 0x202
CAN_ID_PING      = 0x2FF

# -- Logger -------------------------------------------------------------------
log = logging.getLogger('can_bridge')

def setup_can_logging(log_dir):
    """Set up rotating file log for CAN bridge."""
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'can_bridge.log'),
        maxBytes=5*1024*1024,
        backupCount=5,
    )
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    ))
    log.addHandler(fh)


class CANBridge:
    """
    Bridges CAN bus (MCP2515 via SocketCAN can0) and live_gps.py.

    Background thread continuously reads CAN frames from STM32.
    Exposes latest IMU, encoder, and heartbeat data for telemetry.
    Provides methods to send commands to STM32.
    """

    def __init__(self, interface='can0', bitrate=500000):
        self.interface = interface
        self.bitrate = bitrate
        self.bus = None
        self._running = False
        self._thread = None

        # Latest data from STM32 (updated by background thread)
        self.stm32_uptime_ms = 0
        self.stm32_hb_seq = 0
        self.stm32_can_ok = False
        self.stm32_eflg = 0
        self.last_heartbeat_time = 0

        # IMU data (from CAN frames, int16 * 1000 -> float)
        self.ax = 0.0
        self.ay = 0.0
        self.az = 0.0
        self.gx = 0.0
        self.gy = 0.0
        self.gz = 0.0
        self.imu_updated = 0  # timestamp of last IMU update

        # Encoder data (future)
        self.enc_left = 0
        self.enc_right = 0
        self.enc_left_vel = 0
        self.enc_right_vel = 0

        # Stats
        self.rx_count = 0
        self.tx_count = 0
        self.rx_errors = 0
        self.hb_missed = 0

    def open(self):
        """Open CAN bus interface. Returns True on success."""
        if can is None:
            log.error("python-can not installed. Run: pip3 install python-can")
            return False

        try:
            self.bus = can.interface.Bus(
                channel=self.interface,
                bustype='socketcan',
                bitrate=self.bitrate,
            )
            log.info("CAN bus opened: %s @ %d bps", self.interface, self.bitrate)

            self._running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            return True

        except Exception as e:
            log.error("Failed to open CAN bus %s: %s", self.interface, e)
            log.error("Check: sudo ip link set can0 up type can bitrate 500000")
            return False

    def close(self):
        """Shut down CAN bridge."""
        self._running = False
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception:
                pass
            self.bus = None
        log.info("CAN bridge closed (rx=%d tx=%d errs=%d)",
                 self.rx_count, self.tx_count, self.rx_errors)

    def is_stm32_alive(self):
        """Check if STM32 heartbeat was received in the last 3 seconds."""
        if self.last_heartbeat_time == 0:
            return False
        return (time.time() - self.last_heartbeat_time) < 3.0

    def get_imu_data(self):
        """Return latest IMU data as dict (for live_gps.py telemetry)."""
        age = time.time() - self.imu_updated if self.imu_updated else 999
        return {
            'ax': self.ax, 'ay': self.ay, 'az': self.az,
            'gx': self.gx, 'gy': self.gy, 'gz': self.gz,
            'imu_age': round(age, 2),
            'imu_valid': age < 2.0,
        }

    def get_encoder_data(self):
        """Return latest encoder data as dict."""
        return {
            'encL': self.enc_left, 'encR': self.enc_right,
            'encLVel': self.enc_left_vel, 'encRVel': self.enc_right_vel,
        }

    def get_stm32_status(self):
        """Return STM32 health info."""
        return {
            'stm32_alive': self.is_stm32_alive(),
            'stm32_uptime_ms': self.stm32_uptime_ms,
            'stm32_hb_seq': self.stm32_hb_seq,
            'stm32_eflg': self.stm32_eflg,
            'can_rx': self.rx_count,
            'can_tx': self.tx_count,
        }

    # -- Send commands to STM32 -----------------------------------------------

    def send_navigate(self, heading_deg, speed_mps):
        """Send navigate command: heading (degrees) and speed (m/s)."""
        heading_x10 = int(heading_deg * 10)
        speed_x100 = int(speed_mps * 100)
        data = struct.pack('<hh', heading_x10, speed_x100)
        return self._send(CAN_ID_NAV_CMD, data)

    def send_stop(self):
        """Send emergency stop command."""
        return self._send(CAN_ID_STOP_CMD, b'\x01')

    def send_set_speed(self, speed_mps):
        """Send set max speed command."""
        speed_x100 = int(speed_mps * 100)
        data = struct.pack('<h', speed_x100)
        return self._send(CAN_ID_SPEED_CMD, data)

    def send_ping(self):
        """Send ping to STM32 (it responds with heartbeat)."""
        return self._send(CAN_ID_PING, b'\x01')

    def _send(self, can_id, data):
        """Send a CAN frame."""
        if not self.bus:
            log.warning("CAN bus not open, cannot send id=0x%03X", can_id)
            return False
        try:
            msg = can.Message(
                arbitration_id=can_id,
                data=data,
                is_extended_id=False,
            )
            self.bus.send(msg, timeout=0.5)
            self.tx_count += 1
            log.debug("CAN TX id=0x%03X dlc=%d", can_id, len(data))
            return True
        except can.CanError as e:
            log.error("CAN TX failed id=0x%03X: %s", can_id, e)
            return False

    # -- Background read loop -------------------------------------------------

    def _read_loop(self):
        """Background thread: continuously read CAN frames from STM32."""
        log.info("CAN read loop started")
        hb_check_time = time.time()

        while self._running:
            try:
                msg = self.bus.recv(timeout=0.5)
                if msg is None:
                    # No message received (timeout)
                    # Check for heartbeat timeout
                    now = time.time()
                    if now - hb_check_time > 3.0:
                        hb_check_time = now
                        if self.last_heartbeat_time > 0 and not self.is_stm32_alive():
                            self.hb_missed += 1
                            if self.hb_missed <= 5 or self.hb_missed % 10 == 0:
                                log.warning("STM32 heartbeat missing (missed=%d, last=%.1fs ago)",
                                           self.hb_missed,
                                           now - self.last_heartbeat_time)
                    continue

                self.rx_count += 1
                self._decode(msg)

                # Reset heartbeat missed counter on any message
                if msg.arbitration_id == CAN_ID_HEARTBEAT:
                    self.hb_missed = 0

            except can.CanError as e:
                self.rx_errors += 1
                if self.rx_errors <= 5 or self.rx_errors % 50 == 0:
                    log.error("CAN read error #%d: %s", self.rx_errors, e)
            except Exception as e:
                log.error("CAN read loop exception: %s", e)

        log.info("CAN read loop stopped")

    def _decode(self, msg):
        """Decode a received CAN frame."""
        cid = msg.arbitration_id
        data = msg.data

        if cid == CAN_ID_HEARTBEAT and len(data) >= 8:
            self.stm32_uptime_ms = struct.unpack_from('<I', data, 0)[0]
            self.stm32_hb_seq = struct.unpack_from('<H', data, 4)[0]
            self.stm32_can_ok = data[6]
            self.stm32_eflg = data[7]
            self.last_heartbeat_time = time.time()

            # Log heartbeat periodically
            if self.stm32_hb_seq % 50 == 0:
                log.info("STM32 HB seq=%d uptime=%dms eflg=0x%02X",
                         self.stm32_hb_seq, self.stm32_uptime_ms, self.stm32_eflg)

        elif cid == CAN_ID_IMU_AG and len(data) >= 6:
            # ax, ay, az as int16 * 1000
            ax_i, ay_i, az_i = struct.unpack_from('<hhh', data, 0)
            self.ax = ax_i / 1000.0
            self.ay = ay_i / 1000.0
            self.az = az_i / 1000.0
            self.imu_updated = time.time()

        elif cid == CAN_ID_IMU_AG2 and len(data) >= 6:
            # gx, gy, gz as int16 * 1000
            gx_i, gy_i, gz_i = struct.unpack_from('<hhh', data, 0)
            self.gx = gx_i / 1000.0
            self.gy = gy_i / 1000.0
            self.gz = gz_i / 1000.0
            self.imu_updated = time.time()

        elif cid == CAN_ID_ENCODER and len(data) >= 8:
            self.enc_left, self.enc_right = struct.unpack_from('<ii', data, 0)

        elif cid == CAN_ID_STATUS:
            log.info("STM32 status: %s", data.hex())

        else:
            log.debug("CAN RX unknown id=0x%03X dlc=%d data=%s",
                      cid, len(data), data.hex())


# =============================================================================
# Standalone test mode
# =============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="CAN bridge test")
    parser.add_argument('--send-ping', action='store_true', help="Send ping to STM32")
    parser.add_argument('--send-nav', nargs=2, type=float, metavar=('HDG', 'SPD'),
                        help="Send navigate command (heading_deg speed_mps)")
    parser.add_argument('--send-stop', action='store_true', help="Send stop command")
    parser.add_argument('--interface', default='can0', help="CAN interface (default: can0)")
    parser.add_argument('--duration', type=int, default=30, help="Listen duration in seconds")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )

    bridge = CANBridge(interface=args.interface)
    if not bridge.open():
        print("Failed to open CAN bus. Check:")
        print("  1. /boot/firmware/config.txt has MCP2515 overlay")
        print("  2. sudo ip link set can0 up type can bitrate 500000")
        exit(1)

    print("CAN bridge running on %s, listening for %ds..." % (args.interface, args.duration))

    if args.send_ping:
        print("Sending PING to STM32...")
        bridge.send_ping()

    if args.send_nav:
        hdg, spd = args.send_nav
        print("Sending NAVIGATE: heading=%.1f speed=%.2f" % (hdg, spd))
        bridge.send_navigate(hdg, spd)

    if args.send_stop:
        print("Sending STOP")
        bridge.send_stop()

    try:
        start = time.time()
        while time.time() - start < args.duration:
            time.sleep(1)
            imu = bridge.get_imu_data()
            status = bridge.get_stm32_status()
            alive_str = "ALIVE" if status['stm32_alive'] else "DEAD"
            print("\r  [%s] hb_seq=%d uptime=%dms | ax=%.3f ay=%.3f az=%.3f | rx=%d tx=%d   " % (
                alive_str, status['stm32_hb_seq'], status['stm32_uptime_ms'],
                imu['ax'], imu['ay'], imu['az'],
                status['can_rx'], status['can_tx'],
            ), end='', flush=True)
    except KeyboardInterrupt:
        pass

    print("\nDone.")
    bridge.close()
