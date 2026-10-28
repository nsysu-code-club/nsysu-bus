import json
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://ibusplus.tbkc.gov.tw/bsuper"
ROOT = Path(__file__).resolve().parent


def text(value):
    value = str(value).strip() if value is not None else ""
    return "" if value.lower() == "null" else value


def refresh_token(session):
    response = session.post(f"{URL}/Token/Web", timeout=30)
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token") if isinstance(data, dict) else data
    if not isinstance(token, str) or not token.strip():
        raise ValueError("No guest token returned")
    session.headers["Authorization"] = f"Bearer {token}"


def fetch_stops(session, route_id, direction):
    payload = [{"id": str(route_id), "direction": direction}]
    for attempt in range(2):
        response = session.post(
            f"{URL}/Extended/Dal/CustomEstimateTime?extraType=All",
            json=payload, timeout=30,
        )
        if response.status_code == 401 and attempt == 0:
            refresh_token(session)
            continue
        response.raise_for_status()
        data = response.json()
        if data.get("status") != 0 or not isinstance(data.get("data"), list):
            raise ValueError("Arrival API reported failure")
        stops = [stop for group in data["data"] for stop in group]
        if not stops or any(
            text(stop.get("routeid")) != str(route_id)
            or text(stop.get("direction")) != str(direction) for stop in stops
        ):
            raise ValueError("Missing stops or unexpected route/direction")
        return stops


def vehicle_ids(stops):
    ids = set()
    for stop in stops:
        candidates = [stop.get("carId")]
        candidates.extend(eta.get("busId") for eta in (stop.get("etas") or []))
        for candidate in candidates:
            ids.update(part.strip() for part in text(candidate).split(",") if part.strip())
    return sorted(ids)


def main():
    output = ROOT / "build"
    output.mkdir(exist_ok=True)
    # Leave outputs missing on failure so the workflow can restore previous data.
    for lang in ("zh", "en"):
        (output / f"bus_info_data_{lang}.json").unlink(missing_ok=True)
    routes = {
        lang: json.loads((ROOT / f"bus_list_{lang}.json").read_text(encoding="utf-8"))
        for lang in ("zh", "en")
    }
    with requests.Session() as session:
        session.headers.update({"Content-Type": "application/json", "X-Api-Version": "1"})
        refresh_token(session)
        for route in routes["zh"]:
            route_id = route["RouteID"]
            stops = fetch_stops(session, route_id, 0) + fetch_stops(session, route_id, 1)
            ids = vehicle_ids(stops)
            for lang, items in routes.items():
                item = next(item for item in items if item["RouteID"] == route_id)
                name_key = "Name" if lang == "zh" else "NameEn"
                api_name = text(stops[0].get("routename_Zh_Tw" if lang == "zh" else "routename_En"))
                item[name_key] = api_name or item[name_key]
                # Keep static endpoints, including their English translations.
                item.update({
                    "StopName": "" if ids else ("未行駛" if lang == "zh" else "Out of service"),
                    "isOpenData": "Y",
                    "UpdateTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                })
                if ids:
                    item["CarID"] = ",".join(ids) + ","
            print(f"{route_id}: {len(ids)} observed vehicles")
    for lang, items in routes.items():
        (output / f"bus_info_data_{lang}.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=4), encoding="utf-8",
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Crawler failed ({type(error).__name__}); use previous data") from None
