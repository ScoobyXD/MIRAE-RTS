#!/usr/bin/env python3
"""
live_gps.py — Send REAL GPS from SIM7600G-H to GlobalRTS via WebSocket.

OPTION B IMPLEMENTED:
- WiFi stays up for SSH (no route changes, no WiFi shutdown).
- If you run with --cellular, ONLY the WebSocket connection is forced to use cellular
  by binding the outgoing socket to the wwan0 interface IP.
- If you run without --cellular, it uses normal routing (usually WiFi).

Usage:
  python3 live_gps.py
  python3 live_gps.py --rover-id rover-001
  python3 live_gps.py --cellular                 # force ONLY WebSocket over wwan0
  python3 live_gps.py --cellular --cell-iface wwan0
  python3 live_gps.py --gps-port /dev/ttyUSB2
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
import socket
import subprocess
from urllib.parse import urlparse

import serial

try:
    import websockets
except ImportError:
    print("Install websockets first:  pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('live_gps')

# ── Defaults ────────────────────────────────────────────────────────
SERVER     = "wss://miraeopus.com/rover"
ROVER_ID   = "rover-001"
ROVER_NAME = "RasPi Rover"
GPS_PORT   = "/dev/ttyUSB2"
GPS_BAUD   = 115200
# ────────────────────────────────────────────────────────────────────


def get_iface_ipv4(iface: str) -> str | None:
    """
    Return IPv4 address (string) for a Linux network interface, e.g. 'wwan0' or 'wlan0'.
    Uses `ip -4 addr show dev <iface>`.
    """
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show", "dev", iface], text=True)
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", out)
        return m.group(1) if m else None
    except Exception:
        return None


def resolve_host_ipv4(host: str) -> str | None:
    """Resolve hostname to an IPv4 string."""
    try:
        return socket.gethostbyname(host)
    except Exception:
        return None


def parse_ws_host(server_url: str) -> str | None:
    """
    Extract hostname from ws(s):// URL.
    """
    try:
        u = urlparse(server_url)
        return u.hostname
    except Exception:
        return None


def make_bound_tcp_socket(source_ip: str, dest_host: str, dest_port: int, timeout_s: float = 10.0) -> socket.socket:
    """
    Create a TCP socket bound to source_ip, connect to dest_host:dest_port, and return it.
    This forces the route/interface selection based on source address WITHOUT touching system routes.
    """
    dest_ip = resolve_host_ipv4(dest_host) or dest_host

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_s)

    # Bind to the interface's IP, ephemeral port
    s.bind((source_ip, 0))

    # Connect to server (TCP established). websockets will wrap this.
    s.connect((dest_ip, dest_port))

    # websockets expects a socket; it will manage it. Put it back to blocking mode.
    s.settimeout(None)
    return s


class SIM7600GPS:
    """Real GPS reader for SIM7600G-H using AT+CGPSINFO."""

    def __init__(self, port=GPS_PORT, baudrate=GPS_BAUD):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.last_fix = None
        self.fix_count = 0
        self.no_fix_count = 0

    def open(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            log.info(f"GPS serial opened: {self.port}")

            resp = self._send_at("AT+CGPS=1,1", wait=2.0)
            if "ERROR" in resp and "already" not in resp.lower():
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
            lat_raw = float(parts[0])
            lat_deg = int(lat_raw // 100)
            lat_min = lat_raw - (lat_deg * 100)
            lat = lat_deg + lat_min / 60.0
            if parts[1] == "S":
                lat = -lat

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
        fix = self.read()
        return fix if fix else self.last_fix


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


class LiveRover:
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
            print("   NAVIGATE COMMAND RECEIVED")
            print(f"   Target:   Lat: {lat:.6f}  Lon: {lon:.6f}")
            print(f"   Current:  Lat: {self.lat:.6f}  Lon: {self.lon:.6f}")
            print(f"   Distance: {dist:.1f}m ({dist/1000:.2f}km)")
            print(f"   Bearing:  {brng:.1f}deg")
            print("   (No motor control yet — command logged)")
            print(f"{'='*70}")
        else:
            print(f"\n   NAVIGATE COMMAND: {lat:.6f}, {lon:.6f} (no GPS fix yet)")

    def tick(self):
        self.count += 1

        fix = self.gps.get_last_or_current()
        if fix and fix["valid"]:
            self.lat = fix["lat"]
            self.lon = fix["lon"]
            self.alt = fix["alt"]
            self.speed = fix["speed"]
            self.heading = fix["heading"]
            self.has_fix = True

        # IMU placeholder
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


async def run(gps: SIM7600GPS, use_cellular: bool, cell_iface: str):
    rover = LiveRover(gps)

    ws_host = parse_ws_host(SERVER)
    if not ws_host:
        raise RuntimeError(f"Bad SERVER url: {SERVER}")

    is_wss = SERVER.startswith("wss://")
    ws_port = 443 if is_wss else 80

    while True:
        try:
            print(f"\n Connecting to {SERVER} ...")

            sock = None
            if use_cellular:
                src_ip = get_iface_ipv4(cell_iface)
                if not src_ip:
                    print(f"\n ERROR: --cellular set but {cell_iface} has no IPv4 address.")
                    print(f" Fix: bring up cellular so {cell_iface} gets an IP, then retry.")
                    print(f" Check: ip -4 addr show dev {cell_iface}")
                    await asyncio.sleep(5)
                    continue

                try:
                    sock = make_bound_tcp_socket(src_ip, ws_host, ws_port, timeout_s=10.0)
                    print(f" Cellular mode: WebSocket bound to {cell_iface} ({src_ip})")
                except OSError as e:
                    print(f"\n ERROR: Failed to bind/connect via {cell_iface} ({src_ip}): {e}")
                    print(f" Check: {cell_iface} up? route? DNS? signal?")
                    await asyncio.sleep(5)
                    continue

            # IMPORTANT: No system routing changes. WiFi stays for SSH.
            async with websockets.connect(
                SERVER,
                ping_interval=20,
                ping_timeout=10,
                sock=sock,  # None = normal routing; bound socket = cellular-only
            ) as ws:
                rover.ws = ws

                await ws.send(json.dumps({
                    "type": "rover:identify",
                    "data": {"id": ROVER_ID, "name": ROVER_NAME, "type": "robot"}
                }))
                print(" Sent identify")

                ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                ack = json.loads(ack_raw)
                if ack.get("type") != "ack":
                    print(f"  Expected ack, got {ack.get('type')}")

                fix_str = f"{rover.lat:.6f}, {rover.lon:.6f}" if rover.has_fix else "waiting for GPS fix..."
                print(f" Connected! Position: {fix_str}")
                print("   Sending REAL GPS to miraeopus.com ...\n")

                async def telemetry_loop():
                    while True:
                        data = rover.tick()
                        await ws.send(json.dumps({"type": "rover:telemetry", "data": data}))
                        await rover.report_command_status()

                        if rover.has_fix:
                            extra = ""
                            if rover.target_lat is not None:
                                dist = haversine_distance(rover.lat, rover.lon, rover.target_lat, rover.target_lon)
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
                                print("\n STOP command received!")
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
            print("\n No ack from server (timeout)")
        except OSError as e:
            print(f"\n Network error: {e}")

        rover.ws = None
        print("\n   Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


def main():
    parser = argparse.ArgumentParser(description='Send REAL GPS from SIM7600G-H to GlobalRTS')
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

    # OPTION B flag:
    parser.add_argument('--cellular', action='store_true',
                        help='Force ONLY the WebSocket connection to use cellular (bind to wwan0). WiFi stays up for SSH.')
    parser.add_argument('--cell-iface', default='wwan0',
                        help='Cellular interface name (default: wwan0)')

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
    print("  GlobalRTS Rover LIVE GPS")
    print(f"  Server : {SERVER}")
    print(f"  Rover  : {ROVER_ID} ({ROVER_NAME})")
    print(f"  GPS    : {args.gps_port}")
    print(f"  Mode   : {'CELLULAR (WebSocket bound)' if args.cellular else 'DEFAULT (system routing)'}")
    if args.cellular:
        print(f"  Iface  : {args.cell_iface}")
    print(f"{'='*60}\n")

    if args.cellular:
        ipaddr = get_iface_ipv4(args.cell_iface)
        if not ipaddr:
            print(f"WARNING: {args.cell_iface} has no IPv4 yet. Start cellular first, then rerun.")
            print(f"Check: ip -4 addr show dev {args.cell_iface}\n")
        else:
            print(f"Cellular interface {args.cell_iface} IPv4: {ipaddr}\n")

    if not gps.open():
        print(f"Failed to open GPS on {args.gps_port}")
        print("Check: ls /dev/ttyUSB*")
        print("Check: sudo systemctl stop ModemManager")
        sys.exit(1)

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

    print("\nStarting WebSocket telemetry...\n")
    try:
        asyncio.run(run(gps, use_cellular=args.cellular, cell_iface=args.cell_iface))
    except KeyboardInterrupt:
        pass
    finally:
        gps.close()
        print("Done.")


if __name__ == "__main__":
    main()
