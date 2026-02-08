#!/usr/bin/env python3
"""
cellular.py — SIM7600G-H 4G LTE Cellular Manager for Raspberry Pi 5

Sets up and manages the SIM7600G-H cellular modem so all rover communication
(WebSocket telemetry, commands, HTTP fallback) goes through the 4G network.

Two modes of operation:
  1. STANDALONE: Run this script directly to bring up cellular and verify connectivity.
     python3 cellular.py
     
  2. INTEGRATED: Import CellularManager into main.py to auto-manage cellular alongside
     GPS, STM32, and GlobalRTS communication.

Hardware:
    SIM7600G-H HAT connected to Pi via USB, creating:
      /dev/ttyUSB0 — Diagnostic port
      /dev/ttyUSB1 — NMEA GPS output  
      /dev/ttyUSB2 — AT command port (we use this)
      /dev/ttyUSB3 — Modem/PPP port (we use this for data)

The modem provides internet via PPP (Point-to-Point Protocol) over /dev/ttyUSB3.
Once PPP is up, the Pi gets a ppp0 interface with a public-ish IP, and all traffic
(including WebSocket to miraeopus.com) can route through it.

Dependencies:
    pip3 install pyserial
    sudo apt install ppp  (usually pre-installed)
"""

import serial
import time
import subprocess
import os
import signal
import sys
import logging
import threading
from typing import Optional, Tuple
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('cellular')


@dataclass
class ModemStatus:
    """Current modem state"""
    powered: bool = False
    sim_ready: bool = False
    registered: bool = False
    network_name: str = ""
    signal_strength: int = 0       # 0-31, 99=unknown
    signal_dbm: int = -999         # dBm
    signal_percent: int = 0        # 0-100%
    connection_type: str = ""      # "LTE", "WCDMA", "GSM", etc.
    ip_address: str = ""
    data_connected: bool = False
    error: str = ""


class CellularManager:
    """
    Manages the SIM7600G-H cellular modem.
    
    Handles:
      - Modem initialization and AT command interface
      - SIM card detection
      - Network registration
      - Data connection (PPP or QMI)
      - Connection monitoring and auto-reconnect
      - Signal strength reporting
    """

    def __init__(
        self,
        at_port: str = '/dev/ttyUSB2',
        ppp_port: str = '/dev/ttyUSB3',
        baudrate: int = 115200,
        apn: str = 'super',
    ):
        """
        Args:
            at_port:  Serial port for AT commands (/dev/ttyUSB2)
            ppp_port: Serial port for PPP data (/dev/ttyUSB3)  
            baudrate: Serial baudrate (115200 for SIM7600)
            apn:      Your carrier's APN. Common ones:
                      - 'super'        (Mint Mobile / T-Mobile MVNOs)
                      - 'fast.t-mobile.com' (T-Mobile)
                      - 'wholesale'    (Mint Mobile alternative)
                      - 'broadband'    (AT&T prepaid)
                      - 'internet'     (AT&T postpaid)  
                      - 'vzwinternet'  (Verizon)
                      - 'hologram'     (Hologram SIM)
        """
        self.at_port = at_port
        self.ppp_port = ppp_port
        self.baudrate = baudrate
        self.apn = apn

        self._at_serial: Optional[serial.Serial] = None
        self._ppp_process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._status = ModemStatus()

    # ──────────────────────────────────────────────
    # AT COMMAND INTERFACE
    # ──────────────────────────────────────────────

    def _open_at(self) -> bool:
        """Open the AT command serial port."""
        if self._at_serial and self._at_serial.is_open:
            return True
        try:
            self._at_serial = serial.Serial(
                self.at_port,
                self.baudrate,
                timeout=1.0
            )
            log.info(f"AT port opened: {self.at_port}")
            return True
        except serial.SerialException as e:
            log.error(f"Failed to open AT port {self.at_port}: {e}")
            return False

    def _close_at(self):
        """Close the AT command serial port."""
        if self._at_serial and self._at_serial.is_open:
            self._at_serial.close()
            self._at_serial = None

    def _send_at(self, command: str, timeout: float = 2.0, wait_for: str = 'OK') -> str:
        """
        Send an AT command and return the full response.
        
        Args:
            command:  AT command string (e.g. 'AT+CSQ')
            timeout:  Max seconds to wait for response
            wait_for: String that signals end of response ('OK', 'ERROR', etc.)
        
        Returns:
            Full response string, or "" on failure.
        """
        if not self._at_serial or not self._at_serial.is_open:
            if not self._open_at():
                return ""

        try:
            # Flush any stale data
            self._at_serial.reset_input_buffer()

            # Send command
            self._at_serial.write(f"{command}\r\n".encode())
            self._at_serial.flush()

            # Read response
            response = ""
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self._at_serial.in_waiting:
                    chunk = self._at_serial.read(self._at_serial.in_waiting).decode('utf-8', errors='ignore')
                    response += chunk
                    if wait_for in response or 'ERROR' in response:
                        break
                else:
                    time.sleep(0.05)

            return response.strip()

        except serial.SerialException as e:
            log.error(f"AT command error ({command}): {e}")
            return ""

    # ──────────────────────────────────────────────
    # MODEM INITIALIZATION
    # ──────────────────────────────────────────────

    def initialize(self) -> bool:
        """
        Initialize the SIM7600G-H modem.
        
        Steps:
          1. Open AT port
          2. Check modem responds  
          3. Check SIM card
          4. Wait for network registration
          5. Configure APN
        
        Returns True if modem is ready for data connection.
        """
        log.info("=" * 60)
        log.info("  SIM7600G-H Cellular Modem Initialization")
        log.info("=" * 60)

        # Step 1: Open AT port
        if not self._open_at():
            self._status.error = f"Cannot open {self.at_port}"
            return False

        # Step 2: Check modem responds
        log.info("Checking modem...")
        resp = self._send_at('AT', timeout=3.0)
        if 'OK' not in resp:
            # Try a few more times — modem might be booting
            for attempt in range(5):
                log.info(f"  Modem not responding, retry {attempt+1}/5...")
                time.sleep(2)
                resp = self._send_at('AT', timeout=3.0)
                if 'OK' in resp:
                    break
            else:
                self._status.error = "Modem not responding to AT commands"
                log.error(self._status.error)
                return False

        self._status.powered = True
        log.info("  Modem responding OK")

        # Disable echo for cleaner parsing
        self._send_at('ATE0')

        # Get modem info
        model = self._send_at('AT+CGMM')
        log.info(f"  Model: {model.replace('OK', '').strip()}")
        
        imei = self._send_at('AT+CGSN')
        log.info(f"  IMEI: {imei.replace('OK', '').strip()}")

        # Step 3: Check SIM card
        log.info("Checking SIM card...")
        sim_resp = self._send_at('AT+CPIN?')
        if 'READY' in sim_resp:
            self._status.sim_ready = True
            log.info("  SIM card: READY")
        elif 'SIM PIN' in sim_resp:
            self._status.error = "SIM card requires PIN — enter it with AT+CPIN=xxxx"
            log.error(f"  {self._status.error}")
            return False
        else:
            self._status.error = "No SIM card detected"
            log.error(f"  {self._status.error}")
            return False

        # Step 4: Wait for network registration
        log.info("Waiting for network registration...")
        registered = False
        for attempt in range(30):  # Wait up to 60 seconds
            reg_resp = self._send_at('AT+CREG?')
            # +CREG: 0,1 (registered home) or +CREG: 0,5 (registered roaming)
            if ',1' in reg_resp or ',5' in reg_resp:
                registered = True
                break
            log.info(f"  Not registered yet... ({attempt+1}/30)")
            time.sleep(2)

        if not registered:
            self._status.error = "Failed to register on network"
            log.error(self._status.error)
            return False

        self._status.registered = True
        log.info("  Registered on network")

        # Get network operator name
        cop_resp = self._send_at('AT+COPS?')
        if '+COPS:' in cop_resp:
            try:
                # +COPS: 0,0,"T-Mobile",7
                parts = cop_resp.split('"')
                if len(parts) >= 2:
                    self._status.network_name = parts[1]
            except Exception:
                pass
        log.info(f"  Operator: {self._status.network_name or 'Unknown'}")

        # Get connection type
        self._update_signal()
        log.info(f"  Signal: {self._status.signal_percent}% ({self._status.signal_dbm} dBm)")
        log.info(f"  Network: {self._status.connection_type or 'Unknown'}")

        # Step 5: Configure APN
        log.info(f"Configuring APN: {self.apn}")
        self._send_at(f'AT+CGDCONT=1,"IP","{self.apn}"')
        log.info("  APN configured")

        log.info("=" * 60)
        log.info("  Modem initialized successfully!")
        log.info("=" * 60)
        return True

    # ──────────────────────────────────────────────
    # SIGNAL STRENGTH
    # ──────────────────────────────────────────────

    def _update_signal(self):
        """Update signal strength in self._status."""
        # Signal quality
        csq_resp = self._send_at('AT+CSQ')
        if '+CSQ:' in csq_resp:
            try:
                parts = csq_resp.split('+CSQ:')[1].split(',')
                rssi = int(parts[0].strip())
                if rssi != 99:
                    self._status.signal_strength = rssi
                    self._status.signal_dbm = -113 + (rssi * 2)
                    self._status.signal_percent = min(100, max(0, int((rssi / 31) * 100)))
            except (ValueError, IndexError):
                pass

        # Network type (LTE, WCDMA, etc.)
        cnti_resp = self._send_at('AT+CNTI?')
        if '+CNTI:' in cnti_resp:
            try:
                self._status.connection_type = cnti_resp.split(',')[-1].strip().replace('\r', '').replace('\n', '').replace('OK', '').strip()
            except Exception:
                pass
        
        # Fallback: check CPSI for system info
        if not self._status.connection_type:
            cpsi_resp = self._send_at('AT+CPSI?')
            if '+CPSI:' in cpsi_resp:
                try:
                    self._status.connection_type = cpsi_resp.split('+CPSI:')[1].split(',')[0].strip()
                except Exception:
                    pass

    def get_signal(self) -> Tuple[int, int, str]:
        """
        Get current signal strength.
        
        Returns:
            (percent, dbm, network_type)
            e.g. (75, -63, "LTE")
        """
        self._update_signal()
        return (
            self._status.signal_percent,
            self._status.signal_dbm,
            self._status.connection_type
        )

    # ──────────────────────────────────────────────
    # DATA CONNECTION — PPP
    # ──────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Establish a data connection using PPP over the modem port.
        
        This creates a ppp0 network interface on the Pi. Once up,
        all outbound traffic (including WebSocket to miraeopus.com)
        can route through the cellular network.
        
        Returns True if ppp0 comes up successfully.
        """
        if self.is_connected():
            log.info("Already connected (ppp0 exists)")
            return True

        log.info("Establishing cellular data connection...")

        # Make sure the ppp peer config exists
        self._write_ppp_peer_config()

        # Bring up PPP
        log.info(f"  Starting pppd on {self.ppp_port}...")
        try:
            self._ppp_process = subprocess.Popen(
                ['sudo', 'pppd', 'call', 'sim7600'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            log.error("pppd not found. Install with: sudo apt install ppp")
            return False

        # Wait for ppp0 interface to come up
        log.info("  Waiting for ppp0 interface...")
        for i in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            if self._check_ppp0_up():
                ip = self._get_ppp0_ip()
                self._status.ip_address = ip
                self._status.data_connected = True
                log.info(f"  ppp0 UP — IP: {ip}")
                
                # Set ppp0 as default route
                self._set_default_route()
                
                log.info("  Cellular data connection established!")
                return True
            
            # Check if pppd died
            if self._ppp_process.poll() is not None:
                stderr = self._ppp_process.stderr.read().decode('utf-8', errors='ignore')
                log.error(f"  pppd exited early: {stderr[:200]}")
                break

        log.error("  Failed to bring up ppp0 within 30 seconds")
        self.disconnect()
        return False

    def connect_direct(self) -> bool:
        """
        Establish data connection using AT commands (NDIS/QMI mode).
        
        This is simpler than PPP and works well with the SIM7600.
        Uses the built-in network interface instead of PPP.
        
        Requires the usbnet kernel module (usually loaded automatically).
        The SIM7600 creates a usb0 or wwan0 interface.
        
        Returns True if connection established.
        """
        if self.is_connected():
            log.info("Already connected")
            return True

        log.info("Establishing cellular data via AT commands (NDIS mode)...")

        # Set the PDP context with our APN
        self._send_at(f'AT+CGDCONT=1,"IP","{self.apn}"')
        time.sleep(0.5)

        # Activate the network using NDIS (Network Data Interface Specification)
        resp = self._send_at('AT+CNACT=0,1', timeout=15.0)
        if 'ERROR' in resp:
            # Try older command
            resp = self._send_at('AT$QCRMCALL=1,1', timeout=15.0)

        time.sleep(2)

        # Check for usb0 or wwan0 interface
        for iface in ['usb0', 'wwan0', 'eth1']:
            if self._check_interface_up(iface):
                # Request DHCP
                log.info(f"  Interface {iface} detected, requesting IP via DHCP...")
                result = subprocess.run(
                    ['sudo', 'dhclient', iface, '-timeout', '10'],
                    capture_output=True, text=True, timeout=15
                )
                
                ip = self._get_interface_ip(iface)
                if ip:
                    self._status.ip_address = ip
                    self._status.data_connected = True
                    log.info(f"  {iface} UP — IP: {ip}")
                    self._set_default_route(iface)
                    log.info("  Cellular data connection established!")
                    return True

        # Fallback: try PPP
        log.info("  NDIS mode failed, falling back to PPP...")
        return self.connect()

    def disconnect(self):
        """Tear down the cellular data connection."""
        log.info("Disconnecting cellular data...")

        # Kill PPP if running
        if self._ppp_process:
            self._ppp_process.terminate()
            try:
                self._ppp_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._ppp_process.kill()
            self._ppp_process = None

        # Also kill any stray pppd
        subprocess.run(['sudo', 'killall', 'pppd'], capture_output=True)

        # Deactivate NDIS if used
        self._send_at('AT+CNACT=0,0', timeout=5.0)

        self._status.data_connected = False
        self._status.ip_address = ""
        log.info("  Disconnected")

    def is_connected(self) -> bool:
        """Check if we have an active cellular data connection."""
        return (
            self._check_ppp0_up() or
            self._check_interface_up('usb0') or
            self._check_interface_up('wwan0')
        )

    # ──────────────────────────────────────────────
    # PPP CONFIGURATION
    # ──────────────────────────────────────────────

    def _write_ppp_peer_config(self):
        """Write the PPP peer config file for pppd."""
        config = f"""\
# /etc/ppp/peers/sim7600
# Auto-generated by cellular.py for SIM7600G-H

{self.ppp_port}
{self.baudrate}
noauth
nodetach
defaultroute
usepeerdns
noipdefault
persist
maxfail 3
holdoff 10

# Dial script
connect "/usr/sbin/chat -v \\
    ABORT 'BUSY' \\
    ABORT 'NO CARRIER' \\
    ABORT 'NO DIALTONE' \\
    ABORT 'ERROR' \\
    ABORT 'NO ANSWER' \\
    TIMEOUT 30 \\
    '' AT \\
    OK 'AT+CGDCONT=1,\\"IP\\",\\"{self.apn}\\"' \\
    OK ATD*99# \\
    CONNECT ''"
"""
        config_path = '/etc/ppp/peers/sim7600'
        try:
            # Write via sudo tee
            process = subprocess.run(
                ['sudo', 'tee', config_path],
                input=config.encode(),
                capture_output=True,
                timeout=5
            )
            if process.returncode == 0:
                log.info(f"  PPP config written to {config_path}")
            else:
                log.error(f"  Failed to write PPP config: {process.stderr.decode()}")
        except Exception as e:
            log.error(f"  Failed to write PPP config: {e}")

    # ──────────────────────────────────────────────
    # NETWORK INTERFACE HELPERS
    # ──────────────────────────────────────────────

    def _check_ppp0_up(self) -> bool:
        """Check if ppp0 interface exists and is up."""
        return self._check_interface_up('ppp0')

    def _check_interface_up(self, iface: str) -> bool:
        """Check if a network interface exists and is up."""
        try:
            result = subprocess.run(
                ['ip', 'link', 'show', iface],
                capture_output=True, text=True, timeout=3
            )
            return result.returncode == 0 and 'UP' in result.stdout
        except Exception:
            return False

    def _get_ppp0_ip(self) -> str:
        """Get the IP address of the ppp0 interface."""
        return self._get_interface_ip('ppp0')

    def _get_interface_ip(self, iface: str) -> str:
        """Get the IP address of a network interface."""
        try:
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show', iface],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.split('\n'):
                if 'inet ' in line:
                    # inet 10.64.64.64/32 scope global ppp0
                    return line.strip().split()[1].split('/')[0]
        except Exception:
            pass
        return ""

    def _set_default_route(self, iface: str = 'ppp0'):
        """
        Set the cellular interface as the default route.
        
        This ensures WebSocket traffic to miraeopus.com goes through cellular.
        We use a higher metric so WiFi (if available) can still be used for SSH.
        """
        try:
            # Add default route via cellular with metric 100
            # (WiFi typically has metric 600, so cellular wins)
            subprocess.run(
                ['sudo', 'ip', 'route', 'add', 'default', 'dev', iface, 'metric', '50'],
                capture_output=True, text=True, timeout=5
            )
            log.info(f"  Default route set via {iface} (metric 50)")

            # Also set DNS if not already set
            subprocess.run(
                ['sudo', 'bash', '-c', 
                 'echo "nameserver 8.8.8.8" >> /etc/resolv.conf && '
                 'echo "nameserver 8.8.4.4" >> /etc/resolv.conf'],
                capture_output=True, timeout=5
            )

        except Exception as e:
            log.warning(f"  Route setup warning: {e}")

    # ──────────────────────────────────────────────
    # CONNECTION MONITORING
    # ──────────────────────────────────────────────

    def start_monitor(self):
        """
        Start a background thread that monitors connectivity
        and auto-reconnects if the data connection drops.
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="cellular-monitor"
        )
        self._monitor_thread.start()
        log.info("Connection monitor started")

    def stop_monitor(self):
        """Stop the connection monitor."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def _monitor_loop(self):
        """Background loop: check connectivity, reconnect if needed."""
        while self._running:
            try:
                # Update signal info
                self._update_signal()

                # Check if data connection is alive
                if not self.is_connected():
                    log.warning("Cellular data connection lost! Reconnecting...")
                    self._status.data_connected = False
                    self.connect_direct()

                # Ping test (lightweight check every 30s)
                elif not self._ping_test():
                    log.warning("Ping test failed — internet may be down")
                    # Don't immediately reconnect, could be temporary
                    # Wait and try again
                    time.sleep(10)
                    if not self._ping_test():
                        log.warning("Second ping failed — reconnecting")
                        self.disconnect()
                        time.sleep(2)
                        self.connect_direct()

            except Exception as e:
                log.error(f"Monitor error: {e}")

            # Check every 30 seconds
            for _ in range(30):
                if not self._running:
                    return
                time.sleep(1)

    def _ping_test(self) -> bool:
        """Quick ping test to verify internet connectivity."""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '5', '8.8.8.8'],
                capture_output=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    # ──────────────────────────────────────────────
    # STATUS / INFO
    # ──────────────────────────────────────────────

    @property
    def status(self) -> ModemStatus:
        """Get current modem status."""
        return self._status

    def print_status(self):
        """Print a formatted status summary."""
        s = self._status
        self._update_signal()

        print(f"\n{'='*50}")
        print(f"  SIM7600G-H Modem Status")
        print(f"{'='*50}")
        print(f"  Powered:      {'YES' if s.powered else 'NO'}")
        print(f"  SIM Card:     {'READY' if s.sim_ready else 'NOT READY'}")
        print(f"  Registered:   {'YES' if s.registered else 'NO'}")
        print(f"  Operator:     {s.network_name or 'N/A'}")
        print(f"  Network:      {s.connection_type or 'N/A'}")
        print(f"  Signal:       {s.signal_percent}% ({s.signal_dbm} dBm)")
        print(f"  Data:         {'CONNECTED' if s.data_connected else 'DISCONNECTED'}")
        print(f"  IP Address:   {s.ip_address or 'N/A'}")
        if s.error:
            print(f"  Error:        {s.error}")
        print(f"{'='*50}\n")

    def cleanup(self):
        """Clean shutdown — stop monitor, disconnect data."""
        self.stop_monitor()
        self.disconnect()
        self._close_at()
        log.info("Cellular manager cleaned up")


# ══════════════════════════════════════════════════
# STANDALONE MODE — run this script directly
# ══════════════════════════════════════════════════

def main():
    """
    Standalone: Initialize modem, bring up cellular, verify connectivity.
    
    Usage:
        python3 cellular.py                          # Use defaults
        python3 cellular.py --apn fast.t-mobile.com  # Custom APN
        python3 cellular.py --check                  # Just check status
    """
    import argparse

    parser = argparse.ArgumentParser(description='SIM7600G-H Cellular Manager')
    parser.add_argument('--at-port', default='/dev/ttyUSB2',
                        help='AT command port (default: /dev/ttyUSB2)')
    parser.add_argument('--ppp-port', default='/dev/ttyUSB3',
                        help='PPP/modem port (default: /dev/ttyUSB3)')
    parser.add_argument('--apn', default='super',
                        help='Carrier APN (default: super)')
    parser.add_argument('--check', action='store_true',
                        help='Just check modem status, don\'t connect')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--keep-alive', action='store_true',
                        help='Keep running with auto-reconnect monitor')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    cell = CellularManager(
        at_port=args.at_port,
        ppp_port=args.ppp_port,
        apn=args.apn,
    )

    # Handle Ctrl+C
    def signal_handler(sig, frame):
        print("\nShutting down...")
        cell.cleanup()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize modem
    if not cell.initialize():
        print(f"\nModem initialization failed: {cell.status.error}")
        print("\nTroubleshooting:")
        print("  1. Is the SIM7600G-H HAT powered on? (check PWR LED)")
        print("  2. Do the USB serial ports exist?  ls /dev/ttyUSB*")
        print("  3. Is a SIM card inserted?")
        print("  4. Are you running as root/sudo for serial access?")
        sys.exit(1)

    cell.print_status()

    if args.check:
        print("Check complete. Exiting.")
        cell.cleanup()
        return

    # Connect to cellular data
    print("\nBringing up cellular data connection...")
    if cell.connect_direct():
        print("\nCellular data is UP!")
        cell.print_status()

        # Verify we can reach the internet
        print("Testing internet connectivity...")
        if cell._ping_test():
            print("  Ping to 8.8.8.8: OK")
        else:
            print("  Ping to 8.8.8.8: FAILED (routing may need adjustment)")

        # Test DNS
        try:
            result = subprocess.run(
                ['nslookup', 'miraeopus.com'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                print("  DNS resolve miraeopus.com: OK")
            else:
                print("  DNS resolve miraeopus.com: FAILED")
        except Exception:
            print("  DNS test skipped (nslookup not available)")

        if args.keep_alive:
            print("\nRunning with auto-reconnect monitor (Ctrl+C to stop)...")
            cell.start_monitor()
            try:
                while True:
                    time.sleep(60)
                    sig_pct, sig_dbm, net_type = cell.get_signal()
                    connected = cell.is_connected()
                    print(f"  [{time.strftime('%H:%M:%S')}] "
                          f"Signal: {sig_pct}% ({sig_dbm}dBm) | "
                          f"Network: {net_type} | "
                          f"Data: {'UP' if connected else 'DOWN'}")
            except KeyboardInterrupt:
                pass

        print("\nCellular connection is ready.")
        print("You can now run your rover:")
        print(f"  python3 test.py")
        print(f"  python3 main.py --server wss://miraeopus.com --rover-id rover-001")

    else:
        print("\nFailed to establish cellular data connection.")
        print("\nTroubleshooting:")
        print("  1. Check your APN is correct for your carrier")
        print(f"     Current APN: {args.apn}")
        print("  2. Check signal strength with: python3 cellular.py --check")
        print("  3. Try a different connection method:")
        print("     sudo pppd call sim7600 (manual PPP)")
        print("     sudo qmicli ... (QMI mode)")
        cell.cleanup()
        sys.exit(1)

    cell.cleanup()


if __name__ == '__main__':
    main()
