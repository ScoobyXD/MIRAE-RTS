#!/usr/bin/python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re
import time
import serial


@dataclass
class GpsFix:
    lat: float
    lon: float
    utc: datetime
    local: datetime


def ddmm_to_decimal(ddmm: str, hemi: str) -> float:
    v = float(ddmm)
    deg = int(v // 100)
    minutes = v - deg * 100
    dec = deg + minutes / 60.0
    if hemi in ("S", "W"):
        dec = -dec
    return dec


def extract_cgpsinfo_payload(resp: str) -> str:
    m = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", resp)
    if not m:
        raise ValueError("No +CGPSINFO line found")
    return m.group(1).strip()


def send_at(ser: serial.Serial, cmd: str, wait: float = 1.0) -> str:
    # clear stale bytes
    try:
        ser.reset_input_buffer()
    except Exception:
        pass

    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)

    out = b""
    while ser.in_waiting:
        out += ser.read(ser.in_waiting)
        time.sleep(0.05)

    return out.decode(errors="ignore")


def get_human_readable_gps_fix(
    ser: serial.Serial,
    tz_name: str = "America/Los_Angeles",
    attempts: int = 10,
    delay_s: float = 1.5,
) -> GpsFix:
    # turn GPS on (safe to call repeatedly)
    send_at(ser, "AT+CGPS=1,1", wait=1.0)

    for _ in range(attempts):
        resp = send_at(ser, "AT+CGPSINFO", wait=1.0)

        try:
            payload = extract_cgpsinfo_payload(resp)
        except ValueError:
            time.sleep(delay_s)
            continue

        parts = [p.strip() for p in payload.split(",")]

        # Not ready => empty fields like ",,,,,,"
        if len(parts) < 6 or parts[0] == "" or parts[2] == "" or parts[4] == "" or parts[5] == "":
            time.sleep(delay_s)
            continue

        lat_ddmm, lat_hemi = parts[0], parts[1]
        lon_ddmm, lon_hemi = parts[2], parts[3]
        ddmmyy = parts[4]               # DDMMYY
        hhmmss = parts[5].split(".")[0] # HHMMSS

        lat = ddmm_to_decimal(lat_ddmm, lat_hemi)
        lon = ddmm_to_decimal(lon_ddmm, lon_hemi)

        dt_utc = datetime.strptime(ddmmyy + hhmmss, "%d%m%y%H%M%S").replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(ZoneInfo(tz_name))

        return GpsFix(lat=lat, lon=lon, utc=dt_utc, local=dt_local)

    raise RuntimeError("GPS fix not ready (no valid +CGPSINFO after attempts)")


def main():
	while(1):
		with serial.Serial("/dev/ttyUSB2", 115200, timeout=1) as ser:
			fix = get_human_readable_gps_fix(ser)
			print(f"lat={fix.lat:.8f}, lon={fix.lon:.8f}")
			print("UTC :", fix.utc.isoformat())
			print("LA  :", fix.local.isoformat())


if __name__ == "__main__":
    main()
