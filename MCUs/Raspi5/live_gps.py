#!/usr/bin/env python3
"""
live_gps.py — Send REAL GPS from SIM7600G-H to GlobalRTS via WebSocket.

Reads actual GPS coordinates from the SIM7600G-H HAT (AT+CGPSINFO on
/dev/ttyUSB2) and sends them to miraeopus.com using whatever network
the Pi already has (WiFi now, cellular later).

This is the real-GPS version of test.py. Same WebSocket protocol,
same server, same GlobalRTS UI — just real coordinates instead of
simulated ones.

Network note:
    This script does NOT set up cellular data. It uses whatever internet
    connection the Pi already has. To switch from WiFi to cellular:
      1. Bring up wwan0 (see cellular_connect.sh)
      2. Set routing so traffic goes through wwan0 instead of wlan0
      3. Run this script — it doesn't care which interface is used

Usage:
    python3 live_gps.py                              # Defaults
    python3 live_gps.py --rover-id rover-001         # Custom ID
    python3 live_gps.py --gps-port /dev/ttyUSB2      # Custom GPS port
"""

import asyncio
import json
import math
import random
import re
import time
import sys
import signal
import argparse
import logging

import serial

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
GPS_PORT   = "/dev/ttyUSB2"
GPS_BAUD   = 115200
# ────────────────────────────────────────────────────────────────────


class SIM7600GPS:
    """
    Real GPS reader for SIM7600G-H using AT+CGPSINFO.
    Same parsing logic as GPS.py.
    """

    def __init__(self, port=GPS_PORT, baudrate=GPS_BAUD):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.last_fix = None
        self.fix_count = 0
        self.no_fix_count = 0

    def open(self):
        """Open serial port and enable GPS engine."""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            log.info(f"GPS serial opened: {self.port}")

            # Enable GPS (safe to call if already on)
            resp = self._send_at("AT+CGPS=1,1", wait=2.0)
            if "ERROR" in resp and "already" not in resp.lower():
                # GPS might already be enabled — check
                resp2 = self._send_at("AT+CGPS?", wait=1.0)
                if "+CGPS: 1" in resp2:
                    log.info("GPS engine already enabled")
                else:
                    log.warning(f"GPS enable response: {resp.strip()}")
            else:
                log.info("GPS engine enabled")
            return True
        except serial.SerialException as e:
            log.error(f"Failed to open GPS port {self.port}: {e}")
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("GPS serial closed")

    def _send_at(self, cmd, wait=1.0):
        """Send AT command, return response."""
        if not self.ser or not self.ser.is_open:
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
        Read GPS fix. Returns dict or None.

        AT+CGPSINFO response:
        +CGPSINFO: lat,N/S,lon,E/W,date,time,alt,speed,course
        """
        if not self.ser:
            return None

        resp = self._send_at("AT+CGPSINFO", wait=1.0)

        m = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", resp)
        if not m:
            self.no_fix_count += 1
            return None

        payload = m.group(1).strip()
        parts = [p.strip() for p in payload.split(",")]

        if len(parts) < 8 or parts[0] == "" or parts[2] == "":
            self.no_fix_count += 1
            if self.no_fix_count % 5 == 0:
                log.info(f"Waiting for GPS fix... ({self.no_fix_count} attempts)")
            return None

        try:
            # Latitude: DDMM.MMMMMM -> decimal degrees
            lat_raw = float(parts[0])
            lat_deg = int(lat_raw // 100)
            lat_min = lat_raw - (lat_deg * 100)
            lat = lat_deg + lat_min / 60.0
            if parts[1] == "S":
                lat = -lat

            # Longitude: DDDMM.MMMMMM -> decimal degrees
            lon_raw = float(parts[2])
            lon_deg = int(lon_raw // 100)
            lon_min = lon_raw - (lon_deg * 100)
            lon = lon_deg + lon_min / 60.0
            if parts[3] == "W":
                lon = -lon

            alt = float(parts[6]) if len(parts) > 6 and parts[6] else 0.0
            speed_knots = float(parts[7]) if len(parts) > 7 and parts[7] else 0.0
            speed_mps = speed_knots * 0.514444
            heading = float(parts[8]) if len(parts) > 8 and parts[8] else 0.0

            self.fix_count += 1
            self.no_fix_count = 0

            fix = {
                "lat": lat, "lon": lon, "alt": alt,
                "speed": round(speed_mps, 2),
                "heading": round(heading, 1),
                "valid": True,
            }
            self.last_fix = fix
            return fix

        except (ValueError, IndexError) as e:
            log.warning(f"GPS parse error: {e} | raw: {payload}")
            self.no_fix_count += 1
            return None

    def get_last_or_current(self):
        """Try to read, fall back to last known fix."""
        fix = self.read()
        return fix if fix else self.last_fix


# ── Earth math (same as test.py) ───────────────────────────────────

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


# ── Rover with real GPS ────────────────────────────────────────────

class LiveRover:
    """Rover using real GPS. Same telemetry format as test.py's SimulatedRover."""

    def __init__(self, gps: SIM7600GPS):
        self.gps = gps
        self.lat = 0.0
        self.lon = 0.0
        self.alt = 0.0
        self.heading = 0.0
        self.speed = 0.0
        self.battery = 95
        self.count = 0
        self.has_fix = False

        self.target_lat = None
        self.target_lon = None
        self.nav_status = "idle"
        self.ws = None

    def set_target(self, lat, lon, alt=0.0):
        self.target_lat = lat
        self.target_lon = lon
        self.nav_status = "received"
        if self.has_fix:
            dist = haversine_distance(self.lat, self.lon, lat, lon)
            brng = bearing_to(self.lat, self.lon, lat, lon)
            print(f"\n{'='*70}")
            print(f"   NAVIGATE COMMAND RECEIVED")
            print(f"   Target:   Lat: {lat:.6f}  Lon: {lon:.6f}")
            print(f"   Current:  Lat: {self.lat:.6f}  Lon: {self.lon:.6f}")
            print(f"   Distance: {dist:.1f}m ({dist/1000:.2f}km)")
            print(f"   Bearing:  {brng:.1f}deg")
            print(f"   (No motor control yet — command logged)")
            print(f"{'='*70}")
        else:
            print(f"\n   NAVIGATE COMMAND: {lat:.6f}, {lon:.6f} (no GPS fix yet)")

    def tick(self):
        """Read real GPS, return telemetry dict."""
        self.count += 1

        fix = self.gps.get_last_or_current()
        if fix and fix["valid"]:
            self.lat = fix["lat"]
            self.lon = fix["lon"]
            self.alt = fix["alt"]
            self.speed = fix["speed"]
            self.heading = fix["heading"]
            self.has_fix = True

        # IMU placeholder (no STM32 yet)
        ax = random.randint(-50, 50)
        ay = random.randint(-50, 50)
        az = 16300 + random.randint(-100, 100)
        gx = random.randint(-5, 5)
        gy = random.randint(-5, 5)
        gz = random.randint(-3, 3)

        return {
            "id": ROVER_ID, "name": ROVER_NAME, "type": "robot",
            "lat": self.lat, "lon": self.lon, "alt": self.alt,
            "speed": self.speed, "heading": self.heading,
            "accuracy": 2.5 if self.has_fix else 0.0,
            "hdop": 1.1 if self.has_fix else 99.9,
            "pdop": 1.5 if self.has_fix else 99.9,
            "vdop": 1.3 if self.has_fix else 99.9,
            "ax": ax, "ay": ay, "az": az,
            "gx": gx, "gy": gy, "gz": gz,
            "encL": 0, "encR": 0,
            "encLVel": 0, "encRVel": 0,
            "battery": self.battery,
            "status": "online"
        }

    async def report_command_status(self):
        if self.ws:
            try:
                await self.ws.send(json.dumps({
                    "type": "rover:command_status",
                    "data": {"id": ROVER_ID, "status": self.nav_status}
                }))
            except Exception:
                pass


# ── WebSocket loop ─────────────────────────────────────────────────

async def run(gps: SIM7600GPS):
    rover = LiveRover(gps)

    while True:
        try:
            print(f"\n Connecting to {SERVER} ...")

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
                print(f" Connected! Position: {fix_str}")
                print(f"   Sending REAL GPS to miraeopus.com ...\n")

                async def telemetry_loop():
                    while True:
                        data = rover.tick()
                        await ws.send(json.dumps({"type": "rover:telemetry", "data": data}))
                        await rover.report_command_status()

                        if rover.has_fix:
                            extra = ""
                            if rover.target_lat is not None:
                                dist = haversine_distance(
                                    rover.lat, rover.lon,
                                    rover.target_lat, rover.target_lon
                                )
                                extra = f" | target:{dist:.0f}m"
                            print(f"\r #{rover.count:>4d} | {rover.lat:.6f}, {rover.lon:.6f} | "
                                  f"alt:{rover.alt:.1f}m | H:{rover.heading:5.1f}deg | "
                                  f"{rover.speed:.1f}m/s | FIX{extra}  ",
                                  end="", flush=True)
                        else:
                            print(f"\r  #{rover.count:>4d} | NO GPS FIX "
                                  f"(attempt {gps.no_fix_count}) | waiting...  ",
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
        description='Send REAL GPS from SIM7600G-H to GlobalRTS'
    )
    parser.add_argument('--gps-port', default='/dev/ttyUSB2',
                        help='GPS AT command port (default: /dev/ttyUSB2)')
    parser.add_argument('--rover-id', default='rover-001',
                        help='Rover ID (default: rover-001)')
    parser.add_argument('--rover-name', default='RasPi Rover',
                        help='Rover display name')
    parser.add_argument('--server', default='wss://miraeopus.com/rover',
                        help='WebSocket server URL')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    args = parser.parse_args()

    global ROVER_ID, ROVER_NAME, SERVER
    ROVER_ID = args.rover_id
    ROVER_NAME = args.rover_name
    SERVER = args.server

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    gps = SIM7600GPS(port=args.gps_port, baudrate=GPS_BAUD)

    def cleanup(sig=None, frame=None):
        print("\nShutting down...")
        gps.close()
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(f"{'='*60}")
    print(f"  GlobalRTS Rover — LIVE GPS")
    print(f"  Server : {SERVER}")
    print(f"  Rover  : {ROVER_ID} ({ROVER_NAME})")
    print(f"  GPS    : {args.gps_port}")
    print(f"{'='*60}\n")

    # Open GPS
    if not gps.open():
        print(f"Failed to open GPS on {args.gps_port}")
        print("Check: ls /dev/ttyUSB*")
        print("Check: sudo systemctl stop ModemManager")
        sys.exit(1)

    # Wait for initial fix
    print("Waiting for GPS fix (up to 60s, need clear sky)...")
    for i in range(60):
        fix = gps.read()
        if fix and fix["valid"]:
            print(f"\n  GPS FIX: {fix['lat']:.6f}, {fix['lon']:.6f}")
            print(f"  Alt: {fix['alt']:.1f}m  Speed: {fix['speed']:.1f}m/s  Heading: {fix['heading']:.1f}deg")
            break
        dots = "." * ((i % 3) + 1)
        print(f"  Searching{dots:<3s} ({i+1}/60)  ", end="\r")
        time.sleep(1)
    else:
        print("\n  No GPS fix yet — starting anyway (will get fix outdoors)")

    # Run
    print("\nStarting WebSocket telemetry...\n")
    try:
        asyncio.run(run(gps))
    except KeyboardInterrupt:
        pass
    finally:
        gps.close()
        print("Done.")


if __name__ == "__main__":
    main()
