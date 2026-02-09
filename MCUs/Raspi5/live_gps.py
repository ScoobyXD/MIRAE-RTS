#!/usr/bin/env python3
"""
live_gps.py — Send REAL GPS from SIM7600G-H over CELLULAR to GlobalRTS.

This is the bridge between your working GPS.py and the working test.py.
It reads actual GPS coordinates from the SIM7600G-H HAT via AT commands,
then sends them over cellular (T-Mobile) to miraeopus.com via WebSocket.

The SIM7600G-H HAT provides BOTH GPS and cellular on the same hardware:
  - GPS:      AT+CGPSINFO on /dev/ttyUSB2
  - Cellular: PPP/NDIS data on /dev/ttyUSB3

IMPORTANT: GPS reads and cellular init both use /dev/ttyUSB2 for AT commands.
This script coordinates access so they don't collide:
  1. cellular.py initializes modem + brings up data on /dev/ttyUSB3
  2. After cellular is up, we open /dev/ttyUSB2 for GPS reads
  3. GPS reads are quick AT+CGPSINFO calls (non-blocking)

Usage:
    sudo python3 live_gps.py                          # Default (Mint/T-Mobile)
    sudo python3 live_gps.py --apn fast.t-mobile.com  # T-Mobile postpaid
    sudo python3 live_gps.py --rover-id rover-001     # Custom rover ID

You need sudo because cellular (pppd) requires root for network interfaces.
"""

import asyncio
import json
import math
import random
import time
import sys
import signal
import argparse
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import serial

# Import our cellular manager
from cellular import CellularManager

try:
    import websockets
except ImportError:
    print("Install websockets first:  pip install websockets")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('live_gps')

# ── Config ──────────────────────────────────────────────────────────
SERVER     = "wss://miraeopus.com/rover"
ROVER_ID   = "rover-001"
ROVER_NAME = "RasPi Rover"

# GPS serial port (same as GPS.py)
GPS_PORT   = "/dev/ttyUSB2"
GPS_BAUD   = 115200
# ────────────────────────────────────────────────────────────────────


class SIM7600GPS:
    """
    Real GPS reader for SIM7600G-H, adapted from GPS.py.
    
    Uses AT+CGPSINFO to get lat/lon/alt/speed/heading.
    Opens its own serial connection to /dev/ttyUSB2.
    """

    def __init__(self, port=GPS_PORT, baudrate=GPS_BAUD):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.gps_enabled = False
        self.last_fix = None
        self.fix_count = 0
        self.no_fix_count = 0

    def open(self):
        """Open serial port and enable GPS engine."""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            log.info(f"GPS serial opened: {self.port}")
            # Enable GPS (safe to call repeatedly)
            resp = self._send_at("AT+CGPS=1,1", wait=2.0)
            if "OK" in resp or "already" in resp.lower():
                self.gps_enabled = True
                log.info("GPS engine enabled (AT+CGPS=1,1)")
            elif "ERROR" in resp:
                # GPS might already be on
                log.warning(f"GPS enable response: {resp.strip()}")
                self.gps_enabled = True  # Assume it's already on
            return True
        except serial.SerialException as e:
            log.error(f"Failed to open GPS port {self.port}: {e}")
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("GPS serial closed")

    def _send_at(self, cmd, wait=1.0):
        """Send AT command, return response. Same as GPS.py's send_at."""
        if not self.ser:
            return ""
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass
        self.ser.write((cmd + "\r\n").encode())
        time.sleep(wait)
        out = b""
        while self.ser.in_waiting:
            out += self.ser.read(self.ser.in_waiting)
            time.sleep(0.05)
        return out.decode(errors="ignore")

    def read(self):
        """
        Read GPS fix from AT+CGPSINFO.
        
        Returns dict with GPS data, or None if no fix.
        
        AT+CGPSINFO response format:
        +CGPSINFO: lat,N/S,lon,E/W,date,time,alt,speed,course
        Example:
        +CGPSINFO: 3353.518640,N,11753.425498,W,090226,012345.0,85.3,0.0,270.5
        
        Fields:
          lat:    DDMM.MMMMMM
          N/S:    Hemisphere
          lon:    DDDMM.MMMMMM  
          E/W:    Hemisphere
          date:   DDMMYY
          time:   HHMMSS.S
          alt:    meters (MSL)
          speed:  knots
          course: degrees (heading/bearing)
        """
        if not self.ser:
            return None

        resp = self._send_at("AT+CGPSINFO", wait=1.0)

        # Extract +CGPSINFO payload
        m = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", resp)
        if not m:
            self.no_fix_count += 1
            return None

        payload = m.group(1).strip()
        parts = [p.strip() for p in payload.split(",")]

        # Check if fix is valid (empty fields = no fix)
        if len(parts) < 8 or parts[0] == "" or parts[2] == "":
            self.no_fix_count += 1
            if self.no_fix_count % 5 == 0:
                log.info(f"Waiting for GPS fix... ({self.no_fix_count} attempts)")
            return None

        try:
            # Parse latitude (DDMM.MMMMMM -> decimal degrees)
            lat_raw = float(parts[0])
            lat_deg = int(lat_raw // 100)
            lat_min = lat_raw - (lat_deg * 100)
            lat = lat_deg + lat_min / 60.0
            if parts[1] == "S":
                lat = -lat

            # Parse longitude (DDDMM.MMMMMM -> decimal degrees)
            lon_raw = float(parts[2])
            lon_deg = int(lon_raw // 100)
            lon_min = lon_raw - (lon_deg * 100)
            lon = lon_deg + lon_min / 60.0
            if parts[3] == "W":
                lon = -lon

            # Altitude (meters)
            alt = float(parts[6]) if len(parts) > 6 and parts[6] else 0.0

            # Speed: knots -> m/s (1 knot = 0.514444 m/s)
            speed_knots = float(parts[7]) if len(parts) > 7 and parts[7] else 0.0
            speed_mps = speed_knots * 0.514444

            # Course/heading (degrees)
            heading = float(parts[8]) if len(parts) > 8 and parts[8] else 0.0

            # Timestamp
            date_str = parts[4] if len(parts) > 4 else ""
            time_str = parts[5].split(".")[0] if len(parts) > 5 else ""

            self.fix_count += 1
            self.no_fix_count = 0

            fix = {
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "speed": round(speed_mps, 2),
                "heading": round(heading, 1),
                "date": date_str,
                "time": time_str,
                "valid": True,
            }
            self.last_fix = fix
            return fix

        except (ValueError, IndexError) as e:
            log.warning(f"GPS parse error: {e} | raw: {payload}")
            self.no_fix_count += 1
            return None

    def get_last_or_current(self):
        """Try to read, return last known fix if current read fails."""
        fix = self.read()
        if fix:
            return fix
        return self.last_fix  # Could be None if never had a fix


class LiveRover:
    """
    Rover state using REAL GPS data from SIM7600G-H.
    
    Unlike SimulatedRover in test.py, this doesn't simulate movement.
    It just reads real GPS and packages telemetry.
    Navigation commands are logged but not acted on (no STM32 yet).
    """

    def __init__(self, gps: SIM7600GPS):
        self.gps = gps
        self.lat = 0.0
        self.lon = 0.0
        self.alt = 0.0
        self.heading = 0.0
        self.speed = 0.0
        self.battery = 95  # TODO: read actual battery
        self.count = 0
        self.has_fix = False

        # Command tracking (display only, no motor control yet)
        self.target_lat = None
        self.target_lon = None
        self.nav_status = "idle"

        self.ws = None

    def set_target(self, lat, lon, alt=0.0):
        """Log navigation command. No motor control yet."""
        self.target_lat = lat
        self.target_lon = lon
        self.nav_status = "received"
        if self.has_fix:
            dist = haversine_distance(self.lat, self.lon, lat, lon)
            brng = bearing_to(self.lat, self.lon, lat, lon)
            print(f"\n{'='*70}")
            print(f"   NAVIGATE COMMAND RECEIVED")
            print(f"   Target:   Lat: {lat:.6f}  Lon: {lon:.6f}  Alt: {alt:.1f}m")
            print(f"   Current:  Lat: {self.lat:.6f}  Lon: {self.lon:.6f}")
            print(f"   Distance: {dist:.1f}m ({dist/1000:.2f}km)")
            print(f"   Bearing:  {brng:.1f}deg")
            print(f"   (No motor control yet - command logged)")
            print(f"{'='*70}")
        else:
            print(f"\n   NAVIGATE COMMAND: {lat:.6f}, {lon:.6f} (no GPS fix yet)")

    def tick(self):
        """Read real GPS and build telemetry packet."""
        self.count += 1

        fix = self.gps.get_last_or_current()
        if fix and fix["valid"]:
            self.lat = fix["lat"]
            self.lon = fix["lon"]
            self.alt = fix["alt"]
            self.speed = fix["speed"]
            self.heading = fix["heading"]
            self.has_fix = True
        # If no fix, keep last known position (lat/lon stay as-is)

        # IMU placeholder (no STM32 connected yet)
        # Small random noise to show the field is active
        ax = random.randint(-50, 50)
        ay = random.randint(-50, 50)
        az = 16300 + random.randint(-100, 100)
        gx = random.randint(-5, 5)
        gy = random.randint(-5, 5)
        gz = random.randint(-3, 3)

        return {
            "id": ROVER_ID,
            "name": ROVER_NAME,
            "type": "robot",
            "lat": self.lat,
            "lon": self.lon,
            "alt": self.alt,
            "speed": self.speed,
            "heading": self.heading,
            "accuracy": 2.5 if self.has_fix else 0.0,
            "hdop": 1.1 if self.has_fix else 99.9,
            "pdop": 1.5 if self.has_fix else 99.9,
            "vdop": 1.3 if self.has_fix else 99.9,
            "ax": ax, "ay": ay, "az": az,
            "gx": gx, "gy": gy, "gz": gz,
            "encL": 0, "encR": 0,      # No encoders yet
            "encLVel": 0, "encRVel": 0,
            "battery": self.battery,
            "status": "online"
        }

    async def report_command_status(self):
        """Report nav status to server."""
        if self.ws:
            try:
                await self.ws.send(json.dumps({
                    "type": "rover:command_status",
                    "data": {"id": ROVER_ID, "status": self.nav_status}
                }))
            except Exception:
                pass


# ── Earth math helpers (same as test.py) ────────────────────────────

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(rlat1)*math.cos(rlat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def bearing_to(lat1, lon1, lat2, lon2):
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1)*math.sin(rlat2) - math.sin(rlat1)*math.cos(rlat2)*math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ── Main WebSocket loop ────────────────────────────────────────────

async def run(cell: CellularManager, gps: SIM7600GPS):
    """WebSocket loop sending real GPS over cellular."""
    rover = LiveRover(gps)

    while True:
        try:
            # Check cellular is still up
            if not cell.is_connected():
                print("  Cellular connection lost, waiting for reconnect...")
                await asyncio.sleep(5)
                continue

            sig_pct, sig_dbm, net_type = cell.get_signal()
            print(f"\n Connecting to {SERVER} via {net_type} ({sig_pct}%, {sig_dbm}dBm)...")

            async with websockets.connect(SERVER, ping_interval=20, ping_timeout=10) as ws:
                rover.ws = ws

                # Identify
                await ws.send(json.dumps({
                    "type": "rover:identify",
                    "data": {"id": ROVER_ID, "name": ROVER_NAME, "type": "robot"}
                }))
                print(f" Sent identify")

                # Wait for ack
                ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                ack = json.loads(ack_raw)
                if ack.get("type") != "ack":
                    print(f"  Expected ack, got {ack.get('type')}")

                fix_str = f"{rover.lat:.6f}, {rover.lon:.6f}" if rover.has_fix else "waiting for GPS fix..."
                print(f" Connected via CELLULAR! Position: {fix_str}")
                print(f"   Sending REAL GPS to miraeopus.com ...\n")

                # Concurrent send/receive
                async def telemetry_loop():
                    while True:
                        data = rover.tick()
                        await ws.send(json.dumps({"type": "rover:telemetry", "data": data}))
                        await rover.report_command_status()

                        # Status line
                        if rover.has_fix:
                            fix_sym = "FIX"
                            extra = ""
                            if rover.target_lat is not None:
                                dist = haversine_distance(
                                    rover.lat, rover.lon,
                                    rover.target_lat, rover.target_lon
                                )
                                extra = f" | target:{dist:.0f}m"
                            print(f"\r #{rover.count:>4d} | {rover.lat:.6f}, {rover.lon:.6f} | "
                                  f"alt:{rover.alt:.1f}m | H:{rover.heading:5.1f}deg | "
                                  f"{rover.speed:.1f}m/s | {fix_sym} | 4G{extra}  ",
                                  end="", flush=True)
                        else:
                            print(f"\r  #{rover.count:>4d} | NO GPS FIX "
                                  f"(attempt {gps.no_fix_count}) | 4G  ",
                                  end="", flush=True)

                        await asyncio.sleep(1.0)

                async def receive_loop():
                    async for raw in ws:
                        msg = json.loads(raw)
                        msg_type = msg.get("type", "")
                        data = msg.get("data", {})

                        if msg_type == "command":
                            cmd_type = data.get("type", "")
                            payload = data.get("payload", {})
                            if cmd_type == "navigate":
                                t_lat = payload.get("latitude")
                                t_lon = payload.get("longitude")
                                t_alt = payload.get("altitude", 0)
                                if t_lat is not None and t_lon is not None:
                                    rover.set_target(t_lat, t_lon, t_alt)
                            elif cmd_type == "stop":
                                print(f"\n STOP command received!")
                                rover.target_lat = None
                                rover.target_lon = None
                                rover.nav_status = "idle"
                            else:
                                print(f"\n Command: {cmd_type} | {payload}")
                        elif msg_type == "selected":
                            print(f"\n  {ROVER_NAME} selected")
                        elif msg_type == "deselected":
                            print(f"\n  {ROVER_NAME} deselected")
                        elif msg_type == "ack":
                            pass
                        else:
                            print(f"\n {msg_type}: {data}")

                await asyncio.gather(telemetry_loop(), receive_loop())

        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException) as e:
            print(f"\n Connection lost: {e}")
        except asyncio.TimeoutError:
            print(f"\n No ack from server (timeout)")
        except OSError as e:
            print(f"\n Network error: {e}")

        rover.ws = None
        print(f"   Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


def main():
    parser = argparse.ArgumentParser(
        description='Send REAL GPS from SIM7600G-H over cellular to GlobalRTS'
    )
    parser.add_argument('--apn', default='super',
                        help='Carrier APN (default: super for Mint/T-Mobile)')
    parser.add_argument('--at-port', default='/dev/ttyUSB2',
                        help='AT command port (default: /dev/ttyUSB2)')
    parser.add_argument('--ppp-port', default='/dev/ttyUSB3',
                        help='PPP/modem port (default: /dev/ttyUSB3)')
    parser.add_argument('--gps-port', default='/dev/ttyUSB2',
                        help='GPS AT command port (default: /dev/ttyUSB2)')
    parser.add_argument('--rover-id', default='rover-001',
                        help='Rover ID (default: rover-001)')
    parser.add_argument('--rover-name', default='RasPi Rover',
                        help='Rover display name')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    args = parser.parse_args()

    global ROVER_ID, ROVER_NAME, GPS_PORT
    ROVER_ID = args.rover_id
    ROVER_NAME = args.rover_name
    GPS_PORT = args.gps_port

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Step 1: Initialize cellular modem ──
    cell = CellularManager(
        at_port=args.at_port,
        ppp_port=args.ppp_port,
        apn=args.apn,
    )

    # ── Step 2: Create GPS reader ──
    gps = SIM7600GPS(port=args.gps_port, baudrate=GPS_BAUD)

    def cleanup(sig=None, frame=None):
        print("\nShutting down...")
        gps.close()
        cell.cleanup()
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(f"{'='*60}")
    print(f"  GlobalRTS Rover — LIVE GPS over CELLULAR")
    print(f"  Server : {SERVER}")
    print(f"  Rover  : {ROVER_ID} ({ROVER_NAME})")
    print(f"  APN    : {args.apn}")
    print(f"  AT Port: {args.at_port}")
    print(f"  GPS    : {args.gps_port}")
    print(f"{'='*60}\n")

    # Initialize modem (uses AT port for setup commands)
    if not cell.initialize():
        print(f"\nModem init failed: {cell.status.error}")
        print("Check that the SIM7600G-H is powered and USB is connected.")
        print("Run: ls /dev/ttyUSB*  to verify serial ports exist.")
        sys.exit(1)

    # Bring up cellular data connection
    if not cell.connect_direct():
        print("\nFailed to establish cellular data. Check APN and SIM card.")
        cell.cleanup()
        sys.exit(1)

    cell.print_status()
    cell.start_monitor()

    # Now open GPS serial (after cellular init is done with AT port)
    # Both cellular init and GPS use /dev/ttyUSB2 for AT commands.
    # cellular.py's init phase is done now, so GPS can use it.
    # The cellular monitor thread only uses AT commands occasionally
    # for signal checks, and our GPS reads are quick, so they coexist fine.
    print("Opening GPS serial port...")
    if not gps.open():
        print("WARNING: Could not open GPS. Will retry during operation.")
        # Don't exit — cellular is up, GPS might come later

    # Wait briefly for first GPS fix
    print("Waiting for initial GPS fix (up to 30s)...")
    for i in range(30):
        fix = gps.read()
        if fix and fix["valid"]:
            print(f"\n  Got GPS fix: {fix['lat']:.6f}, {fix['lon']:.6f}")
            print(f"  Alt: {fix['alt']:.1f}m  Speed: {fix['speed']:.1f}m/s  Heading: {fix['heading']:.1f}deg")
            break
        print(f"  Waiting... ({i+1}/30)", end="\r")
        time.sleep(1)
    else:
        print("\n  No GPS fix yet — starting anyway, will get fix during operation.")
        print("  (Make sure you're outdoors with clear sky view)")

    # ── Step 3: Run the rover ──
    print("\nCellular + GPS ready. Starting rover...\n")

    try:
        asyncio.run(run(cell, gps))
    except KeyboardInterrupt:
        pass
    finally:
        gps.close()
        cell.cleanup()
        print("Done.")


if __name__ == "__main__":
    main()
