import os
import uuid
from datetime import datetime

import mysql.connector
from flask import url_for
from werkzeug.utils import secure_filename


STAFF_ROLE_TABLES = {
    'worker': 'village_workers',
    'admin': 'taluka_admins',
    'district_admin': 'district_admins',
}

STAFF_VERIFICATION_COLUMNS = {
    'aadhaar_no': "ALTER TABLE {table_name} ADD COLUMN aadhaar_no VARCHAR(20) DEFAULT NULL",
    'aadhaar_photo_path': "ALTER TABLE {table_name} ADD COLUMN aadhaar_photo_path VARCHAR(255) DEFAULT NULL",
    'selfie_photo_path': "ALTER TABLE {table_name} ADD COLUMN selfie_photo_path VARCHAR(255) DEFAULT NULL",
    'verification_status': "ALTER TABLE {table_name} ADD COLUMN verification_status VARCHAR(20) DEFAULT 'pending'",
    'verification_notes': "ALTER TABLE {table_name} ADD COLUMN verification_notes TEXT DEFAULT NULL",
    'verified_by_role': "ALTER TABLE {table_name} ADD COLUMN verified_by_role VARCHAR(30) DEFAULT NULL",
    'verified_by_id': "ALTER TABLE {table_name} ADD COLUMN verified_by_id INT DEFAULT NULL",
    'verified_at': "ALTER TABLE {table_name} ADD COLUMN verified_at TIMESTAMP NULL DEFAULT NULL",
}

VERIFICATION_STATUS_LABELS = {
    'pending': 'Pending Review',
    'approved': 'Verified',
    'rejected': 'Rejected',
}

ANNOUNCEMENT_TARGET_ROLES = ('district_admin', 'admin', 'worker')


def _column_name(row):
    if isinstance(row, dict):
        return row.get('Field')
    if isinstance(row, (list, tuple)) and row:
        return row[0]
    return None


def _table_columns(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    return {name for name in (_column_name(row) for row in (cursor.fetchall() or [])) if name}


def ensure_columns(cursor, table_name, column_map):
    existing_columns = _table_columns(cursor, table_name)
    for column_name, ddl in (column_map or {}).items():
        if column_name not in existing_columns:
            cursor.execute(ddl.format(table_name=table_name))
            existing_columns.add(column_name)
    return existing_columns


def ensure_staff_verification_columns(cursor, table_name):
    return ensure_columns(cursor, table_name, STAFF_VERIFICATION_COLUMNS)


def ensure_staff_portal_schema(cursor):
    ensure_state_admin_table(cursor)
    ensure_announcements_table(cursor)
    for table_name in STAFF_ROLE_TABLES.values():
        ensure_staff_verification_columns(cursor, table_name)


def ensure_state_admin_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_admins (
                id INT NOT NULL AUTO_INCREMENT,
                name VARCHAR(100) DEFAULT NULL,
                email VARCHAR(100) DEFAULT NULL,
                phone VARCHAR(20) DEFAULT NULL,
                password VARCHAR(255) DEFAULT NULL,
                state_id INT DEFAULT NULL,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY idx_state_admin_state_id (state_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """)
    except mysql.connector.Error as err:
        if getattr(err, 'errno', None) != 1050:
            raise


def ensure_announcements_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INT NOT NULL AUTO_INCREMENT,
                title VARCHAR(200) NOT NULL,
                message TEXT NOT NULL,
                author_role VARCHAR(30) NOT NULL,
                author_id INT NOT NULL,
                author_name VARCHAR(120) DEFAULT NULL,
                target_roles VARCHAR(120) DEFAULT NULL,
                state_id INT DEFAULT NULL,
                district_id INT DEFAULT NULL,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY idx_announcements_state_id (state_id),
                KEY idx_announcements_district_id (district_id),
                KEY idx_announcements_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """)
    except mysql.connector.Error as err:
        if getattr(err, 'errno', None) != 1050:
            raise


def ensure_announcement_views_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcement_views (
                id INT NOT NULL AUTO_INCREMENT,
                announcement_id INT NOT NULL,
                viewer_role VARCHAR(30) NOT NULL,
                viewer_id INT NOT NULL,
                seen_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uniq_announcement_view (announcement_id, viewer_role, viewer_id),
                KEY idx_announcement_views_viewer (viewer_role, viewer_id),
                CONSTRAINT announcement_views_announcement_fk
                    FOREIGN KEY (announcement_id) REFERENCES announcements (id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """)
    except mysql.connector.Error as err:
        if getattr(err, 'errno', None) != 1050:
            raise


def normalize_verification_status(status, default='pending'):
    clean_status = (status or '').strip().lower()
    if clean_status not in VERIFICATION_STATUS_LABELS:
        return default
    return clean_status


def verification_status_label(status):
    return VERIFICATION_STATUS_LABELS.get(normalize_verification_status(status), VERIFICATION_STATUS_LABELS['pending'])


def verification_status_class(status):
    return normalize_verification_status(status).replace('_', '-')


def staff_role_requires_verification(role):
    return role in STAFF_ROLE_TABLES


def save_verification_upload(file_storage, root_path, prefix='verification'):
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return None

    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'jpg'
    unique_filename = f"{prefix}_{uuid.uuid4().hex}.{extension}"
    upload_folder = os.path.join(root_path, 'static', 'uploads', 'verifications')
    os.makedirs(upload_folder, exist_ok=True)
    file_storage.save(os.path.join(upload_folder, unique_filename))
    return unique_filename


def verification_file_url(filename):
    clean_name = (filename or '').strip()
    if not clean_name:
        return ''
    return url_for('static', filename=f'uploads/verifications/{clean_name}')


def attach_verification_urls(record):
    if not record:
        return record

    record['verification_status'] = normalize_verification_status(record.get('verification_status'))
    record['verification_status_label'] = verification_status_label(record.get('verification_status'))
    record['verification_status_class'] = verification_status_class(record.get('verification_status'))
    record['aadhaar_photo_url'] = verification_file_url(record.get('aadhaar_photo_path'))
    record['selfie_photo_url'] = verification_file_url(record.get('selfie_photo_path'))
    record['has_aadhaar_photo'] = bool(record['aadhaar_photo_url'])
    record['has_selfie_photo'] = bool(record['selfie_photo_url'])
    return record


def encode_target_roles(target_roles=None):
    roles = []
    for role in (target_roles or ANNOUNCEMENT_TARGET_ROLES):
        if role in ANNOUNCEMENT_TARGET_ROLES and role not in roles:
            roles.append(role)
    return ','.join(roles) or ','.join(ANNOUNCEMENT_TARGET_ROLES)


def decode_target_roles(raw_value):
    roles = []
    for role in (raw_value or '').split(','):
        clean_role = role.strip()
        if clean_role in ANNOUNCEMENT_TARGET_ROLES and clean_role not in roles:
            roles.append(clean_role)
    return roles


def role_display_name(role):
    mapping = {
        'worker': 'Worker',
        'admin': 'Taluka Admin',
        'district_admin': 'District Admin',
        'state_admin': 'State Admin',
    }
    return mapping.get(role, (role or 'Staff').replace('_', ' ').title())


def format_announcement_row(row):
    announcement = dict(row or {})
    announcement['target_roles_list'] = decode_target_roles(announcement.get('target_roles'))
    announcement['target_roles_text'] = ', '.join(role_display_name(role) for role in announcement['target_roles_list'])
    created_at = announcement.get('created_at')
    if isinstance(created_at, datetime):
        announcement['created_at_text'] = created_at.strftime('%d %b %Y %I:%M %p')
    else:
        announcement['created_at_text'] = 'Recently'
    announcement['scope_label'] = 'State Wide' if not announcement.get('district_id') else 'District Level'
    announcement['author_role_label'] = role_display_name(announcement.get('author_role'))
    return announcement


def fetch_visible_announcements(cursor, role, state_id=None, district_id=None, limit=8):
    ensure_announcements_table(cursor)

    if role not in ANNOUNCEMENT_TARGET_ROLES and role != 'state_admin':
        return []
    if not state_id:
        return []

    cursor.execute("""
        SELECT
            id,
            title,
            message,
            author_role,
            author_id,
            author_name,
            target_roles,
            state_id,
            district_id,
            created_at
        FROM announcements
        WHERE state_id = %s
          AND (%s = 'state_admin' OR district_id IS NULL OR district_id = %s)
        ORDER BY created_at DESC
        LIMIT %s
    """, (state_id, role, district_id, max(int(limit), 1)))

    announcements = []
    for row in cursor.fetchall() or []:
        formatted = format_announcement_row(row)
        targets = formatted.get('target_roles_list') or list(ANNOUNCEMENT_TARGET_ROLES)
        if role == 'state_admin' or role in targets:
            announcements.append(formatted)
    return announcements


def fetch_unread_announcements(cursor, role, viewer_id, state_id=None, district_id=None, limit=8):
    ensure_announcements_table(cursor)
    ensure_announcement_views_table(cursor)

    if role not in ANNOUNCEMENT_TARGET_ROLES or not viewer_id or not state_id:
        return []

    cursor.execute("""
        SELECT
            a.id,
            a.title,
            a.message,
            a.author_role,
            a.author_id,
            a.author_name,
            a.target_roles,
            a.state_id,
            a.district_id,
            a.created_at
        FROM announcements a
        LEFT JOIN announcement_views av
            ON av.announcement_id = a.id
           AND av.viewer_role = %s
           AND av.viewer_id = %s
        WHERE a.state_id = %s
          AND (a.district_id IS NULL OR a.district_id = %s)
          AND av.id IS NULL
        ORDER BY a.created_at DESC
        LIMIT %s
    """, (role, viewer_id, state_id, district_id, max(int(limit), 1)))

    announcements = []
    for row in cursor.fetchall() or []:
        formatted = format_announcement_row(row)
        targets = formatted.get('target_roles_list') or list(ANNOUNCEMENT_TARGET_ROLES)
        if role in targets:
            announcements.append(formatted)
    return announcements


def mark_announcements_seen(cursor, role, viewer_id, announcement_ids):
    ensure_announcements_table(cursor)
    ensure_announcement_views_table(cursor)

    if role not in ANNOUNCEMENT_TARGET_ROLES or not viewer_id:
        return 0

    clean_ids = []
    for announcement_id in announcement_ids or []:
        try:
            parsed = int(announcement_id)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in clean_ids:
            clean_ids.append(parsed)

    if not clean_ids:
        return 0

    placeholders = ', '.join(['%s'] * len(clean_ids))
    cursor.execute(f"""
        SELECT id, target_roles
        FROM announcements
        WHERE id IN ({placeholders})
    """, tuple(clean_ids))

    allowed_ids = []
    for row in cursor.fetchall() or []:
        targets = decode_target_roles((row or {}).get('target_roles'))
        if role in (targets or ANNOUNCEMENT_TARGET_ROLES):
            allowed_ids.append((row or {}).get('id'))

    for announcement_id in allowed_ids:
        cursor.execute("""
            INSERT IGNORE INTO announcement_views (announcement_id, viewer_role, viewer_id)
            VALUES (%s, %s, %s)
        """, (announcement_id, role, viewer_id))

    return len(allowed_ids)
