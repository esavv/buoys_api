#!/usr/bin/env python3

import sys
import xml.etree.ElementTree as ET

import requests

ACTIVE_STATIONS_URL = "https://www.ndbc.noaa.gov/activestations.xml"


def fetch_active_stations_xml() -> str:
    response = requests.get(ACTIVE_STATIONS_URL, timeout=15)
    response.raise_for_status()
    return response.text


def parse_stations(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    stations = []

    for station_el in root.iter("station"):
        station_id = station_el.get("id", "")
        lat = station_el.get("lat")
        lon = station_el.get("lon")
        name = station_el.get("name", "")
        owner = station_el.get("pgm", "")

        if not lat or not lon:
            continue

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except ValueError:
            continue

        stations.append({
            "id": station_id,
            "lat": lat_f,
            "lon": lon_f,
            "name": name,
            "owner": owner,
        })

    return stations


def get_stations() -> dict:
    try:
        xml_text = fetch_active_stations_xml()
    except requests.RequestException as exc:
        return {
            "status": "error",
            "error_msg": f"Failed to fetch station list from NOAA: {exc}",
        }

    stations = parse_stations(xml_text)

    if not stations:
        return {
            "status": "error",
            "error_msg": "No stations found in NOAA response.",
        }

    return {
        "status": "success",
        "count": len(stations),
        "stations": stations,
    }


def main(argv: list[str]) -> int:
    result = get_stations()

    if result["status"] == "error":
        print(f"Error: {result['error_msg']}")
        return 1

    print(f"Found {result['count']} active stations")
    for station in result["stations"][:10]:
        print(f"  {station['id']:>8s}  {station['lat']:8.3f}  {station['lon']:9.3f}  {station['name']}")
    if result["count"] > 10:
        print(f"  ... and {result['count'] - 10} more")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
