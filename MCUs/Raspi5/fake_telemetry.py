#!/usr/bin/env python3
"""
fake_telemetry.py — Send simulated rover telemetry to miraeopus.com via WebSocket.

Run this from any machine with internet access to verify the full pipeline:
  Pi/laptop -> WebSocket -> Fly.io server -> WebSocket -> Browser (miraeopus.com)

Then open miraeopus.com, click the rover dot in San Francisco, and watch
the info panel update live (GPS, IMU, Encoders, Battery, etc).

Usage:
    pip install websockets
    python3 fake_telemetry.py

That's it. No args needed. It connects to wss://miraeopus.com/rover,
identifies as "test-rover", and streams fake telemetry once per second.
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
SERVER   = "wss://miraeopus.com/rover"
ROVER_ID = "test-rover"
ROVER_NAME = "SF Test Rover"

# San Francisco — Golden Gate Park
START_LAT = 37.7694
START_LON = -122.4862
# ────────────────────────────────────────────────────────────────────

async def run():
    lat = START_LAT
    lon = START_LON
    heading = 45.0
    enc_l = 0
    enc_r = 0
    count = 0

    while True:
        try:
            print(f"🔌 Connecting to {SERVER} ...")
            async with websockets.connect(SERVER, ping_interval=20, ping_timeout=10) as ws:

                # ── Step 1: Identify ────────────────────────────────
                identify = json.dumps({
                    "type": "rover:identify",
                    "data": {
                        "id": ROVER_ID,
                        "name": ROVER_NAME,
                        "type": "robot"
                    }
                })
                await ws.send(identify)
                print(f"📤 Sent identify")

                # ── Step 2: Wait for ack ────────────────────────────
                ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                ack = json.loads(ack_raw)
                print(f"📥 Server says: {ack}")

                if ack.get("type") != "ack":
                    print(f"⚠️  Expected ack, got {ack.get('type')}. Continuing anyway.")

                print(f"✅ Connected! Streaming telemetry once per second...\n")

                # ── Step 3: Telemetry loop ──────────────────────────
                while True:
                    # Simulate slow random walk around SF
                    lat += (random.random() - 0.5) * 0.00008
                    lon += (random.random() - 0.5) * 0.00008
                    heading = (heading + (random.random() - 0.5) * 10) % 360
                    speed = 0.3 + random.random() * 0.7
                    enc_l += random.randint(5, 15)
                    enc_r += random.randint(5, 15)
                    count += 1

                    msg = json.dumps({
                        "type": "rover:telemetry",
                        "data": {
                            "id": ROVER_ID,
                            "name": ROVER_NAME,
                            "type": "robot",
                            # GPS
                            "lat": lat,
                            "lon": lon,
                            "alt": 52.0 + random.random() * 2,
                            "speed": round(speed, 2),
                            "heading": round(heading, 1),
                            "accuracy": round(2.0 + random.random(), 1),
                            "altAccuracy": round(3.0 + random.random() * 2, 1),
                            "speedAccuracy": round(0.1 + random.random() * 0.3, 2),
                            "headingAccuracy": round(1.0 + random.random() * 2, 1),
                            "pdop": round(1.0 + random.random(), 1),
                            "hdop": round(0.8 + random.random() * 0.5, 1),
                            "vdop": round(1.2 + random.random() * 0.6, 1),
                            # IMU  (raw 16-bit-ish values)
                            "ax": random.randint(-500, 500),
                            "ay": random.randint(-500, 500),
                            "az": 16000 + random.randint(0, 500),
                            "gx": random.randint(-50, 50),
                            "gy": random.randint(-50, 50),
                            "gz": random.randint(-50, 50),
                            # Encoders
                            "encL": enc_l,
                            "encR": enc_r,
                            "encLVel": random.randint(40, 110),
                            "encRVel": random.randint(40, 110),
                            # Status
                            "battery": max(10, 85 - count // 60),  # slowly drains
                            "status": "online"
                        }
                    })

                    await ws.send(msg)
                    print(f"\r📡 #{count:>4d} | {lat:.6f}, {lon:.6f} | "
                          f"H:{heading:5.1f}° | spd:{speed:.2f} m/s | "
                          f"enc:{enc_l}/{enc_r}  ", end="", flush=True)

                    await asyncio.sleep(1.0)

        except (websockets.exceptions.ConnectionClosed, 
                websockets.exceptions.WebSocketException) as e:
            print(f"\n❌ Connection lost: {e}")
        except asyncio.TimeoutError:
            print(f"\n❌ No ack from server (timeout)")
        except OSError as e:
            print(f"\n❌ Network error: {e}")

        print(f"   Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


if __name__ == "__main__":
    print(f"🤖 Fake Telemetry Sender")
    print(f"   Server : {SERVER}")
    print(f"   Rover  : {ROVER_ID} ({ROVER_NAME})")
    print(f"   Location: San Francisco ({START_LAT}, {START_LON})")
    print(f"   Ctrl+C to stop\n")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
