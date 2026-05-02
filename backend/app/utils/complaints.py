import os
import uuid

from werkzeug.utils import secure_filename


COMPLAINT_STATUS_MAP = {
    'pending': ('pending', 'Pending'),
    'assigned': ('assigned', 'Assigned'),
    'in progress': ('in_progress', 'In Progress'),
    'in_progress': ('in_progress', 'In Progress'),
    'completed': ('completed', 'Completed'),
}

COMPLAINT_PROGRESS_MAP = {
    'pending': 25,
    'assigned': 50,
    'in_progress': 75,
    'completed': 100,
}

COMPLAINT_WORKFLOW_COLUMNS = {
    'admin_id': "ALTER TABLE complaints ADD COLUMN admin_id INT DEFAULT NULL",
    'worker_id': "ALTER TABLE complaints ADD COLUMN worker_id INT DEFAULT NULL",
    'assigned_at': "ALTER TABLE complaints ADD COLUMN assigned_at TIMESTAMP NULL DEFAULT NULL",
    'updated_at': "ALTER TABLE complaints ADD COLUMN updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP",
    'resolved_at': "ALTER TABLE complaints ADD COLUMN resolved_at TIMESTAMP NULL DEFAULT NULL",
    'latitude': "ALTER TABLE complaints ADD COLUMN latitude DECIMAL(10, 7) DEFAULT NULL",
    'longitude': "ALTER TABLE complaints ADD COLUMN longitude DECIMAL(10, 7) DEFAULT NULL",
    'location_accuracy_meters': "ALTER TABLE complaints ADD COLUMN location_accuracy_meters DECIMAL(10, 2) DEFAULT NULL",
    'resolution_photo_path': "ALTER TABLE complaints ADD COLUMN resolution_photo_path VARCHAR(255) DEFAULT NULL",
}

COMPLAINT_IMAGE_COLUMNS = ('photo_path', 'garbage_img')


def _column_name(row):
    if isinstance(row, dict):
        return row.get('Field')
    if isinstance(row, (list, tuple)) and row:
        return row[0]
    return None


def get_complaint_columns(cursor):
    cursor.execute("SHOW COLUMNS FROM complaints")
    return {name for name in (_column_name(row) for row in (cursor.fetchall() or [])) if name}


def ensure_complaint_workflow_columns(cursor):
    existing_columns = get_complaint_columns(cursor)
    for column_name, ddl in COMPLAINT_WORKFLOW_COLUMNS.items():
        if column_name not in existing_columns:
            cursor.execute(ddl)
            existing_columns.add(column_name)
    return existing_columns


def complaint_original_photo_column(existing_columns):
    for column_name in COMPLAINT_IMAGE_COLUMNS:
        if column_name in (existing_columns or set()):
            return column_name
    return None


def complaint_original_photo_select(existing_columns, table_alias='c', output_alias='original_photo_path'):
    column_name = complaint_original_photo_column(existing_columns)
    if not column_name:
        return f"NULL AS {output_alias}"
    return f"{table_alias}.{column_name} AS {output_alias}"


def save_complaint_upload(file_storage, root_path, prefix='complaint'):
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return None

    filename = secure_filename(file_storage.filename)
    if '.' in filename:
        extension = filename.rsplit('.', 1)[1].lower()
    else:
        extension = 'jpg'

    unique_filename = f"{prefix}_{uuid.uuid4().hex}.{extension}"
    upload_folder = os.path.join(root_path, 'static', 'uploads', 'complaints')
    os.makedirs(upload_folder, exist_ok=True)
    file_storage.save(os.path.join(upload_folder, unique_filename))
    return unique_filename


def complaint_status_key(status, default='pending'):
    raw_status = (status or '').strip().lower()
    return COMPLAINT_STATUS_MAP.get(raw_status, COMPLAINT_STATUS_MAP[default])[0]


def normalize_complaint_status(status, default='Pending'):
    default_key = complaint_status_key(default)
    raw_status = (status or '').strip().lower()
    return COMPLAINT_STATUS_MAP.get(raw_status, COMPLAINT_STATUS_MAP[default_key])[1]


def complaint_status_class(status, default='pending'):
    return complaint_status_key(status, default=default).replace('_', '-')


def complaint_progress_percent(status, default='pending'):
    return COMPLAINT_PROGRESS_MAP.get(complaint_status_key(status, default=default), COMPLAINT_PROGRESS_MAP[default])
