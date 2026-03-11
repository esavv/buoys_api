#!/usr/bin/env python3

import requests
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SPEC_URL_TEMPLATE = "https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.spec"
TXT_URL_TEMPLATE = "https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.txt"
FEET_PER_METER = 3.28084

def fetch_spec(buoy_id: str) -> str:
    url = SPEC_URL_TEMPLATE.format(buoy_id=buoy_id)
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text

def fetch_txt(buoy_id: str) -> str:
    url = TXT_URL_TEMPLATE.format(buoy_id=buoy_id)
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text

def parse_latest_observation(spec_text: str):
    lines = [line.strip() for line in spec_text.splitlines() if line.strip()]

    header_line = next((line for line in lines if line.startswith("#")), None)
    data_lines = [line for line in lines if not line.startswith("#")]

    if not header_line or not data_lines:
        return None, "No buoy data rows were returned."

    header_tokens = header_line.lstrip("#").split()
    latest_tokens = data_lines[0].split()

    def token_for(column: str):
        if column not in header_tokens:
            return None
        index = header_tokens.index(column)
        if index >= len(latest_tokens):
            return None
        return latest_tokens[index]

    wave_height_meters = token_for("WVHT")
    swell_height_meters = token_for("SwH")
    swell_period = token_for("SwP")
    swell_direction = token_for("SwD")
    mean_swell_direction_deg = token_for("MWD")
    year_token = token_for("YY")
    month_token = token_for("MM")
    day_token = token_for("DD")
    hour_token = token_for("hh")
    minute_token = token_for("mm")

    timestamp_display = "Unknown"
    observation_time = datetime(
        int(year_token),
        int(month_token),
        int(day_token),
        int(hour_token),
        int(minute_token),
        tzinfo=ZoneInfo("UTC"),
    )
    observation_time_iso = observation_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    local_time = observation_time.astimezone(ZoneInfo("America/New_York"))
    timestamp_display = local_time.strftime("%I:%M %p %Z").lstrip("0")
    timestamp_display = timestamp_display.replace("AM", "am").replace("PM", "pm")

    wave_height_display = "N/A"
    if wave_height_meters and wave_height_meters != "MM":
        wave_height_feet = float(wave_height_meters) * FEET_PER_METER
        wave_height_display = f"{wave_height_feet:.1f}"

    swell_height_display = "N/A"
    if swell_height_meters and swell_height_meters != "MM":
        swell_height_feet = float(swell_height_meters) * FEET_PER_METER
        swell_height_display = f"{swell_height_feet:.1f}"

    swell_period_display = (
        swell_period if swell_period and swell_period != "MM" else "N/A"
    )
    swell_direction_display = (
        swell_direction if swell_direction and swell_direction != "MM" else "N/A"
    )
    mean_swell_direction_display = (
        mean_swell_direction_deg if mean_swell_direction_deg and mean_swell_direction_deg != "MM" else "N/A"
    )

    return (
        timestamp_display,
        observation_time_iso,
        wave_height_display,
        swell_height_display,
        swell_period_display,
        swell_direction_display,
        mean_swell_direction_display,
    ), None


def parse_txt_temps(txt_text: str) -> tuple[str | None, str | None]:
    """
    Parse ATMP and WTMP from NDBC realtime2 .txt (first data row).
    Returns (water_temp_c, air_temp_c); each is a string or None if missing/invalid.
    """
    lines = [line.strip() for line in txt_text.splitlines() if line.strip()]
    header_line = next((line for line in lines if line.startswith("#")), None)
    data_lines = [line for line in lines if not line.startswith("#")]

    if not header_line or not data_lines:
        return None, None

    header_tokens = header_line.lstrip("#").split()
    latest_tokens = data_lines[0].split()

    def token_for(column: str) -> str | None:
        if column not in header_tokens:
            return None
        idx = header_tokens.index(column)
        if idx >= len(latest_tokens):
            return None
        val = latest_tokens[idx]
        return val if val and val != "MM" else None

    air_temp_c = token_for("ATMP")
    water_temp_c = token_for("WTMP")
    return water_temp_c, air_temp_c


def get_buoy_reading(buoy_id: str) -> dict:
    """
    Fetch and parse the latest observation for a buoy.
    Returns a dict with status and data, or status and error_msg.
    """
    try:
        spec_text = fetch_spec(buoy_id)
    except requests.RequestException as exc:
        return {
            "status": "error",
            "error_msg": f"Failed to fetch data for buoy {buoy_id}: {exc}",
        }

    observation, error = parse_latest_observation(spec_text)
    if error:
        return {
            "status": "error",
            "error_msg": error,
        }

    timestamp, observation_time_iso, wave_height, swell_height, swell_period, swell_direction, mean_swell_direction = observation

    # Optional: fetch temps from .txt (don't fail the whole request if .txt is missing or errors)
    water_temp_c = "N/A"
    air_temp_c = "N/A"
    try:
        txt_text = fetch_txt(buoy_id)
        wtmp, atmp = parse_txt_temps(txt_text)
        if wtmp is not None:
            water_temp_c = wtmp
        if atmp is not None:
            air_temp_c = atmp
    except requests.RequestException:
        pass

    return {
        "status": "success",
        "last_updated": timestamp,
        "observation_time": observation_time_iso,
        "sig_wave_height_ft": wave_height,
        "swell_height_ft": swell_height,
        "swell_period_s": swell_period,
        "swell_direction": swell_direction,
        "mean_swell_direction_deg": mean_swell_direction,
        "water_temp_c": water_temp_c,
        "air_temp_c": air_temp_c,
    }

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        script_name = Path(argv[0]).name if argv else "fetch_buoy.py"
        print(f"Usage: python {script_name} <buoy_id>")
        return 1

    buoy_id = argv[1]

    try:
        spec_text = fetch_spec(buoy_id)
    except requests.RequestException as exc:
        print(f"Error fetching data for buoy {buoy_id}: {exc}")
        return 2

    # lines = spec_text.splitlines()
    # preview = "\n".join(lines[:5])
    # print(preview + "\n")

    observation, error = parse_latest_observation(spec_text)
    if error:
        print(error)
        return 3

    timestamp, observation_time_iso, wave_height, swell_height, swell_period, swell_direction, mean_swell_direction = observation
    print(f"Last Updated:     {timestamp}")
    print(f"Observation Time: {observation_time_iso}")
    print(f"Sig. Wave Height: {wave_height} ft")
    print(f"Swell Height:     {swell_height} ft")
    print(f"Swell Period:     {swell_period} s")
    print(f"Swell Direction:  {swell_direction}")
    print(f"Mean Swell Dir.:  {mean_swell_direction}°")
    try:
        txt_text = fetch_txt(buoy_id)
        water_temp_c, air_temp_c = parse_txt_temps(txt_text)
        print(f"Water Temp:       {water_temp_c or 'N/A'}°C")
        print(f"Air Temp:         {air_temp_c or 'N/A'}°C")
    except requests.RequestException as e:
        print(f"Temps (from .txt): fetch failed ({e})")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
