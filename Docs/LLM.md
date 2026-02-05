# What We Are Doing
We are creating a system where my wheeled rover has a Raspberry Pi 4 as the main computer with a SIM7600G-H 4G LTE cellular modem that sends GPS data (Latitude, Longitude, Accuracy, Altitude, Speed, Heading, etc.) and telemetry every second while it is moving around in the environment. The Raspberry Pi communicates with an STM32L476RG microcontroller via UART which handles real-time motor control loops (50-100 Hz) using encoder feedback and LSM6DS3 IMU data for heading stabilization. The Pi handles strategic navigation (GPS → waypoint calculation), while the STM32 handles tactical motor control (heading → motor PWM). All data is sent to the main server at miraeopus.com. From my laptop/browser I will see the live data from my robot with GlobalRTS. I can then use my laptop to click on certain areas on GlobalRTS's Google Earth-like UI to command the robot to go to certain coordinates. The system also supports video streaming from a USB camera and audio from a USB microphone for future telepresence features.

## Laptop/Browser
Basically a way to open GlobalRTS, which runs in a browser on the internet. Connects to the Fly.io server to view robot telemetry and send commands.

## GlobalRTS
GlobalRTS is the UI interface to see the live location and data from robot. I can also use it to send commands to the robot like telling it where to go. This is done by giving GlobalRTS a Google Earth view so I can click on the rover from the map and then click on a location to send it to. Possible since the Google Earth map is already divided into Latitude/Longitude coordinates, so both the laptop, GlobalRTS, and robot can agree on coordinates and where things are. 

Important to note the GlobalRTS is also a way for me to check the news, Oura Ring sleep calendar, and has RTS controls like left click+drag to select units (robots), left click on a unit to select it, once selected right click on a location to send it there and displays the location selected, also control panel that can show/hide the different panels and UI elements.

## Miraeopus.com
I bought and own the domain name Miraeopus.com. This is where GlobalRTS is hosted and serves as the connector between my laptop/browser and rover. The server receives telemetry via HTTP POST, queues commands via HTTP GET polling, and provides WebSocket connections for real-time updates to the browser UI.

## Robot Hardware
The rover consists of:
- **Raspberry Pi 4** (2GB+): Main computer running Python, handles GPS, cellular, navigation logic, video streaming
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
┌─────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 4                       │
│                     (Strategic Layer - 1 Hz)            │
│                                                         │
│  Main Python Application:                              │
│  ├─ GPS positioning (from SIM7600 HAT)                 │
│  ├─ Navigation logic (GPS → waypoint → target heading) │
│  ├─ HTTP POST telemetry to miraeopus.com               │
│  ├─ HTTP GET commands from miraeopus.com               │
│  ├─ UART commands to STM32 (target heading/speed)      │
│  ├─ Video streaming (USB camera → WebRTC)              │
│  └─ Audio capture (USB microphone)                     │
│                                                         │
│  Connected Hardware:                                   │
│  ├─ SIM7600G-H HAT (GPIO) ──> 4G LTE + GPS            │
│  ├─ USB Camera ──> Video                               │
│  ├─ USB Microphone ──> Audio                           │
│  └─ UART (GPIO 14/15) ──> STM32                        │
└────────────────────────────┬────────────────────────────┘
                             │ UART (115200 baud)
                             │ TX: Commands (heading, speed)
                             │ RX: Telemetry (encoders, IMU)
┌────────────────────────────▼────────────────────────────┐
│                   STM32L476RG + FreeRTOS                │
│                   (Tactical Layer - 50-100 Hz)          │
│                                                         │
│  Task 1: Motor Control Loop (100 Hz)                   │
│  ├─ Read encoders (left/right wheel speeds)            │
│  ├─ Read IMU (gyroscope for heading)                   │
│  ├─ PID controller (heading + speed)                   │
│  └─ Output PWM to motor driver                         │
│                                                         │
│  Task 2: UART Communication (10 Hz)                    │
│  ├─ Receive commands from Pi (target heading/speed)    │
│  ├─ Send telemetry to Pi (encoders, IMU, status)       │
│  └─ Buffer sensor data                                 │
│                                                         │
│  Task 3: Safety Monitor (100 Hz)                       │
│  └─ Emergency stop if Pi stops responding (5s timeout) │
│                                                         │
└───────────┬─────────────────┬───────────────────────────┘
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
                            ▼
┌────────────────────────────────────────────────────────┐
│              Fly.io Server (miraeopus.com)             │
│                                                        │
│  Node.js + Express + WebSocket                         │
│  ├─ POST /api/robot/telemetry (receive from robot)    │
│  ├─ GET /api/robot/commands (polled by robot)         │
│  ├─ POST /api/robot/command (from GlobalRTS UI)       │
│  ├─ WebSocket (real-time updates to browser)          │
│  └─ In-memory state (no database for now)             │
└────────────────────────────────────────────────────────┘
                            ▲
                    WebSocket + HTTPS
                            │
┌────────────────────────────────────────────────────────┐
│              GlobalRTS UI (Browser)                    │
│                                                        │
│  ├─ Google Maps / Earth view                          │
│  ├─ Robot position marker (updates real-time)         │
│  ├─ Click map → send waypoint command                 │
│  ├─ Telemetry display (speed, heading, battery, etc.) │
│  └─ Video stream view (WebRTC)                        │
└────────────────────────────────────────────────────────┘
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
2. HTTP GET to check for new commands from server
3. Calculate navigation: bearing and distance to target waypoint
4. Send target heading/speed to STM32 via UART
5. Read telemetry from STM32 (encoders, IMU data)
6. HTTP POST all telemetry to miraeopus.com server
7. Capture and stream video frame (if video enabled)

**Every 10ms (STM32 motor control loop):**
1. Read encoder counts (wheel speeds)
2. Read IMU gyroscope (current heading)
3. Run PID loops (heading error → differential drive, speed error → PWM)
4. Update motor PWM outputs
5. Check for UART commands from Pi

**Every 100ms (STM32 UART communication):**
1. Send telemetry packet to Pi: encoder counts, IMU data, status flags

## Communication Protocols

**Pi ↔ STM32 (UART at 115200 baud):**
- Pi → STM32: `"HDG:285.3,SPD:1.50\n"` (target heading in degrees, speed in m/s)
- STM32 → Pi: `"ENC:1234,5678,IMU:0.05,0.02,9.81,0.01,-0.02,0.15\n"` (encoder counts, accel xyz, gyro xyz)

**Robot ↔ Server (HTTP over 4G LTE):**
- Robot → Server: `POST /api/robot/telemetry` with JSON payload (GPS, encoders, IMU, status)
- Robot ← Server: `GET /api/robot/commands` returns JSON command (goto waypoint, stop, etc.)

**Browser ↔ Server (WebSocket + HTTPS):**
- Browser → Server: `POST /api/robot/command` to send waypoint
- Browser ← Server: WebSocket messages with real-time telemetry updates

## Performance Specifications

**Latency:**
- 4G LTE cellular: ~50-100ms
- End-to-end (click to robot response): ~1-2 seconds (limited by 1Hz polling)

**Bandwidth:**
- Telemetry only: ~1 kbps (~300 MB/month)
- With video (720p): ~1-3 Mbps (~1-3 GB/hour)

**GPS Accuracy:**
- Horizontal: ~2.5m CEP (open sky)
- Update rate: 1 Hz

**Control Loop:**
- STM32 motor control: 100 Hz (10ms period)
- Pi navigation updates: 1 Hz (1000ms period)

**Coverage:**
- 4G LTE Cat-1: Works anywhere with cellular coverage
- Fallback: 3G HSPA+ / 2G EDGE (automatic)
