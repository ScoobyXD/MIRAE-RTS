#!/usr/bin/env python3
"""
GlobalRTS Rover - Main Application for Raspberry Pi

Integrates:
- SIM7600G-H HAT: GPS + 4G LTE connectivity
- STM32L476RG: Motor control via UART
- GlobalRTS Server: WebSocket/HTTP communication

Hardware Connections:
    Pi GPIO 14 (TX) -> STM32 UART RX
    Pi GPIO 15 (RX) -> STM32 UART TX
    SIM7600G-H HAT on Pi GPIO (serial via /dev/ttyUSB2 or /dev/ttyAMA0)

Usage:
    python3 main.py --server wss://miraeopus.com --rover-id rover-001
"""

import asyncio
import argparse
import logging
import signal
import sys
import math
from dataclasses import dataclass
from typing import Optional

# Import our rover client
from rover_client import RoverClient, Command, ConnectionMode

# Hardware drivers (will gracefully degrade if not available)
try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("⚠️  pyserial not installed. UART disabled. pip3 install pyserial")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('rover_main')


# ============================================
# GPS PARSER (SIM7600G-H via AT commands)
# ============================================

@dataclass
class GPSData:
    """Parsed GPS data from SIM7600G-H"""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    speed: float = 0.0      # m/s
    heading: float = 0.0    # degrees
    hdop: float = 0.0
    fix_quality: int = 0
    satellites: int = 0
    timestamp: str = ""
    valid: bool = False


class SIM7600GPS:
    """
    GPS interface for SIM7600G-H HAT.
    
    The SIM7600 provides GPS via AT commands or NMEA sentences.
    This class uses AT+CGPSINFO for simplicity.
    """
    
    def __init__(self, port: str = '/dev/ttyUSB2', baudrate: int = 115200):
        """
        Args:
            port: Serial port for SIM7600. Common options:
                  - /dev/ttyUSB2 (USB connection)
                  - /dev/ttyAMA0 (GPIO UART, need to disable console)
                  - /dev/serial0 (symlink to active UART)
            baudrate: Typically 115200 for SIM7600
        """
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self._last_data = GPSData()
    
    def open(self) -> bool:
        """Open serial connection to SIM7600"""
        if not HAS_SERIAL:
            log.warning("pyserial not available, GPS disabled")
            return False
        
        try:
            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=1.0
            )
            log.info(f"📡 GPS opened: {self.port}")
            
            # Initialize GPS
            self._send_at('AT')  # Wake up
            self._send_at('AT+CGPS=1')  # Enable GPS
            return True
            
        except serial.SerialException as e:
            log.error(f"Failed to open GPS port: {e}")
            return False
    
    def close(self):
        """Close serial connection"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            log.info("📡 GPS closed")
    
    def _send_at(self, command: str, timeout: float = 1.0) -> str:
        """Send AT command and return response"""
        if not self.serial:
            return ""
        
        self.serial.write(f"{command}\r\n".encode())
        self.serial.flush()
        
        response = ""
        end_time = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end_time:
            if self.serial.in_waiting:
                response += self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
                if 'OK' in response or 'ERROR' in response:
                    break
        
        return response
    
    def read(self) -> GPSData:
        """
        Read current GPS position using AT+CGPSINFO.
        
        Response format:
        +CGPSINFO: lat,N/S,lon,E/W,date,time,alt,speed,course
        Example:
        +CGPSINFO: 3405.123456,N,11814.654321,W,010124,123456.0,100.0,0.5,45.0
        """
        if not self.serial:
            return self._last_data
        
        try:
            response = self._send_at('AT+CGPSINFO')
            
            # Parse response
            if '+CGPSINFO:' in response:
                # Extract the data part
                line = response.split('+CGPSINFO:')[1].split('\r')[0].strip()
                
                if line and line != ',,,,,,,,':
                    parts = line.split(',')
                    if len(parts) >= 9:
                        # Parse latitude (DDMM.MMMMMM)
                        lat_raw = float(parts[0]) if parts[0] else 0
                        lat_deg = int(lat_raw / 100)
                        lat_min = lat_raw - (lat_deg * 100)
                        latitude = lat_deg + (lat_min / 60)
                        if parts[1] == 'S':
                            latitude = -latitude
                        
                        # Parse longitude (DDDMM.MMMMMM)
                        lon_raw = float(parts[2]) if parts[2] else 0
                        lon_deg = int(lon_raw / 100)
                        lon_min = lon_raw - (lon_deg * 100)
                        longitude = lon_deg + (lon_min / 60)
                        if parts[3] == 'W':
                            longitude = -longitude
                        
                        self._last_data = GPSData(
                            latitude=latitude,
                            longitude=longitude,
                            altitude=float(parts[6]) if parts[6] else 0.0,
                            speed=float(parts[7]) * 0.514444 if parts[7] else 0.0,  # knots to m/s
                            heading=float(parts[8]) if parts[8] else 0.0,
                            timestamp=f"{parts[4]}-{parts[5]}",
                            valid=True
                        )
                else:
                    self._last_data.valid = False
            
        except Exception as e:
            log.error(f"GPS read error: {e}")
            self._last_data.valid = False
        
        return self._last_data


# ============================================
# STM32 UART COMMUNICATION
# ============================================

@dataclass
class STM32Telemetry:
    """Telemetry data from STM32"""
    encoder_left: int = 0
    encoder_right: int = 0
    encoder_left_vel: int = 0
    encoder_right_vel: int = 0
    ax: int = 0
    ay: int = 0
    az: int = 0
    gx: int = 0
    gy: int = 0
    gz: int = 0
    valid: bool = False


class STM32Interface:
    """
    UART interface to STM32L476RG motor controller.
    
    Protocol:
        Pi -> STM32: "HDG:285.3,SPD:1.50\n"
        STM32 -> Pi: "ENC:1234,5678,VEL:100,98,IMU:100,-50,16384,10,-5,2\n"
    """
    
    def __init__(self, port: str = '/dev/ttyAMA0', baudrate: int = 115200):
        """
        Args:
            port: UART port to STM32
                  - /dev/ttyAMA0 (GPIO 14/15 on Pi 4)
                  - /dev/serial0 (symlink)
            baudrate: Match STM32 configuration (typically 115200)
        """
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self._last_telemetry = STM32Telemetry()
        self._read_buffer = ""
    
    def open(self) -> bool:
        """Open UART connection to STM32"""
        if not HAS_SERIAL:
            log.warning("pyserial not available, STM32 UART disabled")
            return False
        
        try:
            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=0.1  # Non-blocking reads
            )
            log.info(f"🔌 STM32 UART opened: {self.port}")
            return True
            
        except serial.SerialException as e:
            log.error(f"Failed to open STM32 UART: {e}")
            return False
    
    def close(self):
        """Close UART connection"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            log.info("🔌 STM32 UART closed")
    
    def send_command(self, heading: float, speed: float):
        """
        Send navigation command to STM32.
        
        Args:
            heading: Target heading in degrees (0-360)
            speed: Target speed in m/s
        """
        if not self.serial:
            return
        
        # Format: "HDG:285.3,SPD:1.50\n"
        cmd = f"HDG:{heading:.1f},SPD:{speed:.2f}\n"
        try:
            self.serial.write(cmd.encode())
            self.serial.flush()
            log.debug(f"→ STM32: {cmd.strip()}")
        except serial.SerialException as e:
            log.error(f"STM32 send error: {e}")
    
    def send_stop(self):
        """Emergency stop - zero speed"""
        self.send_command(0, 0)
    
    def read_telemetry(self) -> STM32Telemetry:
        """
        Read and parse telemetry from STM32.
        
        Expected format:
        "ENC:1234,5678,VEL:100,98,IMU:100,-50,16384,10,-5,2\n"
        """
        if not self.serial:
            return self._last_telemetry
        
        try:
            # Read available data
            if self.serial.in_waiting:
                self._read_buffer += self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
            
            # Process complete lines
            while '\n' in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split('\n', 1)
                line = line.strip()
                
                if line.startswith('ENC:'):
                    self._parse_telemetry(line)
        
        except serial.SerialException as e:
            log.error(f"STM32 read error: {e}")
        
        return self._last_telemetry
    
    def _parse_telemetry(self, line: str):
        """Parse telemetry line from STM32"""
        try:
            # Format: "ENC:1234,5678,VEL:100,98,IMU:100,-50,16384,10,-5,2"
            parts = {}
            for segment in line.split(','):
                if ':' in segment:
                    key, val = segment.split(':', 1)
                    parts[key] = val
                else:
                    # Continuation of previous key's values
                    pass
            
            # Parse encoder counts
            if 'ENC' in parts:
                enc_parts = parts['ENC'].split(',')
                if len(enc_parts) >= 2:
                    self._last_telemetry.encoder_left = int(enc_parts[0])
                    self._last_telemetry.encoder_right = int(enc_parts[1])
            
            # Parse velocities
            if 'VEL' in parts:
                vel_parts = parts['VEL'].split(',')
                if len(vel_parts) >= 2:
                    self._last_telemetry.encoder_left_vel = int(vel_parts[0])
                    self._last_telemetry.encoder_right_vel = int(vel_parts[1])
            
            # Parse IMU (ax,ay,az,gx,gy,gz)
            if 'IMU' in parts:
                imu_parts = parts['IMU'].split(',')
                if len(imu_parts) >= 6:
                    self._last_telemetry.ax = int(imu_parts[0])
                    self._last_telemetry.ay = int(imu_parts[1])
                    self._last_telemetry.az = int(imu_parts[2])
                    self._last_telemetry.gx = int(imu_parts[3])
                    self._last_telemetry.gy = int(imu_parts[4])
                    self._last_telemetry.gz = int(imu_parts[5])
            
            self._last_telemetry.valid = True
            log.debug(f"← STM32: ENC={self._last_telemetry.encoder_left},{self._last_telemetry.encoder_right}")
            
        except (ValueError, IndexError) as e:
            log.warning(f"Failed to parse STM32 telemetry: {e}")


# ============================================
# NAVIGATION
# ============================================

class Navigator:
    """
    Simple waypoint navigation.
    Calculates bearing and distance from current position to target.
    """
    
    def __init__(self):
        self.target_lat: Optional[float] = None
        self.target_lon: Optional[float] = None
        self.target_alt: float = 0.0
        self.arrival_threshold: float = 3.0  # meters
        self.max_speed: float = 1.5  # m/s
    
    def set_target(self, lat: float, lon: float, alt: float = 0.0):
        """Set navigation target waypoint"""
        self.target_lat = lat
        self.target_lon = lon
        self.target_alt = alt
        log.info(f"🎯 Navigation target: {lat:.6f}, {lon:.6f}")
    
    def clear_target(self):
        """Clear current navigation target"""
        self.target_lat = None
        self.target_lon = None
        log.info("🎯 Navigation target cleared")
    
    def calculate(self, current_lat: float, current_lon: float) -> tuple[float, float, float]:
        """
        Calculate navigation parameters.
        
        Returns:
            (bearing, distance, speed)
            bearing: Degrees (0-360) to target
            distance: Meters to target
            speed: Suggested speed in m/s
        """
        if self.target_lat is None or self.target_lon is None:
            return 0.0, 0.0, 0.0
        
        # Calculate bearing using Haversine formula
        lat1 = math.radians(current_lat)
        lat2 = math.radians(self.target_lat)
        lon1 = math.radians(current_lon)
        lon2 = math.radians(self.target_lon)
        
        dlon = lon2 - lon1
        
        # Bearing
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.degrees(math.atan2(x, y))
        bearing = (bearing + 360) % 360
        
        # Distance (Haversine)
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        distance = 6371000 * c  # Earth radius in meters
        
        # Speed (slow down as we approach)
        if distance < self.arrival_threshold:
            speed = 0.0  # Arrived!
            log.info("✅ Arrived at waypoint!")
            self.clear_target()
        elif distance < 5.0:
            speed = self.max_speed * 0.3  # Slow approach
        elif distance < 10.0:
            speed = self.max_speed * 0.5  # Medium
        else:
            speed = self.max_speed  # Full speed
        
        return bearing, distance, speed


# ============================================
# MAIN APPLICATION
# ============================================

class RoverApplication:
    """
    Main rover application tying everything together.
    """
    
    def __init__(
        self,
        server_url: str,
        rover_id: str,
        rover_name: str = "RasPi Rover",
        gps_port: str = '/dev/ttyUSB2',
        stm32_port: str = '/dev/ttyAMA0',
        simulate: bool = False
    ):
        self.server_url = server_url
        self.rover_id = rover_id
        self.rover_name = rover_name
        self.simulate = simulate
        
        # GlobalRTS client
        self.client = RoverClient(
            server_url=server_url,
            rover_id=rover_id,
            rover_name=rover_name,
            on_command=self.handle_command,
            telemetry_interval=1.0
        )
        
        # Hardware interfaces
        self.gps = SIM7600GPS(port=gps_port) if not simulate else None
        self.stm32 = STM32Interface(port=stm32_port) if not simulate else None
        
        # Navigation
        self.navigator = Navigator()
        
        # State
        self.running = False
        
        # Simulation state
        self._sim_lat = 34.0522
        self._sim_lon = -118.2437
        self._sim_heading = 0.0
    
    def handle_command(self, cmd: Command):
        """Handle commands from GlobalRTS"""
        log.info(f"📥 Command: {cmd.type}")
        
        if cmd.type == 'navigate':
            lat = cmd.payload.get('latitude')
            lon = cmd.payload.get('longitude')
            alt = cmd.payload.get('altitude', 0)
            if lat is not None and lon is not None:
                self.navigator.set_target(lat, lon, alt)
        
        elif cmd.type == 'stop':
            log.info("🛑 STOP command received!")
            self.navigator.clear_target()
            if self.stm32:
                self.stm32.send_stop()
        
        elif cmd.type == 'setSpeed':
            speed = cmd.payload.get('speed', 1.5)
            self.navigator.max_speed = speed
            log.info(f"⚡ Max speed set to {speed} m/s")
        
        else:
            log.warning(f"Unknown command type: {cmd.type}")
    
    async def run(self):
        """Main application loop"""
        self.running = True
        
        # Initialize hardware
        if not self.simulate:
            if self.gps:
                self.gps.open()
            if self.stm32:
                self.stm32.open()
        
        # Start GlobalRTS client in background
        client_task = asyncio.create_task(self.client.start())
        
        log.info("🚀 Rover application started")
        
        try:
            while self.running:
                await self._update_cycle()
                await asyncio.sleep(0.1)  # 10 Hz update loop
        
        except asyncio.CancelledError:
            log.info("Application cancelled")
        
        finally:
            # Cleanup
            self.client.stop()
            await client_task
            
            if self.gps:
                self.gps.close()
            if self.stm32:
                self.stm32.close()
    
    async def _update_cycle(self):
        """Single update cycle - read sensors, navigate, update telemetry"""
        
        # Read GPS
        if self.simulate:
            gps_data = self._simulate_gps()
        else:
            gps_data = self.gps.read() if self.gps else GPSData()
        
        # Read STM32 telemetry
        if self.simulate:
            stm32_data = self._simulate_stm32()
        else:
            stm32_data = self.stm32.read_telemetry() if self.stm32 else STM32Telemetry()
        
        # Calculate navigation
        if gps_data.valid and self.navigator.target_lat is not None:
            bearing, distance, speed = self.navigator.calculate(
                gps_data.latitude, gps_data.longitude
            )
            
            # Send command to STM32
            if self.stm32:
                self.stm32.send_command(bearing, speed)
            
            # Update simulation
            if self.simulate and speed > 0:
                self._simulate_movement(bearing, speed)
        
        # Update GlobalRTS telemetry
        self.client.update_gps(
            lat=gps_data.latitude,
            lon=gps_data.longitude,
            alt=gps_data.altitude,
            speed=gps_data.speed,
            heading=gps_data.heading,
            accuracy=2.5 if gps_data.valid else 0,
            hdop=gps_data.hdop
        )
        
        self.client.update_imu(
            ax=stm32_data.ax, ay=stm32_data.ay, az=stm32_data.az,
            gx=stm32_data.gx, gy=stm32_data.gy, gz=stm32_data.gz
        )
        
        self.client.update_encoders(
            left=stm32_data.encoder_left,
            right=stm32_data.encoder_right,
            left_vel=stm32_data.encoder_left_vel,
            right_vel=stm32_data.encoder_right_vel
        )
    
    def _simulate_gps(self) -> GPSData:
        """Generate simulated GPS data"""
        import random
        
        # Add small noise
        self._sim_lat += (random.random() - 0.5) * 0.00001
        self._sim_lon += (random.random() - 0.5) * 0.00001
        
        return GPSData(
            latitude=self._sim_lat,
            longitude=self._sim_lon,
            altitude=100.0,
            speed=0.5 + random.random() * 0.3,
            heading=self._sim_heading,
            hdop=1.2,
            valid=True
        )
    
    def _simulate_stm32(self) -> STM32Telemetry:
        """Generate simulated STM32 telemetry"""
        import random
        
        return STM32Telemetry(
            encoder_left=int(random.random() * 10000),
            encoder_right=int(random.random() * 10000),
            ax=int((random.random() - 0.5) * 1000),
            ay=int((random.random() - 0.5) * 1000),
            az=16000 + int(random.random() * 500),
            gx=int((random.random() - 0.5) * 100),
            gy=int((random.random() - 0.5) * 100),
            gz=int((random.random() - 0.5) * 100),
            valid=True
        )
    
    def _simulate_movement(self, bearing: float, speed: float):
        """Simulate rover movement towards waypoint"""
        # Move ~0.1 seconds worth at 10Hz
        distance_m = speed * 0.1
        
        # Convert to lat/lon delta (approximate)
        lat_delta = distance_m * math.cos(math.radians(bearing)) / 111000
        lon_delta = distance_m * math.sin(math.radians(bearing)) / (111000 * math.cos(math.radians(self._sim_lat)))
        
        self._sim_lat += lat_delta
        self._sim_lon += lon_delta
        self._sim_heading = bearing
    
    def stop(self):
        """Signal application to stop"""
        self.running = False
        self.client.stop()


def main():
    parser = argparse.ArgumentParser(description='GlobalRTS Rover Application')
    parser.add_argument('--server', '-s', default='https://miraeopus.com',
                        help='Server URL (default: https://miraeopus.com)')
    parser.add_argument('--rover-id', '-i', default='rover-001',
                        help='Rover ID (default: rover-001)')
    parser.add_argument('--rover-name', '-n', default='RasPi Rover',
                        help='Rover display name')
    parser.add_argument('--gps-port', default='/dev/ttyUSB2',
                        help='GPS serial port (default: /dev/ttyUSB2)')
    parser.add_argument('--stm32-port', default='/dev/ttyAMA0',
                        help='STM32 UART port (default: /dev/ttyAMA0)')
    parser.add_argument('--simulate', '-S', action='store_true',
                        help='Run in simulation mode (no hardware)')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    app = RoverApplication(
        server_url=args.server,
        rover_id=args.rover_id,
        rover_name=args.rover_name,
        gps_port=args.gps_port,
        stm32_port=args.stm32_port,
        simulate=args.simulate
    )
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        log.info("Shutdown signal received")
        app.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        log.info("Stopped by user")


if __name__ == '__main__':
    main()
