#!/usr/bin/env python3
"""
GlobalRTS Rover Client for Raspberry Pi

Connects rover to GlobalRTS server using:
- WebSocket (primary): Low latency, bidirectional, instant commands
- HTTP (fallback): Works when WebSocket fails

Architecture:
    Pi (this code) <--WebSocket/HTTP--> Server <--WebSocket--> Browser/GlobalRTS

Usage:
    python3 rover_client.py [--server wss://miraeopus.com] [--rover-id rover-001]

Dependencies:
    pip3 install websockets aiohttp
"""

import asyncio
import json
import time
import argparse
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Callable, Dict, Any
from enum import Enum

# Optional imports - graceful degradation
try:
    import websockets
    from websockets.exceptions import ConnectionClosed, WebSocketException
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    print("⚠️  websockets not installed. WebSocket disabled. pip3 install websockets")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    print("⚠️  aiohttp not installed. Using urllib fallback. pip3 install aiohttp")

# Fallback HTTP using standard library
import urllib.request
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('rover')


class ConnectionMode(Enum):
    WEBSOCKET = "websocket"
    HTTP = "http"
    DISCONNECTED = "disconnected"


@dataclass
class Telemetry:
    """Rover telemetry data matching GlobalRTS API format"""
    id: str
    name: str = "Rover"
    type: str = "robot"
    
    # GPS Data
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0
    speed: float = 0.0
    heading: float = 0.0
    accuracy: float = 0.0
    altAccuracy: float = 0.0
    speedAccuracy: float = 0.0
    headingAccuracy: float = 0.0
    pdop: float = 0.0
    hdop: float = 0.0
    vdop: float = 0.0
    tdop: float = 0.0
    vSpeed: float = 0.0
    vSpeedAccuracy: float = 0.0
    
    # IMU Data (raw 16-bit values from LSM6DS3)
    ax: int = 0
    ay: int = 0
    az: int = 0
    gx: int = 0
    gy: int = 0
    gz: int = 0
    
    # Encoder Data
    encL: int = 0
    encR: int = 0
    encLVel: int = 0
    encRVel: int = 0
    
    # Status
    battery: int = 100
    status: str = "online"
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass  
class Command:
    """Command received from GlobalRTS"""
    id: int
    type: str
    payload: Dict[str, Any]
    timestamp: int
    
    @classmethod
    def from_dict(cls, d: dict) -> 'Command':
        return cls(
            id=d.get('id', 0),
            type=d.get('type', ''),
            payload=d.get('payload', {}),
            timestamp=d.get('timestamp', 0)
        )


class RoverClient:
    """
    Main rover client - handles communication with GlobalRTS server.
    
    Prioritizes WebSocket for low latency, falls back to HTTP polling.
    """
    
    def __init__(
        self,
        server_url: str,
        rover_id: str,
        rover_name: str = "Rover",
        on_command: Optional[Callable[[Command], None]] = None,
        telemetry_interval: float = 1.0,
        command_poll_interval: float = 1.0,
        reconnect_delay: float = 5.0,
    ):
        """
        Args:
            server_url: Base server URL (e.g., "wss://miraeopus.com" or "https://miraeopus.com")
            rover_id: Unique rover identifier
            rover_name: Display name for GlobalRTS UI
            on_command: Callback when command received. Signature: fn(Command) -> None
            telemetry_interval: Seconds between telemetry sends (default 1.0)
            command_poll_interval: Seconds between HTTP command polls (only used in HTTP mode)
            reconnect_delay: Seconds to wait before reconnecting after disconnect
        """
        # Parse server URL
        self.server_url = server_url.rstrip('/')
        if self.server_url.startswith('wss://'):
            self.ws_url = self.server_url
            self.http_url = self.server_url.replace('wss://', 'https://')
        elif self.server_url.startswith('ws://'):
            self.ws_url = self.server_url
            self.http_url = self.server_url.replace('ws://', 'http://')
        elif self.server_url.startswith('https://'):
            self.ws_url = self.server_url.replace('https://', 'wss://')
            self.http_url = self.server_url
        elif self.server_url.startswith('http://'):
            self.ws_url = self.server_url.replace('http://', 'ws://')
            self.http_url = self.server_url
        else:
            # Assume https
            self.ws_url = f"wss://{self.server_url}"
            self.http_url = f"https://{self.server_url}"
        
        self.rover_id = rover_id
        self.rover_name = rover_name
        self.on_command = on_command
        self.telemetry_interval = telemetry_interval
        self.command_poll_interval = command_poll_interval
        self.reconnect_delay = reconnect_delay
        
        # State
        self.mode = ConnectionMode.DISCONNECTED
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self._current_telemetry = Telemetry(id=rover_id, name=rover_name)
        self._telemetry_lock = asyncio.Lock()
        
        # Stats
        self.stats = {
            'telemetry_sent': 0,
            'commands_received': 0,
            'ws_connects': 0,
            'ws_disconnects': 0,
            'http_fallbacks': 0,
        }
    
    def update_telemetry(self, **kwargs):
        """
        Thread-safe telemetry update. Call this from your sensor reading code.
        
        Example:
            client.update_telemetry(lat=34.0522, lon=-118.2437, speed=1.5)
        """
        for key, value in kwargs.items():
            if hasattr(self._current_telemetry, key):
                setattr(self._current_telemetry, key, value)
    
    def update_gps(self, lat: float, lon: float, alt: float = 0, 
                   speed: float = 0, heading: float = 0, accuracy: float = 0,
                   hdop: float = 0, vdop: float = 0, pdop: float = 0):
        """Convenience method to update all GPS fields at once"""
        self.update_telemetry(
            lat=lat, lon=lon, alt=alt,
            speed=speed, heading=heading, accuracy=accuracy,
            hdop=hdop, vdop=vdop, pdop=pdop
        )
    
    def update_imu(self, ax: int, ay: int, az: int, gx: int, gy: int, gz: int):
        """Convenience method to update all IMU fields at once"""
        self.update_telemetry(ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz)
    
    def update_encoders(self, left: int, right: int, left_vel: int = 0, right_vel: int = 0):
        """Convenience method to update encoder fields"""
        self.update_telemetry(encL=left, encR=right, encLVel=left_vel, encRVel=right_vel)
    
    async def start(self):
        """Start the rover client. Runs until stop() is called."""
        self.running = True
        log.info(f"🚀 Rover client starting: {self.rover_id}")
        log.info(f"   WebSocket: {self.ws_url}")
        log.info(f"   HTTP:      {self.http_url}")
        
        while self.running:
            try:
                if HAS_WEBSOCKETS:
                    await self._run_websocket()
                else:
                    log.warning("WebSocket not available, using HTTP only")
                    await self._run_http_only()
            except Exception as e:
                log.error(f"Connection error: {e}")
            
            if self.running:
                log.info(f"Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
    
    def stop(self):
        """Signal the client to stop."""
        self.running = False
        log.info("🛑 Rover client stopping")
    
    async def _run_websocket(self):
        """WebSocket main loop - primary mode"""
        log.info(f"🔌 Connecting WebSocket to {self.ws_url}/rover...")
        
        try:
            # Use /rover endpoint for rover WebSocket connections
            async with websockets.connect(
                f"{self.ws_url}/rover",
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
                # Additional options for stability
                max_size=2**20,  # 1MB max message
                compression=None,  # Disable compression for lower latency
            ) as ws:
                self.ws = ws
                self.mode = ConnectionMode.WEBSOCKET
                self.stats['ws_connects'] += 1
                log.info("✅ WebSocket connected!")
                
                # Send identification
                identify_msg = json.dumps({
                    'type': 'rover:identify',
                    'data': {
                        'id': self.rover_id,
                        'name': self.rover_name,
                        'type': 'robot'
                    }
                })
                log.debug(f"Sending identify: {identify_msg}")
                await ws.send(identify_msg)
                
                # Wait for acknowledgment before starting telemetry
                try:
                    ack_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    ack_data = json.loads(ack_msg)
                    if ack_data.get('type') == 'ack':
                        log.info(f"✅ Server acknowledged: {ack_data.get('data', {}).get('message', 'OK')}")
                    else:
                        log.warning(f"Unexpected first message: {ack_data.get('type')}")
                        # Process it anyway
                        await self._handle_server_message(ack_data)
                except asyncio.TimeoutError:
                    log.warning("No ack received, proceeding anyway")
                
                # Run telemetry sender and message receiver concurrently
                # Use return_exceptions=True so one failing doesn't kill the other
                results = await asyncio.gather(
                    self._ws_telemetry_loop(ws),
                    self._ws_receive_loop(ws),
                    return_exceptions=True
                )
                
                # Log any exceptions that occurred
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        task_name = ['telemetry_loop', 'receive_loop'][i]
                        log.error(f"{task_name} exception: {result}")
                        
        except ConnectionClosed as e:
            log.warning(f"WebSocket closed: code={e.code} reason={e.reason}")
            self.stats['ws_disconnects'] += 1
        except WebSocketException as e:
            log.error(f"WebSocket error: {type(e).__name__}: {e}")
        except OSError as e:
            log.error(f"Network error: {e}")
        except Exception as e:
            log.error(f"WebSocket unexpected error: {type(e).__name__}: {e}")
            import traceback
            log.debug(traceback.format_exc())
        finally:
            self.ws = None
            self.mode = ConnectionMode.DISCONNECTED
    
    async def _ws_telemetry_loop(self, ws):
        """Send telemetry at regular intervals over WebSocket"""
        log.info(f"📡 Telemetry loop started (interval: {self.telemetry_interval}s)")
        
        while self.running and not ws.close_code:
            try:
                msg = {
                    'type': 'rover:telemetry',
                    'data': asdict(self._current_telemetry)
                }
                await ws.send(json.dumps(msg))
                self.stats['telemetry_sent'] += 1
                log.debug(f"📡 Telemetry #{self.stats['telemetry_sent']} sent via WS")
            except ConnectionClosed as e:
                log.warning(f"Telemetry send failed - connection closed: {e.code}")
                break
            except Exception as e:
                log.error(f"Telemetry send error: {type(e).__name__}: {e}")
                break
            
            await asyncio.sleep(self.telemetry_interval)
        
        log.info("📡 Telemetry loop ended")
    
    async def _ws_receive_loop(self, ws):
        """Receive and process messages from server over WebSocket"""
        log.info("📥 Receive loop started")
        
        while self.running and not ws.close_code:
            try:
                message = await ws.recv()
                log.debug(f"📥 Received: {message[:100]}...")
                data = json.loads(message)
                await self._handle_server_message(data)
            except ConnectionClosed as e:
                log.warning(f"Receive loop - connection closed: {e.code}")
                break
            except json.JSONDecodeError as e:
                log.warning(f"Invalid JSON from server: {e}")
            except Exception as e:
                log.error(f"Receive error: {type(e).__name__}: {e}")
                break
        
        log.info("📥 Receive loop ended")
    
    async def _handle_server_message(self, msg: dict):
        """Process a message from the server"""
        msg_type = msg.get('type', '')
        data = msg.get('data', {})
        
        if msg_type == 'command':
            # Single command
            cmd = Command.from_dict(data)
            self._dispatch_command(cmd)
        
        elif msg_type == 'commands':
            # Multiple commands
            for cmd_data in data.get('commands', []):
                cmd = Command.from_dict(cmd_data)
                self._dispatch_command(cmd)
        
        elif msg_type == 'ack':
            log.debug(f"Server ack: {data}")
        
        elif msg_type == 'error':
            log.error(f"Server error: {data}")
        
        else:
            log.debug(f"Unknown message type: {msg_type}")
    
    def _dispatch_command(self, cmd: Command):
        """Dispatch a command to the callback"""
        self.stats['commands_received'] += 1
        log.info(f"📥 Command received: {cmd.type} (id={cmd.id})")
        
        if self.on_command:
            try:
                self.on_command(cmd)
            except Exception as e:
                log.error(f"Command callback error: {e}")
    
    async def _run_http_only(self):
        """HTTP-only mode - fallback when WebSocket unavailable"""
        self.mode = ConnectionMode.HTTP
        self.stats['http_fallbacks'] += 1
        log.info("📡 Running in HTTP-only mode")
        
        while self.running:
            try:
                # Send telemetry
                await self._http_send_telemetry()
                
                # Poll for commands
                await self._http_poll_commands()
                
            except Exception as e:
                log.error(f"HTTP error: {e}")
                await asyncio.sleep(self.reconnect_delay)
                continue
            
            await asyncio.sleep(self.telemetry_interval)
    
    async def _http_send_telemetry(self):
        """Send telemetry via HTTP POST"""
        url = f"{self.http_url}/api/telemetry"
        payload = self._current_telemetry.to_json().encode('utf-8')
        
        if HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=payload, 
                                        headers={'Content-Type': 'application/json'},
                                        timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        self.stats['telemetry_sent'] += 1
                        log.debug(f"📡 Telemetry sent via HTTP")
                    else:
                        log.warning(f"HTTP telemetry error: {resp.status}")
        else:
            # Fallback to urllib (blocking, but works)
            await asyncio.get_event_loop().run_in_executor(
                None, self._http_post_sync, url, payload
            )
    
    def _http_post_sync(self, url: str, payload: bytes):
        """Synchronous HTTP POST using urllib"""
        req = urllib.request.Request(
            url, 
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    self.stats['telemetry_sent'] += 1
        except urllib.error.URLError as e:
            log.warning(f"HTTP POST error: {e}")
    
    async def _http_poll_commands(self):
        """Poll for commands via HTTP GET"""
        url = f"{self.http_url}/api/commands/{self.rover_id}"
        
        try:
            if HAS_AIOHTTP:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for cmd_data in data.get('commands', []):
                                cmd = Command.from_dict(cmd_data)
                                self._dispatch_command(cmd)
            else:
                # Fallback to urllib
                await asyncio.get_event_loop().run_in_executor(
                    None, self._http_get_commands_sync, url
                )
        except Exception as e:
            log.debug(f"Command poll error: {e}")
    
    def _http_get_commands_sync(self, url: str):
        """Synchronous HTTP GET for commands"""
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    for cmd_data in data.get('commands', []):
                        cmd = Command.from_dict(cmd_data)
                        self._dispatch_command(cmd)
        except Exception as e:
            log.debug(f"HTTP GET error: {e}")


# ============================================
# EXAMPLE USAGE / TEST MODE
# ============================================

async def test_mode(client: RoverClient):
    """
    Test mode - simulates GPS and sensor data.
    Use this to verify server connectivity before integrating real sensors.
    """
    import random
    
    # Start position: Los Angeles
    lat = 12.1234
    lon = 123.3214
    heading = 1.0
    enc_left = 2
    enc_right = 3
    
    def handle_command(cmd: Command):
        nonlocal lat, lon
        log.info(f"🎯 Handling command: {cmd.type}")
        if cmd.type == 'navigate':
            target_lat = cmd.payload.get('latitude', lat)
            target_lon = cmd.payload.get('longitude', lon)
            log.info(f"   Navigate to: {target_lat:.6f}, {target_lon:.6f}")
            # Simulate movement towards target
            lat += (target_lat - lat) * 0.1
            lon += (target_lon - lon) * 0.1
        elif cmd.type == 'stop':
            log.info("   STOP command received!")
    
    client.on_command = handle_command
    
    # Start client in background
    client_task = asyncio.create_task(client.start())
    
    # Simulate sensor updates
    try:
        while client.running:
            # Simulate GPS drift
            lat += (random.random() - 0.5) * 0.00005
            lon += (random.random() - 0.5) * 0.00005
            heading = (heading + (random.random() - 0.5) * 5) % 360
            speed = 0.5 + random.random() * 0.5
            
            # Simulate encoder counts
            enc_left += int(random.random() * 10)
            enc_right += int(random.random() * 10)
            
            # Update telemetry
            client.update_gps(
                lat=lat, lon=lon, alt=100.0,
                speed=speed, heading=heading, accuracy=2.5,
                hdop=1.2
            )
            client.update_imu(
                ax=int((random.random() - 0.5) * 1000),
                ay=int((random.random() - 0.5) * 1000),
                az=16000 + int(random.random() * 500),  # ~1g
                gx=int((random.random() - 0.5) * 100),
                gy=int((random.random() - 0.5) * 100),
                gz=int((random.random() - 0.5) * 100),
            )
            client.update_encoders(enc_left, enc_right)
            client.update_telemetry(battery=85)
            
            # Print status
            mode_emoji = "🔌" if client.mode == ConnectionMode.WEBSOCKET else "📡"
            print(f"\r{mode_emoji} {lat:.6f}, {lon:.6f} | H:{heading:5.1f}° | "
                  f"TX:{client.stats['telemetry_sent']} RX:{client.stats['commands_received']}  ", 
                  end='', flush=True)
            
            await asyncio.sleep(0.5)  # Update sensors faster than telemetry
    except asyncio.CancelledError:
        pass
    finally:
        client.stop()
        await client_task


def main():
    parser = argparse.ArgumentParser(description='GlobalRTS Rover Client')
    parser.add_argument('--server', '-s', default='https://miraeopus.com',
                        help='Server URL (default: https://miraeopus.com)')
    parser.add_argument('--rover-id', '-i', default='rover-001',
                        help='Rover ID (default: rover-001)')
    parser.add_argument('--rover-name', '-n', default='RasPi Rover',
                        help='Rover display name')
    parser.add_argument('--test', '-t', action='store_true',
                        help='Run in test mode with simulated sensors')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Telemetry interval in seconds (default: 1.0)')
    parser.add_argument('--http-only', action='store_true',
                        help='Force HTTP mode (disable WebSocket)')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.http_only:
        global HAS_WEBSOCKETS
        HAS_WEBSOCKETS = False
    
    client = RoverClient(
        server_url=args.server,
        rover_id=args.rover_id,
        rover_name=args.rover_name,
        telemetry_interval=args.interval,
    )
    
    try:
        if args.test:
            asyncio.run(test_mode(client))
        else:
            # Production mode - just start the client
            # User code should call client.update_*() methods
            asyncio.run(client.start())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")


if __name__ == '__main__':
    main()
