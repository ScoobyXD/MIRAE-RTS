# GlobalRTS Tracker - nRF9151 Firmware

Unified firmware for the nRF9151-DK that sends GNSS telemetry to GlobalRTS server and receives commands via cellular.

## Features

- **GNSS tracking** - Continuous GPS fix with full PVT data (lat, lon, alt, speed, heading, DOPs)
- **Cellular connectivity** - LTE-M with PSM for power efficiency
- **HTTPS telemetry** - Posts JSON to `https://miraeopus.com/api/telemetry` every second
- **Command polling** - Gets commands from server and displays them on serial
- **TLS security** - Let's Encrypt root CA included for HTTPS

## Hardware Requirements

- nRF9151-DK development kit
- LTE antenna connected
- GNSS antenna connected (or clear sky view)
- USB cable for power and serial output

## Building

### Prerequisites

1. Install nRF Connect SDK v2.5.0 or later
2. Install Zephyr toolchain

### Build Commands

```bash
# Navigate to project
cd nRF9151/globalrts_tracker

# Build for nRF9151-DK
west build -b nrf9151dk/nrf9151/ns

# Flash to device
west flash
```

## Configuration

Edit `src/main.c` to change:

```c
#define ROVER_ID        "nrf9151-001"       // Unique ID for your rover
#define ROVER_NAME      "nRF9151 Tracker"   // Display name in GlobalRTS
#define SERVER_HOST     "miraeopus.com"     // Your GlobalRTS server
```

## Serial Output

Connect to the serial port (usually `/dev/ttyACM0` on Linux or COM port on Windows) at 115200 baud.

You'll see:
1. Initialization messages
2. LTE connection status
3. GNSS search status (satellite count)
4. Once fix acquired: position data and telemetry status
5. When commands arrive: boxed command notifications

Example output:
```
==========================================
  GlobalRTS Tracker - nRF9151 Firmware
  Rover ID: nrf9151-001
  Server:   miraeopus.com
==========================================

[00:00:01] Initializing modem...
[00:00:02] Connecting to LTE network...
[00:00:15] LTE connected successfully
[00:00:16] GNSS started, waiting for fix...

[GNSS] Searching... Satellites tracked: 5

=== GlobalRTS Tracker ===
Status: GNSS FIX VALID
-------------------------
Latitude:    34.052200
Longitude:   -118.243700
Altitude:    125.3 m
Accuracy:    3.2 m
Speed:       0.00 m/s
Heading:     45.2 deg
PDOP:        1.8
HDOP:        1.2
VDOP:        1.4
-------------------------
Telemetry #42 sent to miraeopus.com

========================================
  RECEIVED COMMAND: navigate
  Target: 34.053100, -118.244500
========================================
```

## Data Format

### Telemetry (POST /api/telemetry)

```json
{
    "id": "nrf9151-001",
    "name": "nRF9151 Tracker",
    "type": "robot",
    "lat": 34.052200,
    "lon": -118.243700,
    "alt": 125.3,
    "speed": 0.5,
    "heading": 45.2,
    "accuracy": 3.2,
    "altAccuracy": 5.1,
    "speedAccuracy": 0.3,
    "headingAccuracy": 2.5,
    "vSpeed": 0.0,
    "vSpeedAccuracy": 0.5,
    "pdop": 1.8,
    "hdop": 1.2,
    "vdop": 1.4,
    "tdop": 1.1,
    "battery": 100,
    "status": "online"
}
```

### Commands (GET /api/commands/{roverId})

The server returns commands queued by the GlobalRTS browser UI:

```json
{
    "commands": [
        {
            "id": 1,
            "type": "navigate",
            "payload": {
                "latitude": 34.0531,
                "longitude": -118.2445
            },
            "timestamp": 1704067200000
        }
    ]
}
```

Supported command types:
- `navigate` - Go to coordinates (payload: latitude, longitude)
- `stop` - Stop immediately (no payload)
- `setSpeed` - Set max speed (payload: speed in m/s)

## Power Consumption

- LTE-M with PSM enabled
- GNSS in continuous tracking mode
- Estimated: ~15mA average with 1Hz updates

## Troubleshooting

### No LTE connection
- Check antenna is connected
- Verify SIM card is inserted and activated
- Check cellular coverage in your area

### No GNSS fix
- Move to area with clear sky view
- GNSS antenna must have clear line of sight to sky
- Cold start can take 30-60 seconds

### HTTPS failures
- Verify server is running and accessible
- Check DNS resolution is working
- TLS certificate might need updating if expired

## Files

```
globalrts_tracker/
├── CMakeLists.txt     # Build configuration
├── prj.conf           # Kconfig options
├── README.md          # This file
└── src/
    └── main.c         # Main firmware source
```

## Future Enhancements

- [ ] Add IMU (LSM6DS3) support via I2C/SPI
- [ ] Add motor encoder reading via GPIO
- [ ] Implement motor control response to navigate commands
- [ ] Add battery monitoring via ADC
- [ ] Implement A-GNSS for faster fix times
- [ ] Add command acknowledgment back to server
