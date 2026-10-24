"""USGS Earthquake Catalog — бесплатный API, без ключа"""
import requests


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class USGSFetcher:
    """Загрузка землетрясений из USGS Earthquake Catalog"""

    BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

    def fetch(self, min_magnitude=6.0, start_year=1900):
        params = {
            "format": "geojson",
            "starttime": f"{start_year}-01-01",
            "minmagnitude": str(min_magnitude),
            "orderby": "time",
        }
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            events = []
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                geom = feature.get("geometry", {})
                coords = geom.get("coordinates", [0, 0, 0])
                ts_ms = props.get("time", 0)
                year = 1900
                try:
                    year = int(str(ts_ms)[:4]) if ts_ms > 100000 else 1900
                    if ts_ms > 1e12:
                        from datetime import datetime
                        year = datetime.utcfromtimestamp(ts_ms / 1000.0).year
                except Exception:
                    pass
                events.append({
                    "title": str(props.get("title", f"Earthquake {year}")),
                    "year": year,
                    "lat": float(coords[1]) if len(coords) > 1 else 0,
                    "lng": float(coords[0]) if len(coords) > 0 else 0,
                    "magnitude": float(props.get("mag", min_magnitude)) / 10.0,
                    "location": str(props.get("place", "unknown")),
                })
            return events
        except Exception as e:
            _safe_print(f"   USGS error: {e}")
            return []

    def populate_db(self, db, max_events=500):
        _safe_print("\n🌍 USGS Earthquake Catalog...")
        events = self.fetch()
        _safe_print(f"   Received {len(events)} events M>=6.0 from 1900")
        added = 0
        for e in events[:max_events]:
            eid = db.add_event(
                title=e["title"],
                description=f"USGS: {e['title']}",
                year=e["year"],
                location=e["location"],
                category="землетрясение",
                magnitude=e["magnitude"],
                importance_score=0.85,
                source="usgs",
                source_confidence=0.90,
            )
            if eid:
                added += 1
        db.conn.commit()
        _safe_print(f"   +{added} new earthquakes added")
        return added
