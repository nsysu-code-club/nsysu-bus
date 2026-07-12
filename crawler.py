import json
import requests
import urllib3
import os
from datetime import datetime

urllib3.disable_warnings()

URL = "https://ibus.tbkc.gov.tw/ibus/graphql"

QUERY_ROUTE = """
fragment busesFragment on RouteBusConnection { edges { node { id } } }
query QUERY_ROUTE_FOR_MAP_CONTENT($routeId: Int!, $lang: String!) {
    route(xno: $routeId, lang: $lang) {
        departure
        destination
        buses { ...busesFragment }
    }
}
"""

QUERY_SIDE_ROUTES = """
query QUERY_SIDE_ROUTES($lang: String!) {
    routes(lang: $lang) {
        edges {
            node {
                id, opType, seq, name, description
            }
        }
    }
}
"""

def fetch_all_routes_info(lang):
    try:
        response = requests.post(
            URL, 
            json={'query': QUERY_SIDE_ROUTES, 'variables': {'lang': lang}}, 
            verify=False,
            timeout=10
        )
        data = response.json()
        routes_map = {}
        if 'data' in data and data['data']['routes']:
            for edge in data['data']['routes']['edges']:
                node = edge['node']
                routes_map[int(node['id'])] = node['name']
        return routes_map
    except Exception as e:
        print(f"Error fetching all routes for {lang}: {e}")
    return {}

def fetch_route_data(route_id, lang):
    try:
        response = requests.post(
            URL, 
            json={'query': QUERY_ROUTE, 'variables': {'routeId': route_id, 'lang': lang}}, 
            verify=False,
            timeout=10
        )
        data = response.json()
        if 'data' in data and data['data']['route']:
            return data['data']['route']
    except Exception as e:
        print(f"Error fetching route {route_id} for {lang}: {e}")
    return None

def process_language(lang_code, list_file, output_file, name_key, dep_key, dest_key):
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            routes = json.load(f)
    except Exception as e:
        print(f"Error reading {list_file}: {e}")
        return

    routes_info_map = fetch_all_routes_info(lang_code)

    result = []
    for route in routes:
        route_id = route.get('RouteID')
        if not route_id:
            continue
        
        print(f"Fetching {route_id} ({lang_code})...")
        route_data = fetch_route_data(route_id, lang_code)
        
        car_ids = ""
        departure = route.get(dep_key, "")
        destination = route.get(dest_key, "")
        name = routes_info_map.get(route_id, route.get(name_key, ""))
        
        if route_data:
            # Get buses
            buses = route_data.get('buses', {}).get('edges', [])

            if buses:
                car_ids = "".join([bus['node']['id'] + "," for bus in buses])
            
            # Optionally update departure/destination from API if preferred, 
            # but the existing json seems to use its own or we can use API's
            # For now let's use what the API returned, or fallback to the list
            if route_data.get('departure'):
                departure = route_data['departure']
            if route_data.get('destination'):
                destination = route_data['destination']

        stop_name = ""
        if not car_ids:
            stop_name = "未行駛" if lang_code == "zh" else "Out of service"

        item = {
            "CarID": car_ids,
            "StopName": stop_name,
            "RouteID": route_id,
            name_key: name,
            "isOpenData": "Y",
            dep_key: departure,
            dest_key: destination,
            "UpdateTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        }
        # In bus_info_data_zh.json, "Name" is used instead of "NameZh" or something
        if lang_code == "zh" and "Name" in item:
            pass # Name is already the key
            
        result.append(item)

    # ensure the build directory exists
    os.makedirs('build', exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    print(f"Saved {len(result)} routes to {output_file}")

def main():
    print("Processing English routes...")
    process_language(
        lang_code='en', 
        list_file='bus_list_en.json', 
        output_file='build/bus_info_data_en.json',
        name_key='NameEn',
        dep_key='DepartureEn',
        dest_key='DestinationEn'
    )
    
    print("Processing Traditional Chinese routes...")
    process_language(
        lang_code='zh', 
        list_file='bus_list_zh.json', 
        output_file='build/bus_info_data_zh.json',
        name_key='Name',
        dep_key='Departure',
        dest_key='Destination'
    )

if __name__ == '__main__':
    main()
