#!/usr/bin/env python3
"""
test_cellular.py — Run the working test.py rover over cellular instead of WiFi.

This is the simplest integration: it brings up the SIM7600G-H cellular connection
first, then runs the exact same WebSocket logic from test.py through it.

Usage:
    sudo python3 test_cellular.py                     # Default APN (super)
    sudo python3 test_cellular.py --apn broadband     # AT&T
    sudo python3 test_cellular.py --wifi-fallback      # Keep WiFi as backup

You need sudo because pppd requires root to create network interfaces.
"""

import asyncio
import json
import math
import random
import time
import sys
import signal
import argparse

# Import our cellular manager
from cellular import CellularManager

try:
    import websockets
except ImportError:
    print("Install websockets first:  pip install websockets")
    exit(1)

# ── Config ──────────────────────────────────────────────────────────
SERVER     = "wss://miraeopus.com/rover"
ROVER_ID   = "rover-001"
ROVER_NAME = "RasPi Rover"

# Start position — your actual GPS will replace this once SIM7600 GPS is working
START_LAT = 33.9192    # Brea, CA area
START_LON = -117.8903
START_ALT = 52.0

MOVE_SPEED_MPS = 27.78  # ~100 km/h for testing
# ────────────────────────────────────────────────────────────────────


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


def move_toward(lat, lon, target_lat, target_lon, distance_m):
    R = 6371000
    brng = math.radians(bearing_to(lat, lon, target_lat, target_lon))
    rlat = math.radians(lat)
    rlon = math.radians(lon)
    d = distance_m / R
    new_lat = math.asin(math.sin(rlat)*math.cos(d) + math.cos(rlat)*math.sin(d)*math.cos(brng))
    new_lon = rlon + math.atan2(math.sin(brng)*math.sin(d)*math.cos(rlat),
                                 math.cos(d) - math.sin(rlat)*math.sin(new_lat))
    return math.degrees(new_lat), math.degrees(new_lon)


class SimulatedRover:
    """Same SimulatedRover from test.py, untouched."""

    def __init__(self):
        self.lat = START_LAT
        self.lon = START_LON
        self.alt = START_ALT
        self.heading = 0.0
        self.speed = 0.0
        self.enc_l = 0
        self.enc_r = 0
        self.battery = 95
        self.count = 0
        self.target_lat = None
        self.target_lon = None
        self.target_alt = 0.0
        self.nav_status = "idle"
        self.ws = None

    def set_target(self, lat, lon, alt=0.0):
        self.target_lat = lat
        self.target_lon = lon
        self.target_alt = alt
        self.nav_status = "moving"
        dist = haversine_distance(self.lat, self.lon, lat, lon)
        brng = bearing_to(self.lat, self.lon, lat, lon)
        print(f"\n{'='*70}")
        print(f"   Received Movement Command")
        print(f"   Target:   Lat: {lat:.6f}  Lon: {lon:.6f}  Alt: {alt:.1f}m")
        print(f"   Distance: {dist:.1f}m ({dist/1000:.2f}km)")
        print(f"   Bearing:  {brng:.1f}deg")
        print(f"   ETA:      {dist/MOVE_SPEED_MPS:.1f}s at {MOVE_SPEED_MPS*3.6:.0f} km/h")
        print(f"{'='*70}")

    def tick(self, dt=1.0):
        self.count += 1
        if self.nav_status == "moving" and self.target_lat is not None:
            dist = haversine_distance(self.lat, self.lon, self.target_lat, self.target_lon)
            if dist < 2.0:
                self.lat = self.target_lat
                self.lon = self.target_lon
                self.speed = 0.0
                self.nav_status = "arrived"
                self.target_lat = None
                self.target_lon = None
                print(f"\n   Arrived at destination!")
            else:
                self.heading = bearing_to(self.lat, self.lon, self.target_lat, self.target_lon)
                step = min(MOVE_SPEED_MPS * dt, dist)
                self.speed = step / dt
                self.lat, self.lon = move_toward(
                    self.lat, self.lon, self.target_lat, self.target_lon, step
                )
                ticks = int(step * 10)
                self.enc_l += ticks + random.randint(-1, 1)
                self.enc_r += ticks + random.randint(-1, 1)
        else:
            self.speed = 0.0

        if self.speed > 0:
            ax, ay, az = random.randint(-300, 300), random.randint(-300, 300), 16000 + random.randint(0, 500)
            gx, gy, gz = random.randint(-30, 30), random.randint(-30, 30), random.randint(-20, 20)
        else:
            ax, ay, az = random.randint(-50, 50), random.randint(-50, 50), 16300 + random.randint(-100, 100)
            gx, gy, gz = random.randint(-5, 5), random.randint(-5, 5), random.randint(-3, 3)

        enc_vel_l = int(self.speed * 10) + random.randint(-2, 2) if self.speed > 0 else 0
        enc_vel_r = int(self.speed * 10) + random.randint(-2, 2) if self.speed > 0 else 0

        return {
            "id": ROVER_ID, "name": ROVER_NAME, "type": "robot",
            "lat": self.lat, "lon": self.lon, "alt": self.alt,
            "speed": round(self.speed, 2), "heading": round(self.heading, 1),
            "accuracy": 2.5, "hdop": 1.1, "pdop": 1.5, "vdop": 1.3,
            "ax": ax, "ay": ay, "az": az, "gx": gx, "gy": gy, "gz": gz,
            "encL": self.enc_l, "encR": self.enc_r,
            "encLVel": enc_vel_l, "encRVel": enc_vel_r,
            "battery": self.battery, "status": "online"
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


async def run(cell: CellularManager):
    """Same WebSocket loop as test.py — now running over cellular."""
    rover = SimulatedRover()

    while True:
        try:
            # Check cellular is still up before connecting
            if not cell.is_connected():
                print("  Cellular connection lost, waiting for reconnect...")
                await asyncio.sleep(5)
                continue

            sig_pct, sig_dbm, net_type = cell.get_signal()
            print(f"\n Connecting to {SERVER} via {net_type} ({sig_pct}%, {sig_dbm}dBm)...")

            async with websockets.connect(SERVER, ping_interval=20, ping_timeout=10) as ws:
                rover.ws = ws

                await ws.send(json.dumps({
                    "type": "rover:identify",
                    "data": {"id": ROVER_ID, "name": ROVER_NAME, "type": "robot"}
                }))
                print(f" Sent identify")

                ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                ack = json.loads(ack_raw)
                if ack.get("type") != "ack":
                    print(f"  Expected ack, got {ack.get('type')}")

                print(f" Connected via CELLULAR! Rover at {rover.lat:.6f}, {rover.lon:.6f}")
                print(f"   Waiting for commands from miraeopus.com ...\n")

                async def telemetry_loop():
                    while True:
                        data = rover.tick(dt=1.0)
                        await ws.send(json.dumps({"type": "rover:telemetry", "data": data}))
                        await rover.report_command_status()

                        if rover.nav_status == "moving":
                            dist = haversine_distance(
                                rover.lat, rover.lon,
                                rover.target_lat, rover.target_lon
                            )
                            print(f"\r #{rover.count:>4d} | {rover.lat:.6f}, {rover.lon:.6f} | "
                                  f"H:{rover.heading:5.1f}deg | {rover.speed:.1f} m/s | "
                                  f"dist:{dist:.0f}m | 4G  ",
                                  end="", flush=True)
                        else:
                            print(f"\r  #{rover.count:>4d} | {rover.lat:.6f}, {rover.lon:.6f} | "
                                  f"idle | 4G  ",
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
                                print(f"\n Received STOP command!")
                                rover.target_lat = None
                                rover.target_lon = None
                                rover.nav_status = "idle"
                                rover.speed = 0.0
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
    parser = argparse.ArgumentParser(description='GlobalRTS Rover over Cellular')
    parser.add_argument('--apn', default='super',
                        help='Carrier APN (default: super for Mint Mobile)')
    parser.add_argument('--at-port', default='/dev/ttyUSB2',
                        help='AT command port (default: /dev/ttyUSB2)')
    parser.add_argument('--ppp-port', default='/dev/ttyUSB3',
                        help='PPP/modem port (default: /dev/ttyUSB3)')
    parser.add_argument('--rover-id', default='rover-001',
                        help='Rover ID')
    parser.add_argument('--rover-name', default='RasPi Rover',
                        help='Rover display name')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    args = parser.parse_args()

    global ROVER_ID, ROVER_NAME
    ROVER_ID = args.rover_id
    ROVER_NAME = args.rover_name

    if args.debug:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Step 1: Initialize and connect cellular ──
    cell = CellularManager(
        at_port=args.at_port,
        ppp_port=args.ppp_port,
        apn=args.apn,
    )

    def cleanup(sig=None, frame=None):
        print("\nShutting down...")
        cell.cleanup()
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(f"{'='*60}")
    print(f"  GlobalRTS Rover — CELLULAR MODE")
    print(f"  Server : {SERVER}")
    print(f"  Rover  : {ROVER_ID} ({ROVER_NAME})")
    print(f"  APN    : {args.apn}")
    print(f"  AT Port: {args.at_port}")
    print(f"{'='*60}\n")

    if not cell.initialize():
        print(f"\nModem init failed: {cell.status.error}")
        print("Check that the SIM7600G-H is powered and USB is connected.")
        print("Run: ls /dev/ttyUSB*  to verify serial ports exist.")
        sys.exit(1)

    if not cell.connect_direct():
        print("\nFailed to establish cellular data. Check APN and SIM card.")
        cell.cleanup()
        sys.exit(1)

    cell.print_status()

    # Start auto-reconnect monitor in background
    cell.start_monitor()

    # ── Step 2: Run the rover over cellular ──
    print("Cellular is UP. Starting rover...\n")

    try:
        asyncio.run(run(cell))
    except KeyboardInterrupt:
        pass
    finally:
        cell.cleanup()
        print("Done.")


if __name__ == "__main__":
    main()
