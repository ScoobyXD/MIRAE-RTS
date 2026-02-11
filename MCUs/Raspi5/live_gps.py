#!/usr/bin/env python3
"""
live_gps.py -- Send REAL GPS from SIM7600G-H to GlobalRTS via WebSocket.

Reads GPS from the SIM7600G-H HAT using two sources:
  - /dev/ttyUSB2 (AT commands): AT+CGPSINFO for lat/lon/alt/speed/heading
  - /dev/ttyUSB1 (NMEA port): $GPGGA for HDOP/sats/altitude, $GPGSA for PDOP/HDOP/VDOP

Sends telemetry to miraeopus.com via WebSocket. Receives commands from GlobalRTS
(laptop -> miraeopus.com -> SIM7600 cellular -> Raspi).

Network modes:
    python3 live_gps.py              WiFi (wlan0) -- for dev/testing
    python3 live_gps.py --cellular   Cellular (wwan0) -- for field use
                                     Only WebSocket uses cellular. WiFi stays for SSH.

Prerequisites for cellular mode:
    sudo apt install libqmi-utils udhcpc
    sudo bash cellular_connect.sh    # brings up wwan0 with IP
"""

import asyncio
import json
import math
import random
import re
import socket
import struct
import time
import sys
import signal
import argparse
import logging
import logging.handlers
import os
import subprocess
import threading

import serial

try:
    import websockets
except ImportError:
    print("Install websockets first:  pip install websockets")
    sys.exit(1)

try:
    from can_bridge import CANBridge, setup_can_logging
except ImportError:
    CANBridge = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('live_gps')

# Set up rotating file log
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOG_DIR, 'live_gps.log'),
    maxBytes=5*1024*1024,
    backupCount=10,
)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logging.getLogger().addHandler(_file_handler)

# -- Config -------------------------------------------------------------------
SERVER     = "wss://miraeopus.com/rover"
ROVER_ID   = "rover-001"
ROVER_NAME = "RasPi Rover"
AT_PORT    = "/dev/ttyUSB2"
NMEA_PORT  = "/dev/ttyUSB1"
GPS_BAUD   = 115200
CELLULAR_IFACE = "wwan0"
# -----------------------------------------------------------------------------


# =============================================================================
# Network helpers
# =============================================================================

def get_interface_ip(iface):
    """Get the IPv4 address of a network interface, or None."""
    try:
        result = subprocess.run(
            ['ip', '-4', 'addr', 'show', iface],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.split('\n'):
            if 'inet ' in line:
                return line.strip().split()[1].split('/')[0]
    except Exception:
        pass
    return None


def create_cellular_socket(target_host, target_port):
    """
    Create a raw TCP socket bound to wwan0 at the kernel level using SO_BINDTODEVICE,
    then connect it to the target. We do NOT wrap with SSL here -- websockets handles that.
    Requires root (sudo) because SO_BINDTODEVICE is a privileged operation.
    """
    ip = get_interface_ip(CELLULAR_IFACE)
    if not ip:
        log.error(
            "No IP on %s. Run: sudo bash cellular_connect.sh", CELLULAR_IFACE
        )
        return None

    log.info("Forcing connection through %s (%s) via SO_BINDTODEVICE", CELLULAR_IFACE, ip)

    # Resolve DNS
    addrs = socket.getaddrinfo(target_host, target_port, socket.AF_INET, socket.SOCK_STREAM)
    if not addrs:
        log.error("DNS resolution failed for %s", target_host)
        return None
    target_ip = addrs[0][4][0]
    log.info("Resolved %s -> %s", target_host, target_ip)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # SO_BINDTODEVICE: kernel-level binding to the interface.
        # All packets from this socket go through wwan0 regardless of routing table.
        sock.setsockopt(socket.SOL_SOCKET, 25, CELLULAR_IFACE.encode() + b'\0')  # 25 = SO_BINDTODEVICE
        sock.settimeout(15)
        sock.connect((target_ip, target_port))
        sock.settimeout(None)
        log.info("Connected to %s:%d via %s (raw TCP, SSL will be added by websockets)",
                 target_ip, target_port, CELLULAR_IFACE)
        return sock
    except Exception as e:
        log.error("Failed to connect via %s: %s", CELLULAR_IFACE, e)
        sock.close()
        return None


# =============================================================================
# NMEA reader (runs on background thread, reads /dev/ttyUSB1)
# =============================================================================

class NMEAReader:
    """
    Reads NMEA sentences from /dev/ttyUSB1 to get HDOP, PDOP, VDOP,
    satellite count, and a second source of altitude.

    The SIM7600G-H outputs NMEA on ttyUSB1 automatically when GPS is enabled.
    Key sentences:
      $GPGGA: time, lat, lon, fix_quality, num_sats, hdop, alt, ...
      $GPGSA: mode, fix_type, sat_ids..., pdop, hdop, vdop
      $GPRMC: time, status, lat, lon, speed_knots, heading, date, ...
      $GPVTG: true_heading, ..., speed_knots, ..., speed_kmh, ...
    """

    def __init__(self, port=NMEA_PORT, baudrate=GPS_BAUD):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._thread = None
        self._running = False

        # Parsed data (updated by background thread)
        self.hdop = 99.9
        self.pdop = 99.9
        self.vdop = 99.9
        self.num_sats = 0
        self.fix_quality = 0
        self.gga_alt = 0.0
        self.rmc_speed_mps = 0.0
        self.rmc_heading = 0.0
        self.vtg_speed_mps = 0.0
        self.vtg_heading = 0.0
        self.last_update = 0

    def open(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            log.info("NMEA port opened: %s", self.port)
            self._running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            return True
        except serial.SerialException as e:
            log.warning("NMEA port %s unavailable: %s (HDOP/PDOP will be estimated)", self.port, e)
            return False

    def close(self):
        self._running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

    def _read_loop(self):
        """Background thread: continuously read and parse NMEA sentences."""
        while self._running:
            try:
                if not self.ser or not self.ser.is_open:
                    break
                line = self.ser.readline().decode(errors='ignore').strip()
                if not line:
                    continue
                self._parse(line)
            except serial.SerialException:
                log.warning("NMEA port read error, stopping reader")
                break
            except Exception as e:
                log.debug("NMEA parse exception: %s", e)

    def _parse(self, line):
        """Parse a single NMEA sentence."""
        # $GPGGA,HHMMSS.SS,lat,N,lon,W,qual,numSV,hdop,alt,M,geoid,M,age,refid*CS
        if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
            parts = line.split(',')
            if len(parts) >= 10:
                try:
                    self.fix_quality = int(parts[6]) if parts[6] else 0
                    self.num_sats = int(parts[7]) if parts[7] else 0
                    self.hdop = float(parts[8]) if parts[8] else 99.9
                    self.gga_alt = float(parts[9]) if parts[9] else 0.0
                    self.last_update = time.time()
                except (ValueError, IndexError):
                    pass

        # $GPGSA,mode,fixtype,sv1,...,sv12,pdop,hdop,vdop*CS
        elif line.startswith('$GPGSA') or line.startswith('$GNGSA'):
            parts = line.split(',')
            if len(parts) >= 17:
                try:
                    pdop_str = parts[15]
                    hdop_str = parts[16]
                    vdop_raw = parts[17].split('*')[0] if len(parts) > 17 else ''
                    if pdop_str:
                        self.pdop = float(pdop_str)
                    if hdop_str:
                        self.hdop = float(hdop_str)
                    if vdop_raw:
                        self.vdop = float(vdop_raw)
                    self.last_update = time.time()
                except (ValueError, IndexError):
                    pass

        # $GPRMC,HHMMSS,A,lat,N,lon,W,speed_knots,heading,DDMMYY,...
        elif line.startswith('$GPRMC') or line.startswith('$GNRMC'):
            parts = line.split(',')
            if len(parts) >= 9:
                try:
                    if parts[7]:
                        self.rmc_speed_mps = float(parts[7]) * 0.514444
                    if parts[8]:
                        self.rmc_heading = float(parts[8])
                    self.last_update = time.time()
                except (ValueError, IndexError):
                    pass

        # $GPVTG,heading_true,T,heading_mag,M,speed_knots,N,speed_kmh,K,...
        elif line.startswith('$GPVTG') or line.startswith('$GNVTG'):
            parts = line.split(',')
            if len(parts) >= 8:
                try:
                    if parts[1]:
                        self.vtg_heading = float(parts[1])
                    if parts[7]:
                        self.vtg_speed_mps = float(parts[7]) / 3.6  # kmh to m/s
                    self.last_update = time.time()
                except (ValueError, IndexError):
                    pass

    def get_data(self):
        """Return current NMEA-derived data as a dict."""
        age = time.time() - self.last_update if self.last_update else 999
        return {
            "hdop": round(self.hdop, 2),
            "pdop": round(self.pdop, 2),
            "vdop": round(self.vdop, 2),
            "num_sats": self.num_sats,
            "fix_quality": self.fix_quality,
            "gga_alt": round(self.gga_alt, 1),
            "rmc_speed": round(self.rmc_speed_mps, 2),
            "rmc_heading": round(self.rmc_heading, 1),
            "vtg_speed": round(self.vtg_speed_mps, 2),
            "vtg_heading": round(self.vtg_heading, 1),
            "nmea_age": round(age, 1),
            "nmea_valid": age < 5.0,
        }


# =============================================================================
# AT command GPS reader (reads /dev/ttyUSB2)
# =============================================================================

class SIM7600GPS:
    """Real GPS via AT+CGPSINFO on /dev/ttyUSB2."""

    def __init__(self, port=AT_PORT, baudrate=GPS_BAUD):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.last_fix = None
        self.fix_count = 0
        self.no_fix_count = 0

    def open(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            log.info("AT port opened: %s", self.port)

            resp = self._send_at("AT+CGPS=1,1", wait=2.0)
            if "ERROR" in resp and "already" not in resp.lower():
                resp2 = self._send_at("AT+CGPS?", wait=1.0)
                if "+CGPS: 1" in resp2:
                    log.info("GPS engine already enabled")
                else:
                    log.warning("GPS enable response: %s", resp.strip())
            else:
                log.info("GPS engine enabled")
            return True
        except serial.SerialException as e:
            log.error("Failed to open AT port %s: %s", self.port, e)
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("AT port closed")

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
        """
        Read GPS from AT+CGPSINFO.
        Response: +CGPSINFO: lat,N/S,lon,E/W,date,time,alt,speed_knots,course
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
                log.info("Waiting for GPS fix... (%d attempts)", self.no_fix_count)
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
            log.warning("GPS parse error: %s | raw: %s", e, payload)
            self.no_fix_count += 1
            return None

    def get_last_or_current(self):
        fix = self.read()
        return fix if fix else self.last_fix


# =============================================================================
# Earth math
# =============================================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_to(lat1, lon1, lat2, lon2):
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = (math.cos(rlat1) * math.sin(rlat2)
         - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# =============================================================================
# Latency tracker
# =============================================================================

class LatencyTracker:
    """
    Measures WebSocket round-trip time using the protocol-level ping/pong.
    websockets library handles pong automatically; we measure the time.
    """

    def __init__(self):
        self.last_rtt_ms = 0.0
        self.avg_rtt_ms = 0.0
        self.min_rtt_ms = 9999.0
        self.max_rtt_ms = 0.0
        self.samples = 0
        self._pending_ping_time = None

    async def ping(self, ws):
        """Send a WebSocket ping and measure pong latency."""
        try:
            self._pending_ping_time = time.monotonic()
            pong_waiter = await ws.ping()
            await asyncio.wait_for(pong_waiter, timeout=5.0)
            rtt = (time.monotonic() - self._pending_ping_time) * 1000.0

            self.last_rtt_ms = rtt
            self.samples += 1
            if rtt < self.min_rtt_ms:
                self.min_rtt_ms = rtt
            if rtt > self.max_rtt_ms:
                self.max_rtt_ms = rtt
            # Exponential moving average
            if self.samples == 1:
                self.avg_rtt_ms = rtt
            else:
                self.avg_rtt_ms = self.avg_rtt_ms * 0.8 + rtt * 0.2

        except (asyncio.TimeoutError, Exception) as e:
            log.debug("Ping failed: %s", e)
            self.last_rtt_ms = -1

    def get_stats(self):
        return {
            "rtt_ms": round(self.last_rtt_ms, 1),
            "rtt_avg_ms": round(self.avg_rtt_ms, 1),
            "rtt_min_ms": round(self.min_rtt_ms, 1) if self.min_rtt_ms < 9999 else 0,
            "rtt_max_ms": round(self.max_rtt_ms, 1),
            "rtt_samples": self.samples,
        }


# =============================================================================
# Rover
# =============================================================================

class LiveRover:
    """Rover using real GPS + NMEA + CAN. Same telemetry format as test.py."""

    def __init__(self, gps, nmea, can_bridge=None):
        self.gps = gps
        self.nmea = nmea
        self.can_bridge = can_bridge
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

        self.latency = LatencyTracker()

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
            print(f"   (No motor control yet -- command logged)")
            print(f"{'='*70}")
        else:
            print(f"\n   NAVIGATE CMD: {lat:.6f}, {lon:.6f} (no GPS fix yet)")

    def tick(self):
        """Read GPS + NMEA, return telemetry dict."""
        self.count += 1

        # AT command GPS (primary: lat/lon)
        fix = self.gps.get_last_or_current()
        if fix and fix["valid"]:
            self.lat = fix["lat"]
            self.lon = fix["lon"]
            self.has_fix = True

        # NMEA data (HDOP, PDOP, VDOP, sats, better alt/speed/heading)
        nd = self.nmea.get_data() if self.nmea else {}
        nmea_valid = nd.get("nmea_valid", False)

        # Prefer NMEA altitude (from $GPGGA) if available, else AT alt
        if nmea_valid and nd.get("gga_alt", 0) != 0:
            self.alt = nd["gga_alt"]
        elif fix and fix["valid"]:
            self.alt = fix["alt"]

        # Prefer NMEA speed (from $GPRMC or $GPVTG) if available
        if nmea_valid and nd.get("rmc_speed", 0) > 0:
            self.speed = nd["rmc_speed"]
        elif nmea_valid and nd.get("vtg_speed", 0) > 0:
            self.speed = nd["vtg_speed"]
        elif fix and fix["valid"]:
            self.speed = fix["speed"]

        # Prefer NMEA heading (from $GPVTG or $GPRMC) if available
        if nmea_valid and nd.get("vtg_heading", 0) > 0:
            self.heading = nd["vtg_heading"]
        elif nmea_valid and nd.get("rmc_heading", 0) > 0:
            self.heading = nd["rmc_heading"]
        elif fix and fix["valid"]:
            self.heading = fix["heading"]

        # DOP values from NMEA
        hdop = nd.get("hdop", 99.9) if nmea_valid else 99.9
        pdop = nd.get("pdop", 99.9) if nmea_valid else 99.9
        vdop = nd.get("vdop", 99.9) if nmea_valid else 99.9
        num_sats = nd.get("num_sats", 0) if nmea_valid else 0

        # Accuracy estimate: HDOP * 2.5m (typical GPS base accuracy)
        accuracy = round(hdop * 2.5, 1) if hdop < 50 else 0.0

        # IMU data from STM32 via CAN (or placeholder if no CAN)
        if self.can_bridge and self.can_bridge.is_stm32_alive():
            imu_can = self.can_bridge.get_imu_data()
            # Scale to raw-ish int values matching server expectation
            ax = int(imu_can['ax'] * 1000)
            ay = int(imu_can['ay'] * 1000)
            az = int(imu_can['az'] * 1000)
            gx = int(imu_can['gx'] * 1000)
            gy = int(imu_can['gy'] * 1000)
            gz = int(imu_can['gz'] * 1000)
            enc_can = self.can_bridge.get_encoder_data()
            enc_l = enc_can['encL']
            enc_r = enc_can['encR']
            enc_l_vel = enc_can['encLVel']
            enc_r_vel = enc_can['encRVel']
        else:
            # No CAN -- random placeholder
            ax = random.randint(-50, 50)
            ay = random.randint(-50, 50)
            az = 16300 + random.randint(-100, 100)
            gx = random.randint(-5, 5)
            gy = random.randint(-5, 5)
            gz = random.randint(-3, 3)
            enc_l = 0
            enc_r = 0
            enc_l_vel = 0
            enc_r_vel = 0

        # Latency stats
        lat_stats = self.latency.get_stats()

        return {
            "id": ROVER_ID, "name": ROVER_NAME, "type": "robot",
            # GPS
            "lat": self.lat, "lon": self.lon, "alt": round(self.alt, 1),
            "speed": round(self.speed, 2), "heading": round(self.heading, 1),
            "accuracy": accuracy,
            "hdop": hdop, "pdop": pdop, "vdop": vdop,
            "numSats": num_sats,
            # IMU
            "ax": ax, "ay": ay, "az": az,
            "gx": gx, "gy": gy, "gz": gz,
            # Encoders (from CAN or zero)
            "encL": enc_l, "encR": enc_r, "encLVel": enc_l_vel, "encRVel": enc_r_vel,
            # Status
            "battery": self.battery,
            "status": "online",
            # Latency (included in telemetry so GlobalRTS UI can display it)
            "rtt_ms": lat_stats["rtt_ms"],
            "rtt_avg_ms": lat_stats["rtt_avg_ms"],
            # Timestamp for server-side latency measurement
            "sent_at": int(time.time() * 1000),
        }

    async def report_command_status(self):
        if self.ws:
            try:
                await self.ws.send(json.dumps({
                    "type": "rover:command_status",
                    "data": {"id": ROVER_ID, "status": self.nav_status},
                }))
            except Exception:
                pass


# =============================================================================
# WebSocket loop
# =============================================================================

async def run(gps, nmea, use_cellular=False, can_bridge=None):
    rover = LiveRover(gps, nmea, can_bridge=can_bridge)
    net_label = "4G" if use_cellular else "WiFi"

    # Parse server URL for host/port (needed for cellular socket)
    import urllib.parse
    parsed = urllib.parse.urlparse(SERVER)
    ws_host = parsed.hostname
    ws_port = parsed.port or (443 if parsed.scheme == 'wss' else 80)

    while True:
        ws = None
        try:
            print(f"\n Connecting to {SERVER} via {net_label}...")

            if use_cellular:
                sock = create_cellular_socket(ws_host, ws_port)
                if sock is None:
                    print("   Cannot connect via cellular, retrying in 5s...")
                    await asyncio.sleep(5)
                    continue
                # Pass raw connected socket. websockets will do the SSL
                # handshake on it (because URI is wss://). The socket is
                # already bound to wwan0 via SO_BINDTODEVICE so all traffic
                # including the SSL handshake goes through cellular.
                ws = await websockets.connect(
                    SERVER,
                    sock=sock,
                    ping_interval=None,
                    ping_timeout=None,
                )
            else:
                ws = await websockets.connect(
                    SERVER,
                    ping_interval=None,
                    ping_timeout=None,
                )

            rover.ws = ws

            # Identify
            await ws.send(json.dumps({
                "type": "rover:identify",
                "data": {
                    "id": ROVER_ID,
                    "name": ROVER_NAME,
                    "type": "robot",
                },
            }))
            print(" Sent identify")

            ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            ack = json.loads(ack_raw)
            if ack.get("type") != "ack":
                print(f"  Expected ack, got {ack.get('type')}")

            fix_str = (
                f"{rover.lat:.6f}, {rover.lon:.6f}"
                if rover.has_fix
                else "waiting for GPS fix..."
            )
            print(f" Connected! Position: {fix_str}")
            print(f"   Sending REAL GPS via {net_label}...\n")

            # Initial latency measurement
            await rover.latency.ping(ws)
            init_rtt = rover.latency.last_rtt_ms
            if init_rtt > 0:
                print(f"   Initial latency: {init_rtt:.0f}ms\n")

            async def telemetry_loop():
                ping_counter = 0
                while True:
                    data = rover.tick()
                    await ws.send(json.dumps({
                        "type": "rover:telemetry",
                        "data": data,
                    }))
                    await rover.report_command_status()

                    # Measure latency every 10 seconds
                    ping_counter += 1
                    if ping_counter % 10 == 0:
                        await rover.latency.ping(ws)

                    # Print status line
                    lat_stats = rover.latency.get_stats()
                    rtt_str = f"{lat_stats['rtt_ms']:.0f}ms" if lat_stats['rtt_ms'] > 0 else "..."

                    if rover.has_fix:
                        nd = rover.nmea.get_data() if rover.nmea else {}
                        sats = nd.get("num_sats", 0)
                        hdop = nd.get("hdop", 99.9)
                        extra = ""
                        if rover.target_lat is not None:
                            dist = haversine_distance(
                                rover.lat, rover.lon,
                                rover.target_lat, rover.target_lon,
                            )
                            extra = f" tgt:{dist:.0f}m"
                        print(
                            f"\r #{rover.count:>4d} "
                            f"{rover.lat:.6f},{rover.lon:.6f} "
                            f"alt:{rover.alt:.0f}m "
                            f"spd:{rover.speed:.1f}m/s "
                            f"hdg:{rover.heading:.0f} "
                            f"sats:{sats} hdop:{hdop:.1f} "
                            f"rtt:{rtt_str} "
                            f"{net_label}{extra}  ",
                            end="", flush=True,
                        )
                    else:
                        print(
                            f"\r  #{rover.count:>4d} NO FIX "
                            f"({gps.no_fix_count}) "
                            f"rtt:{rtt_str} {net_label}  ",
                            end="", flush=True,
                        )

                    await asyncio.sleep(1.0)

            async def receive_loop():
                async for raw in ws:
                    recv_time = time.time()
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")
                    data = msg.get("data", {})

                    if msg_type == "command":
                        cmd_type = data.get("type", "")
                        payload = data.get("payload", {})
                        cmd_ts = data.get("timestamp", 0)

                        # Command latency: time from browser click to rover receipt
                        cmd_age = ""
                        if cmd_ts > 0:
                            age_ms = (recv_time * 1000) - cmd_ts
                            cmd_age = f" (cmd age: {age_ms:.0f}ms)"

                        if cmd_type == "navigate":
                            t_lat = payload.get("latitude")
                            t_lon = payload.get("longitude")
                            t_alt = payload.get("altitude", 0)
                            if t_lat is not None and t_lon is not None:
                                rover.set_target(t_lat, t_lon, t_alt)
                                log.info("CMD navigate lat=%.6f lon=%.6f%s", t_lat, t_lon, cmd_age)
                                # Forward to STM32 via CAN
                                if rover.can_bridge and rover.has_fix:
                                    brng = bearing_to(rover.lat, rover.lon, t_lat, t_lon)
                                    rover.can_bridge.send_navigate(brng, 1.0)
                                    log.info("CAN TX navigate heading=%.1f speed=1.0", brng)
                                print(f"   Command latency{cmd_age}")
                        elif cmd_type == "stop":
                            print(f"\n STOP command received!{cmd_age}")
                            log.info("CMD stop%s", cmd_age)
                            rover.target_lat = None
                            rover.target_lon = None
                            rover.nav_status = "idle"
                            if rover.can_bridge:
                                rover.can_bridge.send_stop()
                                log.info("CAN TX stop")
                        elif cmd_type == "setSpeed":
                            spd = payload.get("speed", 0)
                            print(f"\n SET SPEED: {spd} m/s{cmd_age}")
                            log.info("CMD setSpeed=%.2f%s", spd, cmd_age)
                            if rover.can_bridge:
                                rover.can_bridge.send_set_speed(spd)
                                log.info("CAN TX setSpeed=%.2f", spd)
                        else:
                            print(f"\n CMD: {cmd_type} | {payload}{cmd_age}")
                            log.info("CMD unknown type=%s payload=%s%s", cmd_type, payload, cmd_age)
                    elif msg_type == "selected":
                        print(f"\n  {ROVER_NAME} selected in GlobalRTS")
                    elif msg_type == "deselected":
                        print(f"\n  {ROVER_NAME} deselected")
                    elif msg_type == "ack":
                        pass
                    else:
                        log.debug("msg: %s %s", msg_type, data)

            await asyncio.gather(telemetry_loop(), receive_loop())

        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.WebSocketException,
        ) as e:
            log.error("WebSocket connection lost: %s", e)
            print(f"\n Connection lost: {e}")
        except asyncio.TimeoutError:
            log.error("WebSocket timeout: no ack from server")
            print("\n No ack from server (timeout)")
        except OSError as e:
            log.error("Network error: %s", e)
            print(f"\n Network error: {e}")

        # Clean up
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        rover.ws = None
        print("   Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Send REAL GPS from SIM7600G-H to GlobalRTS"
    )
    parser.add_argument(
        "--cellular", action="store_true",
        help="Route WebSocket through wwan0 (cellular). WiFi stays for SSH.",
    )
    parser.add_argument(
        "--at-port", default="/dev/ttyUSB2",
        help="AT command port for GPS (default: /dev/ttyUSB2)",
    )
    parser.add_argument(
        "--nmea-port", default="/dev/ttyUSB1",
        help="NMEA port for HDOP/PDOP/sats (default: /dev/ttyUSB1)",
    )
    parser.add_argument(
        "--no-nmea", action="store_true",
        help="Skip NMEA port (no HDOP/PDOP data, only AT+CGPSINFO)",
    )
    parser.add_argument(
        "--rover-id", default="rover-001",
        help="Rover ID (default: rover-001)",
    )
    parser.add_argument(
        "--rover-name", default="RasPi Rover",
        help="Rover display name",
    )
    parser.add_argument(
        "--server", default="wss://miraeopus.com/rover",
        help="WebSocket server URL",
    )
    parser.add_argument(
        "--debug", "-d", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--can", action="store_true",
        help="Enable CAN bus bridge to STM32 (requires MCP2515 + can0 interface)",
    )
    parser.add_argument(
        "--can-interface", default="can0",
        help="CAN interface name (default: can0)",
    )
    args = parser.parse_args()

    global ROVER_ID, ROVER_NAME, SERVER
    ROVER_ID = args.rover_id
    ROVER_NAME = args.rover_name
    SERVER = args.server

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    gps = SIM7600GPS(port=args.at_port, baudrate=GPS_BAUD)
    nmea = None if args.no_nmea else NMEAReader(port=args.nmea_port, baudrate=GPS_BAUD)
    can_br = None

    def cleanup(sig=None, frame=None):
        print("\nShutting down...")
        log.info("Shutdown signal received")
        gps.close()
        if nmea:
            nmea.close()
        if can_br:
            can_br.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    net_mode = "CELLULAR (wwan0)" if args.cellular else "WIFI (wlan0)"
    can_mode = args.can_interface if args.can else "DISABLED"

    print(f"{'='*60}")
    print(f"  GlobalRTS Rover -- LIVE GPS")
    print(f"  Server  : {SERVER}")
    print(f"  Rover   : {ROVER_ID} ({ROVER_NAME})")
    print(f"  AT Port : {args.at_port}")
    print(f"  NMEA    : {args.nmea_port if not args.no_nmea else 'DISABLED'}")
    print(f"  Network : {net_mode}")
    print(f"  CAN Bus : {can_mode}")
    print(f"  Logs    : {LOG_DIR}/")
    print(f"{'='*60}\n")

    log.info("="*60)
    log.info("live_gps.py starting")
    log.info("Server=%s Rover=%s Network=%s CAN=%s", SERVER, ROVER_ID, net_mode, can_mode)
    log.info("="*60)

    # If cellular, verify wwan0 has IP and we have root
    if args.cellular:
        if os.geteuid() != 0:
            print("  ERROR: --cellular requires root for SO_BINDTODEVICE.")
            print("  Run with: sudo python3 live_gps.py --cellular")
            sys.exit(1)
        ip = get_interface_ip(CELLULAR_IFACE)
        if ip:
            print(f"  Cellular IP: {ip} ({CELLULAR_IFACE})")
            wifi_ip = get_interface_ip("wlan0")
            if wifi_ip:
                print(f"  WiFi IP:     {wifi_ip} (wlan0) -- SSH available here")
        else:
            print(f"  ERROR: {CELLULAR_IFACE} has no IP address.")
            print(f"  Run first: sudo bash cellular_connect.sh")
            sys.exit(1)

    # Open GPS
    if not gps.open():
        print(f"Failed to open GPS on {args.at_port}")
        print("Check: ls /dev/ttyUSB*")
        print("Check: sudo systemctl stop ModemManager")
        sys.exit(1)

    # Open NMEA
    if nmea:
        if nmea.open():
            print("NMEA reader active -- will get HDOP/PDOP/sats")
        else:
            print("NMEA reader failed -- continuing without HDOP/PDOP")
            nmea = None

    # Open CAN bus
    if args.can:
        if CANBridge is None:
            print("CAN bridge not available (python-can not installed)")
            print("Run: pip3 install python-can")
        else:
            setup_can_logging(LOG_DIR)
            can_br = CANBridge(interface=args.can_interface)
            if can_br.open():
                print(f"CAN bus active on {args.can_interface} -- STM32 bridge enabled")
                log.info("CAN bus opened on %s", args.can_interface)
                # Send initial ping to STM32
                can_br.send_ping()
            else:
                print("CAN bus failed -- continuing without STM32 data")
                log.warning("CAN bus failed to open")
                can_br = None

    # Wait for initial fix
    print("Waiting for GPS fix (up to 60s, need clear sky)...")
    for i in range(60):
        fix = gps.read()
        if fix and fix["valid"]:
            nd = nmea.get_data() if nmea else {}
            print(f"\n  GPS FIX: {fix['lat']:.6f}, {fix['lon']:.6f}")
            print(f"  Alt: {fix['alt']:.1f}m  "
                  f"Speed: {fix['speed']:.1f}m/s  "
                  f"Heading: {fix['heading']:.1f}deg")
            if nd.get("nmea_valid"):
                print(f"  HDOP: {nd['hdop']}  PDOP: {nd['pdop']}  "
                      f"VDOP: {nd['vdop']}  Sats: {nd['num_sats']}")
            break
        dots = "." * ((i % 3) + 1)
        print(f"  Searching{dots:<3s} ({i+1}/60)  ", end="\r")
        time.sleep(1)
    else:
        print("\n  No GPS fix yet -- starting anyway (will get fix outdoors)")

    # Run
    print(f"\nStarting WebSocket telemetry via {net_mode}...\n")
    log.info("Starting WebSocket loop")
    try:
        asyncio.run(run(gps, nmea, use_cellular=args.cellular, can_bridge=can_br))
    except KeyboardInterrupt:
        pass
    finally:
        gps.close()
        if nmea:
            nmea.close()
        if can_br:
            can_br.close()
        log.info("live_gps.py shut down")
        print("Done.")


if __name__ == "__main__":
    main()
