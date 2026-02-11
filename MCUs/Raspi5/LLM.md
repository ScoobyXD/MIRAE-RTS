# What We Are Doing
We are creating a system where my wheeled rover has a Raspberry Pi 5 as the main computer with a SIM7600G-H 4G LTE cellular modem that sends GPS data (Latitude, Longitude, Accuracy, Altitude, Speed, Heading, etc.) and telemetry every second while it is moving around in the environment. The Raspberry Pi communicates with an STM32L476RG microcontroller via CAN bus (MCP2515 SPI-to-CAN modules on both sides) which handles real-time motor control loops (50-100 Hz) using encoder feedback and LSM6DS3 IMU data for heading stabilization. The Pi handles strategic navigation (GPS -> waypoint calculation), while the STM32 handles tactical motor control (heading -> motor PWM). All data is sent to the main server at miraeopus.com. From my laptop/browser I will see the live data from my robot with GlobalRTS. I can then use my laptop to click on certain areas on GlobalRTS's Google Earth-like UI to command the robot to go to certain coordinates. The system also supports video streaming from a USB camera and audio from a USB microphone for future telepresence features.

## Laptop/Browser
Opens GlobalRTS in a browser. Connects to Fly.io server via WebSocket to view robot telemetry and send commands in real-time.

## GlobalRTS
UI interface to see live location and data from robot. Google Earth view lets you click on rover on map, then right-click a location to send it there. Also displays news, Oura Ring sleep calendar, and has RTS controls (left-click+drag select, left-click unit to select, right-click to send).

## Miraeopus.com
Owned domain. Hosts GlobalRTS. Server uses WebSocket as primary protocol for both browser and rover connections, HTTP as fallback.

## Robot Hardware
- **Raspberry Pi 5**: Main computer, Python, GPS, cellular, navigation logic
- **STM32L476RG**: Real-time motor control with FreeRTOS, PID loops, encoders, IMU
- **Waveshare SIM7600G-H 4G HAT**: 4G LTE modem + GPS/GNSS receiver
- **MCP2515+TJA1050 CAN modules (x2)**: SPI-to-CAN bridge, one per side, 500kbps
- **LSM6DS3 IMU**: 6-axis accel+gyro for heading (connected to STM32 via I2C)
- **Motor encoders**: Quadrature on both motors (future)
- **12V Battery**: Powers motors, 5V buck converters for Pi+STM32

## System Architecture

```
                    RASPBERRY PI 5
                   (Strategic Layer)
                          |
        +-----------------+-----------------+
        |                 |                 |
   SIM7600G-H HAT     SPI0 GPIO        USB Devices
   /dev/ttyUSB1 (NMEA)  (MCP2515)       Camera, Mic
   /dev/ttyUSB2 (AT)    can0 interface   (future)
        |                 |
        |            CAN Bus (500kbps)
        |            CANH/CANL wires
        |                 |
        |            MCP2515+TJA1050
        |            (STM32 side, SPI1)
        |                 |
        |            STM32L476RG
        |            (Motor Control)
        |                 |
        |            Motors + IMU + Encoders
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
wwan0 (4G)    -- Brought up by cellular_connect.sh. Used ONLY by live_gps.py.
```

**How --cellular works:** live_gps.py uses `SO_BINDTODEVICE` (Linux socket option 25) to force the WebSocket through wwan0 at the kernel level. This is the same mechanism `curl --interface wwan0` uses. Requires sudo/root.

**CRITICAL: socket.bind((ip, 0)) does NOT work.** We tried this first and it failed -- traffic still routed through WiFi because Linux's routing table overrides the source IP. Only `SO_BINDTODEVICE` actually forces packets through a specific interface.

**Command flow (laptop -> miraeopus -> cellular -> Pi):**
```
1. Click location in GlobalRTS browser
2. Browser sends command via WebSocket to wss://miraeopus.com/
3. Server forwards command to rover's WebSocket connection
4. If --cellular: that WebSocket runs over wwan0 (4G LTE) via SO_BINDTODEVICE
5. live_gps.py receives and logs the command
```

**Quick reference:**
```bash
python3 live_gps.py                      # WiFi mode
sudo python3 live_gps.py --cellular      # Cellular mode (requires sudo for SO_BINDTODEVICE)
```

## GPS Data Sources

live_gps.py reads GPS from TWO serial ports simultaneously:

**Port 1: /dev/ttyUSB2 (AT commands)** -- primary position source
- Command: `AT+CGPSINFO` -> lat, lon, alt, speed (knots), heading

**Port 2: /dev/ttyUSB1 (NMEA sentences)** -- DOP and satellite data
- Background thread parses: `$GPGGA` (HDOP, sats, alt), `$GPGSA` (PDOP, HDOP, VDOP), `$GPRMC`/`$GPVTG` (speed, heading)

**Telemetry fields sent to server every 1 second:**
```
lat, lon, alt, speed, heading, accuracy, hdop, pdop, vdop, numSats,
rtt_ms, rtt_avg_ms, sent_at, ax, ay, az, gx, gy, gz,
encL, encR, encLVel, encRVel, battery, status
```

## Latency Measurement

**1. WebSocket ping/pong:** Every 10s, measures round-trip time via WS ping/pong.
**2. Command age:** Commands include a timestamp. Rover calculates `now - timestamp` on receipt.

## SIM7600G-H Cellular Setup (QMI)

Qualcomm MDM9607 chipset. Uses **QMI** (Qualcomm MSM Interface), NOT PPP. PPP failed on this modem.

### Hardware Interfaces
- `/dev/ttyUSB0` -- Diagnostic
- `/dev/ttyUSB1` -- NMEA GPS output (live_gps.py NMEA reader)
- `/dev/ttyUSB2` -- AT commands (live_gps.py GPS reads)
- `/dev/ttyUSB3` -- Modem port
- `/dev/cdc-wdm0` -- QMI control (cellular_connect.sh)
- `wwan0` -- Cellular data interface (qmi_wwan kernel driver)

### How QMI Cellular Data Works

**Step 1: Set modem online** -- `qmicli --dms-set-operating-mode='online'`
**Step 2: Set raw-ip mode** -- `echo Y > /sys/class/net/wwan0/qmi/raw_ip` (interface must be down first, cellular uses raw IP not ethernet frames)
**Step 3: Start QMI data session** -- `qmicli --wds-start-network="apn='super',ip-type=4" --client-no-release-cid` (establishes PDP context with cell tower, `--client-no-release-cid` keeps session alive after qmicli exits)
**Step 4: Get IP via DHCP** -- `udhcpc -i wwan0`

### Cell Tower Handover Problem
When driving, cell tower handovers can drop the PDP context. Unlike a phone, QMI doesn't auto-reconnect. **cellular_connect.sh has a watchdog loop** that pings every 15s and re-runs the full QMI setup if connectivity is lost.

### One-Time Pi Setup
```bash
sudo apt install libqmi-utils udhcpc
sudo systemctl stop ModemManager && sudo systemctl disable ModemManager
pip3 install websockets pyserial
```

## Auto-Start on Boot (systemd)

Two systemd services handle startup:

**rover-cellular.service** -- Waits for `/dev/cdc-wdm0` (up to 30s), then runs `cellular_connect.sh` with watchdog.
**rover-gps.service** -- Waits for wwan0 to get an IP (up to 60s), then runs `live_gps.py --cellular`.

### Installation
```bash
sudo cp rover-cellular.service /etc/systemd/system/
sudo cp rover-gps.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rover-cellular.service
sudo systemctl enable rover-gps.service

# Test (starts immediately):
sudo systemctl start rover-cellular.service
sudo systemctl start rover-gps.service

# Check status:
sudo systemctl status rover-cellular.service
sudo systemctl status rover-gps.service
sudo journalctl -u rover-gps.service -f     # live system logs

# Disable auto-start:
sudo systemctl disable rover-cellular.service
sudo systemctl disable rover-gps.service
```

### Manual Mode (development)
```bash
# Terminal 1:
sudo bash cellular_connect.sh

# Terminal 2:
sudo python3 live_gps.py --cellular
```

## Logging

Both scripts write rotating logs to `~/Documents/MiraeRTS/MCUs/Raspi5/logs/`:

- `logs/live_gps.log` -- GPS fixes (every 30s), connections, disconnects, commands, errors. Rotates at 5MB, keeps 10 files.
- `logs/cellular.log` -- QMI session starts/stops, signal strength, reconnections, watchdog events. Rotates at 5MB.

**View logs:**
```bash
tail -f logs/live_gps.log
tail -f logs/cellular.log
cat logs/live_gps.log | grep "ERROR\|WARN"
cat logs/cellular.log | grep "Connection lost"
```

## Communication Protocols

### Pi <-> STM32 (CAN Bus 500kbps via MCP2515)
Both sides use MCP2515+TJA1050 modules connected via SPI. CAN frames carry structured data with defined message IDs.

**STM32 -> Pi (telemetry):**
- `0x100` Heartbeat: uptime(4B) + seq(2B) + can_ok(1B) + eflg(1B) -- every 200ms
- `0x101` IMU accel: ax(2B) + ay(2B) + az(2B) as int16*1000 -- every 200ms
- `0x102` IMU gyro: gx(2B) + gy(2B) + gz(2B) as int16*1000 -- every 200ms
- `0x103` Encoders: encL(4B) + encR(4B) as int32 -- future
- `0x104` Status: flags, battery, errors -- future

**Pi -> STM32 (commands):**
- `0x200` Navigate: heading_x10(2B) + speed_x100(2B) as int16
- `0x201` Stop: 0x01 (1B)
- `0x202` Set speed: speed_x100(2B) as int16
- `0x2FF` Ping: 0x01 (STM32 responds with heartbeat)

### Rover <-> Server (WebSocket)
**Telemetry:** `{"type": "rover:telemetry", "data": {...}}`
**Commands:** `{"type": "command", "data": {"type": "navigate", "payload": {"latitude": ..., "longitude": ...}, "timestamp": ...}}`
**Command types:** navigate, stop, setSpeed

### Browser <-> Server
Connect to `wss://miraeopus.com/` -- receives device:online/update/offline, sends getDevices/sendCommand

## File Structure

### Raspberry Pi (`~/Documents/MiraeRTS/MCUs/Raspi5/`)
```
live_gps.py              # MAIN SCRIPT -- real GPS to GlobalRTS over cellular/WiFi
can_bridge.py            # CAN bus bridge -- reads STM32 telemetry, sends commands via MCP2515
can_setup.sh             # Bring up can0 interface (run after reboot)
cellular_connect.sh      # Bring up wwan0 via QMI + watchdog auto-reconnect
rover-cellular.service   # systemd: auto-start cellular on boot
rover-gps.service        # systemd: auto-start live_gps.py on boot
GPS.py                   # Standalone GPS reader (AT+CGPSINFO only)
test.py                  # Simulated rover (for testing server/UI without hardware)
rover_client.py          # WebSocket/HTTP client library
main.py                  # Full app with STM32 navigation (future)
LLM.md                   # This file
logs/                    # Log files (auto-created)
  live_gps.log
  cellular.log
  can_bridge.log
```

### Deprecated Files
- `cellular.py` -- PPP/NDIS approach. Failed. Replaced by cellular_connect.sh (QMI).
- `test_cellular.py` -- Used cellular.py. Use live_gps.py --cellular instead.

### Server (GlobalRTS on Fly.io)
```
GlobalRTS/
  server.js, public/globalui.html, public/CONFIG.js, fly.toml, Dockerfile
```

## Known Issues & Solutions

### Rover goes gray when driving (cell tower handover)
cellular_connect.sh watchdog detects and reconnects within 15-30s. live_gps.py reconnects WebSocket every 5s.

### WebSocket connects through WiFi despite --cellular flag
MUST use `SO_BINDTODEVICE` (requires sudo). `socket.bind((ip, 0))` does NOT work.

### Fly.io multiple instances
`fly scale count 1 --yes` -- server stores state in-memory.

### ModemManager grabs AT port
`sudo systemctl stop ModemManager && sudo systemctl disable ModemManager`

### GPS cold start takes 30-60s
Normal. Needs clear sky. live_gps.py waits 60s then starts anyway.

## Changelog

### 2026-02-11 -- CAN Bus (MCP2515) + STM32 SPI Driver + Enhanced Logging
- Added SPI-CAN bus communication between Pi and STM32 using MCP2515+TJA1050 modules
- STM32: New register-level SPI1 driver (PA5/PA6/PA7/PB6), MCP2515 driver, CAN send/receive FreeRTOS tasks
- STM32: Structured UART logging with [TAG] prefixes: [INIT], [HB], [IMU], [CAN-TX], [CAN-RX], [CMD]
- STM32: Sends heartbeat (0x100), IMU data (0x101/0x102) over CAN at 5Hz
- STM32: Receives and logs navigate/stop/speed commands from Pi
- Pi: New can_bridge.py module (python-can, SocketCAN), new can_setup.sh
- Pi: live_gps.py --can flag integrates CAN bridge for real IMU data and command forwarding
- Pi: Added rotating file logs (logs/live_gps.log, logs/can_bridge.log) with connection/error tracking
- End-to-end: laptop->GlobalRTS->miraeopus->cellular->Pi->CAN->STM32->UART serial print

### CAN Bus Wiring (MCP2515+TJA1050 modules)
Both the Pi and STM32 use identical MCP2515+TJA1050 combo modules (8MHz crystal, 5V, 120ohm termination).

**STM32 side (MCP2515 module #1 via SPI1):**
```
MCP2515 Pin    STM32 Nucleo Pin     Function
-----------    -----------------    --------
VCC            5V (CN7 pin 18)      Power (TJA1050 needs 5V)
GND            GND (CN7 pin 20)     Ground
CS             PB6 (D10)            SPI chip select (GPIO, active low)
SCK            PA5 (D13)            SPI clock
MOSI (SI)      PA7 (D11)            SPI master out
MISO (SO)      PA6 (D12)            SPI master in
INT            not connected        (polled, not interrupt-driven)
```

**Pi side (MCP2515 module #2 via SPI0):**
```
MCP2515 Pin    Raspberry Pi 5 Pin   Function
-----------    -----------------    --------
VCC            5V (pin 2)           Power
GND            GND (pin 6)          Ground
CS             GPIO8/CE0 (pin 24)   SPI chip select
SCK            GPIO11/SCLK (pin 23) SPI clock
MOSI (SI)      GPIO10/MOSI (pin 19) SPI master out
MISO (SO)      GPIO9/MISO (pin 21)  SPI master in
INT            GPIO25 (pin 22)      Interrupt (kernel driver)
```

**CAN bus between modules:**
```
Module #1 (STM32)    Module #2 (Pi)
CANH  <----------->  CANH
CANL  <----------->  CANL
```
- Enable 120ohm termination jumper (J1) on BOTH modules
- Share a common GND between STM32 and Pi

**Pi kernel config (one-time, /boot/firmware/config.txt):**
```
dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
dtoverlay=spi0-0cs
```

**Pi runtime setup (after each reboot, or use can_setup.sh):**
```bash
sudo ip link set can0 up type can bitrate 500000
```

**Quick reference:**
```bash
# Pi: bring up CAN
sudo bash can_setup.sh

# Pi: test CAN standalone
python3 can_bridge.py --send-ping --duration 10

# Pi: run with GPS + cellular + CAN
sudo python3 live_gps.py --cellular --can

# Pi: monitor raw CAN traffic
candump can0

# Pi: send raw CAN frame (ping STM32)
cansend can0 2FF#01

# STM32: watch UART output (serial monitor, 9600 baud)
# You'll see [CAN-RX], [CMD], [HB], [IMU] tagged messages
```

### 2026-02-10 -- Systemd services + file logging
- Added rotating file logs to `logs/` directory for both live_gps.py and cellular_connect.sh
- Created rover-cellular.service and rover-gps.service for auto-start on boot
- live_gps.py logs: GPS positions every 30s, all connections/disconnections, commands received, errors
- cellular_connect.sh logs: QMI session events, signal strength, reconnections

### 2026-02-10 -- SO_BINDTODEVICE fix (the real cellular fix)
socket.bind((ip, 0)) did NOT force traffic through wwan0. Field testing proved WebSocket still went through WiFi. Fixed with SO_BINDTODEVICE (socket option 25) which binds at kernel level. Requires sudo. websockets library gets a raw pre-connected TCP socket (NOT SSL-wrapped -- websockets handles SSL itself on wss:// URIs).

### 2026-02-10 -- cellular_connect.sh v2: Auto-Reconnect Watchdog
QMI data sessions drop during cell tower handovers. Added watchdog loop that pings every 15s and re-runs full QMI setup when connectivity lost.

### 2026-02-09 -- live_gps.py v2: NMEA, cellular --flag, latency
Added NMEA reader (background thread on /dev/ttyUSB1) for HDOP/PDOP/VDOP/sats. Added --cellular flag. Added latency measurement (WS ping/pong + command age). Added --no-nmea flag.

### 2026-02-09 -- Initial cellular_connect.sh + live_gps.py v1
Created QMI-based cellular script. Initial GPS over WiFi confirmed working.

### IMPORTANT NOTES KEEP THIS AT THE BOTTOM OF THIS MD FILE
1. For the love of god do not rename the file or folder other than what was already given and if you want to name something new, ask first
2. Do not use emojis for any print statements for files meant to go into a linux machine like Raspi, it can't encode the emoji properly.
