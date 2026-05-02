from urllib.parse import quote_plus


REQUEST_LOCATION_COLUMNS = {
    'latitude': "ALTER TABLE requests ADD COLUMN latitude DECIMAL(10, 7) DEFAULT NULL",
    'longitude': "ALTER TABLE requests ADD COLUMN longitude DECIMAL(10, 7) DEFAULT NULL",
    'location_accuracy_meters': "ALTER TABLE requests ADD COLUMN location_accuracy_meters DECIMAL(10, 2) DEFAULT NULL",
}
MAX_LOCATION_ACCURACY_METERS = 500


def _column_name(row):
    if isinstance(row, dict):
        return row.get('Field')
    if isinstance(row, (list, tuple)) and row:
        return row[0]
    return None


def get_table_columns(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    return {name for name in (_column_name(row) for row in (cursor.fetchall() or [])) if name}


def ensure_table_columns(cursor, table_name, column_ddls):
    existing_columns = get_table_columns(cursor, table_name)
    for column_name, ddl in column_ddls.items():
        if column_name not in existing_columns:
            cursor.execute(ddl)
            existing_columns.add(column_name)
    return existing_columns


def ensure_request_location_columns(cursor):
    return ensure_table_columns(cursor, 'requests', REQUEST_LOCATION_COLUMNS)


def normalize_coordinate(value, minimum, maximum):
    if value in (None, ''):
        return None

    try:
        numeric_value = round(float(value), 7)
    except (TypeError, ValueError):
        return None

    if numeric_value < minimum or numeric_value > maximum:
        return None
    return numeric_value


def normalize_accuracy(value):
    if value in (None, ''):
        return None

    try:
        numeric_value = round(float(value), 2)
    except (TypeError, ValueError):
        return None

    return numeric_value if numeric_value >= 0 else None


def parse_submitted_location(form_data):
    latitude_raw = (form_data.get('latitude') or '').strip()
    longitude_raw = (form_data.get('longitude') or '').strip()
    accuracy_raw = (form_data.get('location_accuracy_meters') or '').strip()

    if not latitude_raw and not longitude_raw and not accuracy_raw:
        return {
            'latitude': None,
            'longitude': None,
            'location_accuracy_meters': None,
        }

    latitude = normalize_coordinate(latitude_raw, -90, 90)
    longitude = normalize_coordinate(longitude_raw, -180, 180)
    accuracy = normalize_accuracy(accuracy_raw)

    if latitude is None or longitude is None:
        raise ValueError("Please capture a valid live location before submitting.")
    if accuracy is not None and accuracy > MAX_LOCATION_ACCURACY_METERS:
        raise ValueError(
            f"Captured live location is too broad ({round(accuracy)} meters). Move outdoors, enable phone GPS, and capture again."
        )

    return {
        'latitude': latitude,
        'longitude': longitude,
        'location_accuracy_meters': accuracy,
    }


def _normalized_coordinate_pair(latitude, longitude):
    latitude_value = normalize_coordinate(latitude, -90, 90)
    longitude_value = normalize_coordinate(longitude, -180, 180)
    if latitude_value is None or longitude_value is None:
        return None, None
    return latitude_value, longitude_value


def format_coordinates(latitude, longitude):
    latitude_value, longitude_value = _normalized_coordinate_pair(latitude, longitude)
    if latitude_value is None or longitude_value is None:
        return ''
    return f"{latitude_value:.6f}, {longitude_value:.6f}"


def format_map_coordinates(latitude, longitude):
    latitude_value, longitude_value = _normalized_coordinate_pair(latitude, longitude)
    if latitude_value is None or longitude_value is None:
        return ''
    return f"{latitude_value:.6f},{longitude_value:.6f}"


def build_map_url(latitude=None, longitude=None, query=None, directions=False):
    coordinate_text = format_map_coordinates(latitude, longitude)
    if coordinate_text:
        if directions:
            return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(coordinate_text)}"
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(coordinate_text)}"

    clean_query = (query or '').strip()
    if not clean_query:
        return ''

    if directions:
        return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(clean_query)}"
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(clean_query)}"


def build_location_payload(latitude=None, longitude=None, accuracy=None, query=None, directions=False):
    latitude_value, longitude_value = _normalized_coordinate_pair(latitude, longitude)
    accuracy_value = normalize_accuracy(accuracy)
    has_coordinates = latitude_value is not None and longitude_value is not None

    return {
        'latitude': latitude_value,
        'longitude': longitude_value,
        'location_accuracy_meters': accuracy_value,
        'has_coordinates': has_coordinates,
        'coordinates_text': format_coordinates(latitude_value, longitude_value),
        'map_url': build_map_url(latitude_value, longitude_value, query=query, directions=directions),
    }
