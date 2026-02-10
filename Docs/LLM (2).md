# What We Are Doing
We are creating a system where my wheeled rover has a Raspberry Pi 5 as the main computer with a SIM7600G-H 4G LTE cellular modem that sends GPS data (Latitude, Longitude, Accuracy, Altitude, Speed, Heading, etc.) and telemetry every second while it is moving around in the environment. The Raspberry Pi communicates with an STM32L476RG microcontroller via UART which handles real-time motor control loops (50-100 Hz) using encoder feedback and LSM6DS3 IMU data for heading stabilization. The Pi handles strategic navigation (GPS -> waypoint calculation), while the STM32 handles tactical motor control (heading -> motor PWM). All data is sent to the main server at miraeopus.com. From my laptop/browser I will see the live data from my robot with GlobalRTS. I can then use my laptop to click on certain areas on GlobalRTS's Google Earth-like UI to command the robot to go to certain coordinates. The system also supports video streaming from a USB camera and audio from a USB microphone for future telepresence features.

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
                    RASPBERRY PI 5
                   (Strategic Layer)
                          |
        +-----------------+-----------------+
        |                 |                 |
   SIM7600G-H HAT     UART GPIO        USB Devices
   /dev/ttyUSB1 (NMEA)  /dev/ttyAMA0    Camera, Mic
   /dev/ttyUSB2 (AT)    (to STM32)      (future)
        |                 |
        |            STM32L476RG
        |            (Motor Control)
        |                 |
        |            Motors + IMU
        |
   /dev/cdc-wdm0     wwan0
   (QMI control)     (cellular data)
        |                 |
        +--------+--------+
                 |
          4G LTE / WiFi
                 |
                 v
      Fly.io Server (miraeopus.com)
                 ^
                 |
          Browser (GlobalRTS)
```

## Networking: WiFi + Cellular Coexistence

The Pi runs both WiFi and cellular simultaneously. **WiFi is never disabled.**

```
wlan0 (WiFi)  -- ALWAYS ON. Used for SSH, dev work, default internet.
wwan0 (4G)    -- Brought up by cellular_connect.sh. Used ONLY by live_gps.py
                 when --cellular flag is passed.
```

**How --cellular works:** live_gps.py creates a socket bound to wwan0's IP address (`socket.bind((wwan0_ip, 0))`), then passes that socket to the WebSocket connection. This forces ONLY the rover telemetry through cellular. All other traffic (SSH, DNS, apt, etc.) continues through WiFi via the default route. You never lose SSH access.

**Command flow (laptop -> miraeopus -> cellular -> Pi):**
```
1. You click a location in GlobalRTS (browser on laptop)
2. Browser sends command via WebSocket to wss://miraeopus.com/
3. Server forwards command via WebSocket to the rover's connection
4. If --cellular: that WebSocket connection runs over wwan0 (4G LTE)
5. live_gps.py receives the command and logs it (motor control is future)
```

**Quick reference:**
```bash
python3 live_gps.py              # WiFi mode (WebSocket via wlan0)
python3 live_gps.py --cellular   # Cellular mode (WebSocket via wwan0, SSH via wlan0)
```

## GPS Data Sources

live_gps.py reads GPS from TWO serial ports simultaneously for maximum data:

**Port 1: /dev/ttyUSB2 (AT commands) -- primary position source**
- Command: `AT+CGPSINFO`
- Returns: latitude, longitude, altitude, speed (knots), heading (course)
- Parsed every 1 second in main thread

**Port 2: /dev/ttyUSB1 (NMEA sentences) -- DOP and satellite data**
- Outputs continuously when GPS is enabled (no AT commands needed)
- Parsed by background thread, provides:
  - `$GPGGA`: HDOP, number of satellites, fix quality, altitude (MSL)
  - `$GPGSA`: PDOP, HDOP, VDOP
  - `$GPRMC`: Speed (knots), heading, date/time
  - `$GPVTG`: Speed (km/h), true heading

**Data merging:** AT+CGPSINFO provides lat/lon (primary). NMEA provides HDOP/PDOP/VDOP/sat count. For altitude/speed/heading, NMEA is preferred when available (higher update rate), with AT values as fallback.

**Telemetry fields sent to server:**
```
lat, lon, alt, speed, heading    -- from AT+CGPSINFO / NMEA
accuracy                         -- estimated from HDOP * 2.5m
hdop, pdop, vdop                 -- from NMEA ($GPGSA)
numSats                          -- from NMEA ($GPGGA)
rtt_ms, rtt_avg_ms               -- WebSocket ping/pong latency
sent_at                          -- timestamp for server-side latency calc
ax, ay, az, gx, gy, gz          -- placeholder (STM32 IMU future)
encL, encR, encLVel, encRVel     -- placeholder (STM32 encoders future)
battery, status                  -- rover status
```

## Latency Measurement

live_gps.py measures round-trip latency two ways:

**1. WebSocket ping/pong (rover <-> server)**
Every 10 seconds, the rover sends a WebSocket-level ping frame and waits for the pong response. The round-trip time is measured and reported as `rtt_ms` in telemetry. This measures: Pi -> cellular/WiFi -> internet -> Fly.io server -> internet -> cellular/WiFi -> Pi.

**2. Command age (browser -> server -> rover)**
When GlobalRTS sends a command, it includes a `timestamp` (milliseconds since epoch). When the rover receives the command, it calculates `recv_time - timestamp` = command age in ms. This measures the full pipeline: browser -> miraeopus.com -> rover.

Both are printed to the terminal and included in telemetry data.

## SIM7600G-H Cellular Setup (QMI)

The SIM7600G-H has a Qualcomm MDM9607 chipset. Cellular data uses **QMI** (Qualcomm MSM Interface), NOT PPP. The old `cellular.py` PPP approach failed because this modem doesn't support PPP well when QMI is active.

### Hardware Interfaces Created by SIM7600
- `/dev/ttyUSB0` -- Diagnostic port
- `/dev/ttyUSB1` -- NMEA GPS output (used by live_gps.py for HDOP/PDOP)
- `/dev/ttyUSB2` -- AT command port (used by live_gps.py for GPS reads)
- `/dev/ttyUSB3` -- Modem port
- `/dev/cdc-wdm0` -- QMI control device (used by cellular_connect.sh)
- `wwan0` -- Cellular data interface (created by qmi_wwan kernel driver)

### One-Time Pi Setup
```bash
# 1. Install QMI tools and DHCP client
sudo apt install libqmi-utils udhcpc

# 2. Disable ModemManager (it grabs the AT port and interferes)
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager

# 3. Disable serial console (required for STM32 UART on /dev/ttyAMA0)
sudo raspi-config
# Interface Options -> Serial Port -> Login shell: NO, Hardware: YES

# 4. Install Python dependencies
pip3 install websockets aiohttp pyserial

# 5. Verify SIM7600 is detected
lsusb | grep -i qualcomm    # Should show Qualcomm device
ls /dev/ttyUSB*              # Should show ttyUSB0 through ttyUSB3
ls /dev/cdc-wdm0             # Should exist (QMI control)
ip link show wwan0           # Should exist (state DOWN is OK at this point)
```

### Bringing Up Cellular Data
```bash
# Bring up wwan0 with cellular data via QMI
sudo bash cellular_connect.sh              # APN: super (Mint Mobile / T-Mobile MVNO)
sudo bash cellular_connect.sh broadband    # Custom APN example

# Verify cellular is up
ip addr show wwan0           # Should show an inet IP address
ping -c 2 -I wwan0 8.8.8.8  # Should get replies (through cellular!)

# Stop cellular when done
sudo bash cellular_connect.sh stop
```

### What cellular_connect.sh Does
1. Checks `/dev/cdc-wdm0` exists (QMI control device from qmi_wwan driver)
2. Sets modem online: `qmicli --dms-set-operating-mode='online'`
3. Checks signal strength and network registration (T-Mobile)
4. Brings wwan0 down, sets raw-ip mode (`echo Y > /sys/class/net/wwan0/qmi/raw_ip`), brings wwan0 up
5. Starts QMI data session: `qmicli --wds-start-network="apn='super',ip-type=4"`
6. Gets IP address via DHCP: `udhcpc -i wwan0`
7. Verifies connectivity with ping through wwan0

### Running the Rover
```bash
# --- WiFi mode (at home, testing) ---
python3 live_gps.py

# --- Cellular mode (in the field) ---
sudo bash cellular_connect.sh              # Step 1: bring up wwan0
python3 live_gps.py --cellular             # Step 2: rover data goes through 4G
# WiFi stays up! SSH still works on wlan0.

# --- Skip NMEA if ttyUSB1 is busy ---
python3 live_gps.py --no-nmea             # Only AT+CGPSINFO, no HDOP/PDOP

# --- Simulated rover (no hardware) ---
python3 test.py                            # For testing server/UI
```

### Troubleshooting Cellular
```bash
# /dev/cdc-wdm0 missing?
sudo modprobe qmi_wwan
lsusb | grep -i qualcomm     # Is the modem detected?

# wwan0 has no IP after cellular_connect.sh?
# Check APN is correct for your carrier
# Check signal: send AT+CSQ to /dev/ttyUSB2
# Check SIM: send AT+CPIN? to /dev/ttyUSB2

# ModemManager keeps grabbing the port?
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
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

### Connection Flow

```
1. Pi runs: python3 live_gps.py [--cellular]
2. Opens /dev/ttyUSB2 (AT) and /dev/ttyUSB1 (NMEA)
3. Enables GPS: AT+CGPS=1,1
4. Waits for GPS fix (up to 60s)
5. Connects WebSocket to wss://miraeopus.com/rover
   - WiFi mode: normal socket through wlan0
   - Cellular mode: socket bound to wwan0 IP
6. Sends: {"type": "rover:identify", "data": {"id": "rover-001", ...}}
7. Server responds: {"type": "ack"}
8. Telemetry loop: sends rover:telemetry every 1s with GPS + NMEA data
9. Receives commands instantly from GlobalRTS browser
10. Latency ping every 10s
11. On disconnect: reconnects every 5s
```

## Power Architecture

```
12V Battery (5-10 Ah)
    |
    +---> Motor Driver (12V direct) ---> Motors
    |
    +---> 5V Buck Converter (6A) --+---> Raspberry Pi (via GPIO 5V pins)
    |                              |      +---> SIM7600 HAT (via GPIO)
    |                              |      +---> USB Camera
    |                              +---> USB Microphone
    |
    +---> 3.3V Buck Converter (1A) ---> STM32 VDD
```

## Communication Protocols

### Pi <-> STM32 (UART at 115200 baud) [future]
- Pi -> STM32: `"HDG:285.3,SPD:1.50\n"` (target heading in degrees, speed in m/s)
- STM32 -> Pi: `"ENC:1234,5678,VEL:100,98,IMU:100,-50,16384,10,-5,2\n"` (encoder counts, velocities, IMU raw values)

### Rover <-> Server (WebSocket)

**Rover -> Server (telemetry):**
```json
{
    "type": "rover:telemetry",
    "data": {
        "id": "rover-001",
        "name": "RasPi Rover",
        "type": "robot",
        "lat": 34.0522, "lon": -118.2437, "alt": 100.0,
        "speed": 1.5, "heading": 45.0,
        "accuracy": 2.75, "hdop": 1.1, "pdop": 1.5, "vdop": 1.3,
        "numSats": 12,
        "ax": 100, "ay": -50, "az": 16384,
        "gx": 10, "gy": -5, "gz": 2,
        "encL": 0, "encR": 0, "encLVel": 0, "encRVel": 0,
        "battery": 85, "status": "online",
        "rtt_ms": 87, "rtt_avg_ms": 92,
        "sent_at": 1707500000000
    }
}
```

**Server -> Rover (command):**
```json
{
    "type": "command",
    "data": {
        "id": 1,
        "type": "navigate",
        "payload": { "latitude": 34.0525, "longitude": -118.2440, "altitude": 0 },
        "timestamp": 1707500000000
    }
}
```

**Command Types:**
- `navigate` - Go to coordinates. Payload: `{ latitude, longitude, altitude }`
- `stop` - Stop immediately. Payload: `{}`
- `setSpeed` - Set max speed. Payload: `{ speed: 1.5 }`

### Browser <-> Server (WebSocket)
- Connect to `wss://miraeopus.com/` (root path)
- Receives: `devices:list`, `device:online`, `device:update`, `device:offline`
- Sends: `getDevices`, `sendCommand`

## Performance Specifications

**Latency (WebSocket mode):**
- 4G LTE cellular: ~50-100ms RTT (measured by ping/pong)
- End-to-end command (browser click to rover receipt): ~100-300ms

**Bandwidth:**
- Telemetry only: ~1 kbps (~300 MB/month)
- With video (720p): ~1-3 Mbps (~1-3 GB/hour)

**GPS Accuracy:**
- Horizontal: ~2.5m CEP (open sky), accuracy = HDOP * 2.5m
- Update rate: 1 Hz
- DOP values: HDOP, PDOP, VDOP from NMEA $GPGSA

**Coverage:**
- 4G LTE Cat-1: Works anywhere with cellular coverage
- Fallback: 3G HSPA+ / 2G EDGE (automatic)

## File Structure

### Raspberry Pi (`~/Documents/MiraeRTS/MCUs/Raspi5/`)
```
rover/
+-- live_gps.py          # THE MAIN SCRIPT -- real GPS to GlobalRTS
+-- cellular_connect.sh  # Bring up wwan0 cellular via QMI
+-- GPS.py               # Standalone GPS reader (AT+CGPSINFO)
+-- test.py              # Simulated rover (for testing server/UI)
+-- rover_client.py      # WebSocket/HTTP client library
+-- main.py              # Full app with STM32 navigation (future)
+-- requirements.txt     # Python dependencies
+-- SIM7600InstallRun.md # Hardware setup notes
+-- LLM.md              # This file
```

### Server (GlobalRTS on Fly.io)
```
GlobalRTS/
+-- server.js          # Main server with WebSocket rover support
+-- public/
|   +-- globalui.html  # Main UI
|   +-- CONFIG.js      # Client configuration
+-- fly.toml           # Fly.io config (MUST be single instance!)
+-- Dockerfile
+-- package.json
```

### Deprecated Files (still on Pi, not actively used)
- `cellular.py` -- PPP/NDIS approach. Failed. Replaced by `cellular_connect.sh` (QMI).
- `test_cellular.py` -- Used cellular.py. Use `live_gps.py --cellular` instead.

## Deployment Notes

### Fly.io Single Instance Requirement
The server stores rover state in-memory. Multiple instances cause WebSocket disconnects.
```bash
fly scale count 1 --yes
```

## Known Issues & Solutions

### WebSocket Disconnects Immediately After Identification
- **Cause**: Multiple Fly.io instances running
- **Solution**: `fly scale count 1 --yes`

### GPS Not Getting Fix
- **Cause**: Need clear sky view, cold start can take 30-60 seconds
- **Solution**: Wait outdoors, check antenna connection, verify with `AT+CGPSINFO`

### /dev/cdc-wdm0 Not Found
- **Cause**: qmi_wwan kernel driver not loaded or SIM7600 not detected
- **Solution**: `sudo modprobe qmi_wwan`, check `lsusb`, check USB cable

### wwan0 Has No IP After cellular_connect.sh
- **Cause**: APN wrong, SIM not activated, or signal too weak
- **Solution**: Check APN for your carrier, verify SIM with `AT+CPIN?`, check signal with `AT+CSQ`

### ModemManager Grabs AT Port
- **Cause**: ModemManager auto-detects modem and locks /dev/ttyUSB2
- **Solution**: `sudo systemctl stop ModemManager && sudo systemctl disable ModemManager`

### NMEA Port Not Working (/dev/ttyUSB1)
- **Cause**: GPS not enabled yet, or ModemManager holding the port
- **Solution**: Enable GPS first (`AT+CGPS=1,1`), disable ModemManager, or use `--no-nmea` flag

## Changelog

### 2026-02-09 -- live_gps.py v2: NMEA, cellular --flag, latency
Major rewrite of live_gps.py:
- Added NMEA reader (background thread on /dev/ttyUSB1) for HDOP, PDOP, VDOP, sat count, better alt/speed/heading
- Added `--cellular` flag that binds WebSocket to wwan0 IP (WiFi stays for SSH)
- Added latency measurement: WebSocket ping/pong RTT every 10s + command age calculation
- Added `--no-nmea` flag to skip NMEA port if unavailable
- Commands from GlobalRTS (navigate/stop/setSpeed) are received and logged with latency info

### 2026-02-09 -- cellular_connect.sh
Created QMI-based cellular data script. Uses qmicli to bring up wwan0 via QMI instead of the old PPP approach which failed.

### 2026-02-09 -- live_gps.py v1
Initial version. Real GPS over WiFi confirmed working.

### IMPORTANT NOTES KEEP THIS AT THE BOTTOM OF THIS MD FILE
1. For the love of god do not rename the file or folder other than what was already given and if you want to name something new, ask first
2. Do not use emojis for any print statements for files meant to go into a linux machine like Raspi, it can't encode the emoji properly. 
