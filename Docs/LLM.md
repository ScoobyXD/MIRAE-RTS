# What We Are Doing
We are creating a system where my wheeled rover has a Raspberry Pi 5 as the main computer with a SIM7600G-H 4G LTE cellular modem that sends GPS data (Latitude, Longitude, Accuracy, Altitude, Speed, Heading, etc.) and telemetry every second while it is moving around in the environment. The Raspberry Pi communicates with an STM32L476RG microcontroller via UART which handles real-time motor control loops (50-100 Hz) using encoder feedback and LSM6DS3 IMU data for heading stabilization. The Pi handles strategic navigation (GPS → waypoint calculation), while the STM32 handles tactical motor control (heading → motor PWM). All data is sent to the main server at miraeopus.com. From my laptop/browser I will see the live data from my robot with GlobalRTS. I can then use my laptop to click on certain areas on GlobalRTS's Google Earth-like UI to command the robot to go to certain coordinates. The system also supports video streaming from a USB camera and audio from a USB microphone for future telepresence features.

## Laptop/Browser
Basically a way to open GlobalRTS, which runs in a browser on the internet. Connects to the Fly.io server via WebSocket to view robot telemetry and send commands in real-time.

## GlobalRTS
GlobalRTS is the UI interface to see the live location and data from robot. I can also use it to send commands to the robot like telling it where to go. This is done by giving GlobalRTS a Google Earth view so I can click on the rover from the map and then click on a location to send it to. Possible since the Google Earth map is already divided into Latitude/Longitude coordinates, so both the laptop, GlobalRTS, and robot can agree on coordinates and where things are. 

Important to note the GlobalRTS is also a way for me to check the news, Oura Ring sleep calendar, and has RTS controls like left click+drag to select units (robots), left click on a unit to select it, once selected right click on a location to send it there and displays the location selected, also control panel that can show/hide the different panels and UI elements.

## Miraeopus.com
I bought and own the domain name Miraeopus.com. This is where GlobalRTS is hosted and serves as the connector between my laptop/browser and rover. The server uses **WebSocket as the primary protocol** for both browser and rover connections, with HTTP as a fallback for rovers when WebSocket fails.

## Robot Hardware
The rover consists of:
- **Raspberry Pi 5**: Main computer running Python, handles GPS, cellular, navigation logic, video streaming
- **STM32L476RG**: Real-time motor control with FreeRTOS, runs PID loops, reads encoders and IMU
- **Waveshare SIM7600G-H 4G HAT**: 4G LTE cellular modem (10 Mbps) + GPS/GNSS receiver (~2.5m accuracy)
- **LSM6DS3 IMU**: 6-axis accelerometer + gyroscope for heading stabilization (connected to STM32)
- **Motor encoders**: Quadrature encoders on both motors for closed-loop speed control
- **Motor driver**: H-bridge driver for 12V motors
- **USB Camera**: 1080p video for streaming (future)
- **USB Microphone**: Audio input (future)
- **12V Battery**: Powers motors directly, 5V buck converters for Pi + STM32

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 5                            │
│                   (Strategic Layer - 1-10 Hz)                │
│                                                              │
│  Main Python Application (main.py):                         │
│  ├─ GPS positioning (from SIM7600 HAT via AT commands)      │
│  ├─ Navigation logic (GPS → waypoint → target heading)      │
│  ├─ WebSocket connection to miraeopus.com (PRIMARY)         │
│  ├─ HTTP POST/GET fallback if WebSocket fails               │
│  ├─ UART commands to STM32 (target heading/speed)           │
│  ├─ Video streaming (USB camera → WebRTC) [future]          │
│  └─ Audio capture (USB microphone) [future]                 │
│                                                              │
│  Python Files:                                              │
│  ├─ rover_client.py  - WebSocket/HTTP communication client  │
│  ├─ main.py          - Full application with GPS, STM32     │
│  └─ requirements.txt - websockets, aiohttp, pyserial        │
│                                                              │
│  Connected Hardware:                                        │
│  ├─ SIM7600G-H HAT (/dev/ttyUSB2) ──> 4G LTE + GPS         │
│  ├─ USB Camera ──> Video                                    │
│  ├─ USB Microphone ──> Audio                                │
│  └─ UART (/dev/ttyAMA0, GPIO 14/15) ──> STM32              │
└─────────────────────────────┬───────────────────────────────┘
                              │ UART (115200 baud)
                              │ TX: Commands (heading, speed)
                              │ RX: Telemetry (encoders, IMU)
┌─────────────────────────────▼───────────────────────────────┐
│                   STM32L476RG + FreeRTOS                     │
│                   (Tactical Layer - 50-100 Hz)               │
│                                                              │
│  Task 1: Motor Control Loop (100 Hz)                        │
│  ├─ Read encoders (left/right wheel speeds)                 │
│  ├─ Read IMU (gyroscope for heading)                        │
│  ├─ PID controller (heading + speed)                        │
│  └─ Output PWM to motor driver                              │
│                                                              │
│  Task 2: UART Communication (10 Hz)                         │
│  ├─ Receive commands from Pi (target heading/speed)         │
│  ├─ Send telemetry to Pi (encoders, IMU, status)            │
│  └─ Buffer sensor data                                      │
│                                                              │
│  Task 3: Safety Monitor (100 Hz)                            │
│  └─ Emergency stop if Pi stops responding (5s timeout)      │
│                                                              │
└───────────┬─────────────────┬───────────────────────────────┘
            │                 │
    ┌───────▼────────┐   ┌────▼─────────┐
    │  Motor Driver  │   │  LSM6DS3 IMU │
    │  (H-Bridge)    │   │  (I2C)       │
    └───────┬────────┘   └──────────────┘
            │
    ┌───────▼────────┐
    │  12V Motors    │
    │  (with encoders)│
    └────────────────┘

                    4G Cellular (LTE Cat-1)
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Fly.io Server (miraeopus.com)                   │
│              IMPORTANT: Must run as SINGLE INSTANCE          │
│              (fly scale count 1) - state is in-memory        │
│                                                              │
│  Node.js Server (server.js / server_enhanced.js):           │
│                                                              │
│  WebSocket Endpoints:                                       │
│  ├─ ws://miraeopus.com/       ← Browser connections         │
│  └─ ws://miraeopus.com/rover  ← Rover connections (NEW!)    │
│                                                              │
│  HTTP Endpoints (fallback):                                 │
│  ├─ POST /api/telemetry       ← Rover sends telemetry       │
│  ├─ GET  /api/commands/:id    ← Rover polls for commands    │
│  ├─ POST /api/command         ← Browser sends command       │
│  ├─ GET  /api/rovers          ← List all rovers             │
│  └─ GET  /api/health          ← Health check + stats        │
│                                                              │
│  In-Memory State:                                           │
│  ├─ rovers: Map<roverId, telemetryData>                     │
│  ├─ roverClients: Map<roverId, WebSocket>                   │
│  ├─ browserClients: Set<WebSocket>                          │
│  └─ pendingCommands: Map<roverId, Command[]>                │
└─────────────────────────────────────────────────────────────┘
                            ▲
                    WebSocket (wss://)
                            │
┌─────────────────────────────────────────────────────────────┐
│              GlobalRTS UI (Browser)                          │
│                                                              │
│  ├─ Google Maps / Earth view                                │
│  ├─ Robot position marker (updates real-time via WebSocket) │
│  ├─ Click map → send waypoint command                       │
│  ├─ Telemetry display (speed, heading, battery, etc.)       │
│  ├─ Connection mode indicator (WebSocket vs HTTP)           │
│  └─ Video stream view (WebRTC) [future]                     │
└─────────────────────────────────────────────────────────────┘
```

## Communication Architecture: WebSocket-First

### Why WebSocket over HTTP Polling?

| Aspect | WebSocket (Primary) | HTTP Polling (Fallback) |
|--------|---------------------|-------------------------|
| Command latency | ~50-100ms (cellular only) | ~1-2 seconds (poll interval) |
| Connection overhead | 1 handshake, then ~6 bytes/frame | ~500 bytes headers per request |
| Server push | Instant | Must wait for next poll |
| Connection state | Server knows immediately when rover disconnects | 10s timeout to detect |
| Bandwidth | Lower (no repeated headers) | Higher (HTTP overhead each request) |

### Why Not UDP?

The Pi is behind cellular NAT. UDP would require:
- STUN/TURN servers for NAT traversal
- Custom reliability layer for commands
- Hole punching that may not work through carrier-grade NAT

WebSocket gives UDP-like low latency through a single TCP connection that works through NAT since the Pi initiates it outbound.

### Connection Flow

```
1. Pi boots up, starts main.py
2. rover_client.py attempts WebSocket connection to wss://miraeopus.com/rover
3. On connect, sends identification: {"type": "rover:identify", "data": {"id": "rover-001", ...}}
4. Server responds with ack: {"type": "ack", "data": {"message": "Identified"}}
5. Telemetry loop starts: sends {"type": "rover:telemetry", "data": {...}} every 1 second
6. Commands arrive instantly: {"type": "command", "data": {"type": "navigate", "payload": {...}}}
7. If WebSocket disconnects, automatically falls back to HTTP POST/GET
8. Reconnection attempts every 5 seconds
```

## Power Architecture

```
12V Battery (5-10 Ah)
    │
    ├──> Motor Driver (12V direct) ──> Motors
    │
    ├──> 5V Buck Converter (6A) ──┬──> Raspberry Pi (via GPIO 5V pins)
    │                             │     └──> SIM7600 HAT (via GPIO)
    │                             │     └──> USB Camera
    │                             └──> USB Microphone
    │
    └──> 3.3V Buck Converter (1A) ──> STM32 VDD
```

## Data Flow Timeline

**Every 1 second (Raspberry Pi main loop):**
1. Read GPS position from SIM7600 HAT (lat, lon, speed, heading)
2. Read telemetry from STM32 via UART (encoders, IMU data)
3. Calculate navigation: bearing and distance to target waypoint
4. Send target heading/speed to STM32 via UART
5. Send telemetry to server via WebSocket (or HTTP POST if WS disconnected)
6. Receive commands instantly via WebSocket (or poll HTTP GET if WS disconnected)

**Every 10ms (STM32 motor control loop):**
1. Read encoder counts (wheel speeds)
2. Read IMU gyroscope (current heading)
3. Run PID loops (heading error → differential drive, speed error → PWM)
4. Update motor PWM outputs
5. Check for UART commands from Pi

**Every 100ms (STM32 UART communication):**
1. Send telemetry packet to Pi: encoder counts, IMU data, status flags

## Communication Protocols

### Pi ↔ STM32 (UART at 115200 baud)
- Pi → STM32: `"HDG:285.3,SPD:1.50\n"` (target heading in degrees, speed in m/s)
- STM32 → Pi: `"ENC:1234,5678,VEL:100,98,IMU:100,-50,16384,10,-5,2\n"` (encoder counts, velocities, IMU raw values)

### Rover ↔ Server (WebSocket - PRIMARY)

**Rover → Server (telemetry):**
```json
{
    "type": "rover:telemetry",
    "data": {
        "id": "rover-001",
        "name": "RasPi Rover",
        "type": "robot",
        "lat": 34.0522,
        "lon": -118.2437,
        "alt": 100.0,
        "speed": 1.5,
        "heading": 45.0,
        "accuracy": 2.5,
        "hdop": 1.2,
        "ax": 100, "ay": -50, "az": 16384,
        "gx": 10, "gy": -5, "gz": 2,
        "encL": 12345, "encR": 12340,
        "encLVel": 100, "encRVel": 98,
        "battery": 85,
        "status": "online"
    }
}
```

**Server → Rover (command):**
```json
{
    "type": "command",
    "data": {
        "id": 1,
        "type": "navigate",
        "payload": {
            "latitude": 34.0525,
            "longitude": -118.2440,
            "altitude": 0
        },
        "timestamp": 1704067200000
    }
}
```

**Command Types:**
- `navigate` - Go to coordinates. Payload: `{ latitude, longitude, altitude }`
- `stop` - Stop immediately. Payload: `{}`
- `setSpeed` - Set max speed. Payload: `{ speed: 1.5 }`

### Rover ↔ Server (HTTP - FALLBACK)

Only used when WebSocket connection fails:
- `POST /api/telemetry` - Send telemetry JSON
- `GET /api/commands/{roverId}` - Poll for pending commands (cleared after retrieval)

### Browser ↔ Server (WebSocket)
- Connect to `wss://miraeopus.com/` (root path)
- Receives: `devices:list`, `device:online`, `device:update`, `device:offline`
- Sends: `getDevices`, `sendCommand`

## Performance Specifications

**Latency (WebSocket mode):**
- 4G LTE cellular: ~50-100ms
- End-to-end (click to robot response): ~100-200ms

**Latency (HTTP fallback mode):**
- 4G LTE cellular: ~50-100ms
- End-to-end (click to robot response): ~1-2 seconds (polling interval)

**Bandwidth:**
- Telemetry only: ~1 kbps (~300 MB/month)
- With video (720p): ~1-3 Mbps (~1-3 GB/hour)

**GPS Accuracy:**
- Horizontal: ~2.5m CEP (open sky)
- Update rate: 1 Hz

**Control Loop:**
- STM32 motor control: 100 Hz (10ms period)
- Pi navigation updates: 1 Hz (1000ms period)
- Pi sensor reading: 10 Hz (100ms period)

**Coverage:**
- 4G LTE Cat-1: Works anywhere with cellular coverage
- Fallback: 3G HSPA+ / 2G EDGE (automatic)

## File Structure

### Raspberry Pi (`/home/pi/rover/`)
```
rover/
├── rover_client.py    # WebSocket/HTTP client (standalone, can be imported)
├── main.py            # Full application with GPS, STM32, navigation
├── requirements.txt   # Python dependencies
└── README.md          # Setup and usage instructions
```

### Server (GlobalRTS on Fly.io)
```
GlobalRTS/
├── server.js          # Main server (use server_enhanced.js for WS rover support)
├── public/
│   ├── globalui.html  # Main UI
│   └── CONFIG.js      # Client configuration
├── fly.toml           # Fly.io deployment config (MUST be single instance!)
├── Dockerfile
└── package.json
```

## Deployment Notes

### Fly.io Single Instance Requirement
The server stores rover state in-memory (no database). If multiple Fly.io instances run, WebSocket connections get load-balanced between them, causing disconnects. **Always run single instance:**

```bash
fly scale count 1 --yes
```

Or in `fly.toml`:
```toml
[http_service]
  min_machines_running = 1
  # Don't set max > 1 unless you add Redis for shared state
```

### Raspberry Pi Setup
```bash
# Install dependencies
pip3 install websockets aiohttp pyserial

# Disable serial console (required for STM32 UART)
sudo raspi-config
# Interface Options → Serial Port → Login shell: NO, Hardware: YES

# Run rover
python3 main.py --server wss://miraeopus.com --rover-id rover-001

# Or simulation mode (no hardware)
python3 main.py --simulate --server wss://miraeopus.com --rover-id test-rover
```

### SIM7600G-H Serial Ports
The SIM7600 creates multiple USB serial ports:
- `/dev/ttyUSB0` - Diagnostic port
- `/dev/ttyUSB1` - NMEA GPS output
- `/dev/ttyUSB2` - AT command port (used by our code)
- `/dev/ttyUSB3` - Modem port

## Known Issues & Solutions

### WebSocket Disconnects Immediately After Identification
- **Cause**: Multiple Fly.io instances running
- **Solution**: `fly scale count 1 --yes`

### `'ClientConnection' object has no attribute 'open'`
- **Cause**: websockets library v12+ API change
- **Solution**: Use `not ws.close_code` instead of `ws.open` (fixed in latest rover_client.py)

### GPS Not Getting Fix
- **Cause**: Need clear sky view, cold start can take 30-60 seconds
- **Solution**: Wait outdoors, check antenna connection, verify with `AT+CGPSINFO`

### STM32 UART Not Responding
- **Cause**: Pi serial console still enabled, or TX/RX wiring swapped
- **Solution**: Disable console via raspi-config, verify crossover wiring (Pi TX → STM32 RX)
