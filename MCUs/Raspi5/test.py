#!/usr/bin/env python3
"""
test.py — Simulated rover that responds to GlobalRTS commands.

Sits at a fixed position in San Francisco until you send it a move command
from miraeopus.com. Then it drives toward the target at ~100 km/h with
realistic heading, speed, distance, and encoder updates.

Select/deselect the rover in the UI to see notifications here.
Right-click a location while the rover is selected to send a navigate command.

Usage:
    pip install websockets
    python3 test.py
"""

import asyncio
import json
import math
import random
import time

try:
    import websockets
except ImportError:
    print("Install websockets first:  pip install websockets")
    exit(1)

# ── Config ──────────────────────────────────────────────────────────
SERVER     = "wss://miraeopus.com/rover"
ROVER_ID   = "test-rover"
ROVER_NAME = "SF Test Rover"

# San Francisco — Golden Gate Park
START_LAT = 37.7694
START_LON = -122.4862
START_ALT = 52.0

# Movement speed: ~100 km/h = 27.78 m/s
MOVE_SPEED_MPS = 27.78
# ────────────────────────────────────────────────────────────────────

# Earth math helpers
def haversine_distance(lat1, lon1, lat2, lon2):
    """Distance in meters between two lat/lon points."""
    R = 6371000
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(rlat1)*math.cos(rlat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def bearing_to(lat1, lon1, lat2, lon2):
    """Bearing in degrees from point 1 to point 2."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1)*math.sin(rlat2) - math.sin(rlat1)*math.cos(rlat2)*math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def move_toward(lat, lon, target_lat, target_lon, distance_m):
    """Move lat/lon toward target by distance_m meters. Returns new lat, lon."""
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
    def __init__(self):
        self.lat = START_LAT
        self.lon = START_LON
        self.alt = START_ALT
        self.heading = 0.0
        self.speed = 0.0        # m/s
        self.enc_l = 0
        self.enc_r = 0
        self.battery = 95
        self.count = 0

        # Navigation target (None = idle)
        self.target_lat = None
        self.target_lon = None
        self.target_alt = 0.0
        self.nav_status = "idle"  # idle | moving | arrived

        self.ws = None

    def set_target(self, lat, lon, alt=0.0):
        """Set a new navigation target."""
        self.target_lat = lat
        self.target_lon = lon
        self.target_alt = alt
        self.nav_status = "moving"
        dist = haversine_distance(self.lat, self.lon, lat, lon)
        brng = bearing_to(self.lat, self.lon, lat, lon)
        print(f"\n{'='*70}")
        print(f"   Received Movement Command")
        print(f"   Target:   Latitude: {lat:.6f}  Longitude: {lon:.6f}  Alt: {alt:.1f}m")
        print(f"   Distance: {dist:.1f}m ({dist/1000:.2f}km)")
        print(f"   Bearing:  {brng:.1f}°")
        print(f"   ETA:      {dist/MOVE_SPEED_MPS:.1f}s at {MOVE_SPEED_MPS*3.6:.0f} km/h")
        print(f"{'='*70}")

    def tick(self, dt=1.0):
        """Advance simulation by dt seconds. Returns telemetry dict."""
        self.count += 1

        if self.nav_status == "moving" and self.target_lat is not None:
            dist = haversine_distance(self.lat, self.lon, self.target_lat, self.target_lon)

            if dist < 2.0:
                # Arrived
                self.lat = self.target_lat
                self.lon = self.target_lon
                self.speed = 0.0
                self.nav_status = "arrived"
                self.target_lat = None
                self.target_lon = None
                print(f"\n{'='*70}")
                print(f"   Arrived at destination!")
                print(f"   Position: {self.lat:.6f}, {self.lon:.6f}")
                print(f"{'='*70}")
            else:
                # Move toward target
                self.heading = bearing_to(self.lat, self.lon, self.target_lat, self.target_lon)
                step = min(MOVE_SPEED_MPS * dt, dist)
                self.speed = step / dt
                self.lat, self.lon = move_toward(
                    self.lat, self.lon, self.target_lat, self.target_lon, step
                )
                # Encoders: ~ticks per meter * distance
                ticks = int(step * 10)
                self.enc_l += ticks + random.randint(-1, 1)
                self.enc_r += ticks + random.randint(-1, 1)
        else:
            # Idle — stationary
            self.speed = 0.0

        # IMU: always has some noise (real sensor behavior)
        # Accel: gravity on Z (~16384 for ±2g 16-bit), small vibration on X/Y
        # Gyro: near-zero when straight, small noise
        if self.speed > 0:
            ax = random.randint(-300, 300)
            ay = random.randint(-300, 300)
            az = 16000 + random.randint(0, 500)
            gx = random.randint(-30, 30)
            gy = random.randint(-30, 30)
            gz = random.randint(-20, 20)
        else:
            ax = random.randint(-50, 50)
            ay = random.randint(-50, 50)
            az = 16300 + random.randint(-100, 100)
            gx = random.randint(-5, 5)
            gy = random.randint(-5, 5)
            gz = random.randint(-3, 3)

        enc_vel_l = int(self.speed * 10) + random.randint(-2, 2) if self.speed > 0 else 0
        enc_vel_r = int(self.speed * 10) + random.randint(-2, 2) if self.speed > 0 else 0

        return {
            "id": ROVER_ID,
            "name": ROVER_NAME,
            "type": "robot",
            "lat": self.lat,
            "lon": self.lon,
            "alt": self.alt,
            "speed": round(self.speed, 2),
            "heading": round(self.heading, 1),
            "accuracy": 2.5,
            "hdop": 1.1,
            "pdop": 1.5,
            "vdop": 1.3,
            "ax": ax, "ay": ay, "az": az,
            "gx": gx, "gy": gy, "gz": gz,
            "encL": self.enc_l,
            "encR": self.enc_r,
            "encLVel": enc_vel_l,
            "encRVel": enc_vel_r,
            "battery": self.battery,
            "status": "online"
        }

    async def report_command_status(self):
        """Report nav status to server for /api/health tracking."""
        if self.ws:
            try:
                await self.ws.send(json.dumps({
                    "type": "rover:command_status",
                    "data": { "id": ROVER_ID, "status": self.nav_status }
                }))
            except Exception:
                pass


async def run():
    rover = SimulatedRover()

    while True:
        try:
            print(f" Connecting to {SERVER} ...")
            async with websockets.connect(SERVER, ping_interval=20, ping_timeout=10) as ws:
                rover.ws = ws

                # ── Step 1: Identify ────────────────────────────────
                await ws.send(json.dumps({
                    "type": "rover:identify",
                    "data": { "id": ROVER_ID, "name": ROVER_NAME, "type": "robot" }
                }))
                print(f" Sent identify")

                # ── Step 2: Wait for ack ────────────────────────────
                ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                ack = json.loads(ack_raw)
                if ack.get("type") != "ack":
                    print(f"  Expected ack, got {ack.get('type')}")

                print(f" Connected! Rover idle at {rover.lat:.6f}, {rover.lon:.6f}")
                print(f"   Waiting for commands from miraeopus.com ...\n")

                # ── Step 3: Concurrent send/receive ─────────────────
                async def telemetry_loop():
                    while True:
                        data = rover.tick(dt=1.0)
                        await ws.send(json.dumps({"type": "rover:telemetry", "data": data}))

                        # Report command status changes
                        await rover.report_command_status()

                        # Status line
                        if rover.nav_status == "moving":
                            dist = haversine_distance(
                                rover.lat, rover.lon,
                                rover.target_lat, rover.target_lon
                            )
                            print(f"\r #{rover.count:>4d} | {rover.lat:.6f}, {rover.lon:.6f} | "
                                  f"H:{rover.heading:5.1f}° | {rover.speed:.1f} m/s | "
                                  f"dist:{dist:.0f}m | enc:{rover.enc_l}/{rover.enc_r}  ",
                                  end="", flush=True)
                        else:
                            print(f"\r  #{rover.count:>4d} | {rover.lat:.6f}, {rover.lon:.6f} | "
                                  f"idle | enc:{rover.enc_l}/{rover.enc_r}  ",
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
                            pass  # already handled

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


if __name__ == "__main__":
    print(f"{'='*60}")
    print(f"  GlobalRTS Test Rover")
    print(f"  Server : {SERVER}")
    print(f"  Rover  : {ROVER_ID} ({ROVER_NAME})")
    print(f"  Start  : {START_LAT}, {START_LON}")
    print(f"  Speed  : {MOVE_SPEED_MPS*3.6:.0f} km/h when moving")
    print(f"  Ctrl+C to stop")
    print(f"{'='*60}\n")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n Stopped.")
