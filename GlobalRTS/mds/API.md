# GlobalRTS Server API

**Base URL:** `https://globalrts.fly.dev` (or your custom domain)

## Overview

The server connects rovers (via HTTP) to GlobalRTS browsers (via WebSocket).

```
Rover ──HTTP POST──> Server ──WebSocket──> Browser
Rover <──HTTP GET─── Server <──WebSocket── Browser
```

---

## Rover API (HTTP)

### POST /api/telemetry

Send telemetry data from rover to server. Call this ~1Hz for GPS/IMU, faster for encoders if needed.

**Request:**
```json
{
    "id": "rover-001",           // REQUIRED: unique rover identifier
    "name": "MyRover",           // Display name (default: "Rover")
    "type": "robot",             // Device type: robot, drone, vehicle (default: "robot")
    
    // GPS Data
    "lat": 34.0522,              // Latitude (required for map display)
    "lon": -118.2437,            // Longitude (required for map display)
    "alt": 100.0,                // Altitude in meters
    "speed": 1.5,                // Speed in m/s
    "heading": 45.0,             // Heading in degrees (0-360)
    "accuracy": 2.5,             // Position accuracy in meters
    "altAccuracy": 5.0,          // Altitude accuracy
    "speedAccuracy": 0.5,        // Speed accuracy
    "headingAccuracy": 2.0,      // Heading accuracy
    "vSpeed": 0.0,               // Vertical speed
    "vSpeedAccuracy": 0.5,       // Vertical speed accuracy
    "pdop": 1.5,                 // Position DOP
    "hdop": 1.2,                 // Horizontal DOP
    "vdop": 1.8,                 // Vertical DOP
    "tdop": 1.0,                 // Time DOP
    
    // IMU Data (raw 16-bit signed integers from LSM6DS3)
    "ax": 100,                   // Accelerometer X
    "ay": -50,                   // Accelerometer Y
    "az": 16384,                 // Accelerometer Z (~1g at ±2g range)
    "gx": 10,                    // Gyroscope X
    "gy": -5,                    // Gyroscope Y
    "gz": 2,                     // Gyroscope Z
    
    // Encoder Data
    "encL": 12345,               // Left encoder count
    "encR": 12340,               // Right encoder count
    "encLVel": 100,              // Left encoder velocity (counts/sec)
    "encRVel": 98,               // Right encoder velocity
    
    // Status
    "battery": 85,               // Battery percentage
    "status": "online"           // Status: online, moving, idle, error
}
```

**Response:**
```json
{ "ok": true }
```

**Minimal Example (just GPS):**
```json
{
    "id": "rover-001",
    "lat": 34.0522,
    "lon": -118.2437
}
```

---

### GET /api/commands/{roverId}

Poll for pending commands. Call this every 1-2 seconds.

**Response:**
```json
{
    "commands": [
        {
            "id": 1,
            "type": "navigate",
            "payload": {
                "latitude": 34.0525,
                "longitude": -118.2440,
                "altitude": 0
            },
            "timestamp": 1704067200000
        },
        {
            "id": 2,
            "type": "stop",
            "payload": {},
            "timestamp": 1704067205000
        }
    ]
}
```

**Command Types:**
- `navigate` - Go to coordinates. Payload: `{ latitude, longitude, altitude }`
- `stop` - Stop immediately. Payload: `{}`
- `setSpeed` - Set max speed. Payload: `{ speed: 1.5 }`
- Custom commands can be added as needed

**Important:** Commands are cleared after retrieval. If you get them, you own them.

---

### GET /api/rovers

Get all known rovers (for debugging).

**Response:**
```json
[
    {
        "id": "rover-001",
        "name": "MyRover",
        "lat": 34.0522,
        "lon": -118.2437,
        "status": "online",
        "lastSeen": 1704067200000
    }
]
```

---

### GET /api/health

Server health check.

**Response:**
```json
{
    "status": "ok",
    "rovers": 1,
    "browsers": 2,
    "uptime": 3600.5
}
```

---

## nRF9151 Implementation Notes

### Minimal C Pseudocode

```c
// Send telemetry (call every 1 second)
void send_telemetry(void) {
    char json[512];
    snprintf(json, sizeof(json),
        "{\"id\":\"%s\",\"lat\":%.6f,\"lon\":%.6f,\"alt\":%.1f,"
        "\"speed\":%.2f,\"heading\":%.1f,"
        "\"ax\":%d,\"ay\":%d,\"az\":%d,"
        "\"gx\":%d,\"gy\":%d,\"gz\":%d,"
        "\"encL\":%d,\"encR\":%d,\"battery\":%d,\"status\":\"online\"}",
        ROVER_ID, gps_lat, gps_lon, gps_alt,
        gps_speed, gps_heading,
        imu_ax, imu_ay, imu_az,
        imu_gx, imu_gy, imu_gz,
        enc_left, enc_right, battery_pct
    );
    
    http_post("https://globalrts.fly.dev/api/telemetry", json);
}

// Poll for commands (call every 1-2 seconds)
void poll_commands(void) {
    char url[128];
    snprintf(url, sizeof(url), 
        "https://globalrts.fly.dev/api/commands/%s", ROVER_ID);
    
    char response[1024];
    http_get(url, response, sizeof(response));
    
    // Parse JSON and execute commands
    // Look for "type":"navigate" with latitude/longitude
}
```

### Data Rate Estimation

At 1 telemetry packet per second:
- JSON size: ~300-500 bytes
- HTTP overhead: ~200 bytes headers
- Total: ~700 bytes/second = ~2.5 KB/hour

Very light on cellular data.

---

## WebSocket API (for reference)

Browsers connect via WebSocket. Message format:

**Server → Browser:**
- `devices:list` - Initial list of all rovers
- `device:online` - New rover connected
- `device:update` - Rover telemetry update
- `device:offline` - Rover went offline (no data for 10s)

**Browser → Server:**
- `getDevices` - Request current rover list
- `sendCommand` - Send command to rover
  ```json
  {
      "type": "sendCommand",
      "data": {
          "deviceId": "rover-001",
          "commandType": "navigate",
          "payload": { "latitude": 34.05, "longitude": -118.24 }
      }
  }
  ```
