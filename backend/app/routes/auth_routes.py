from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.db import get_db
from app.utils.complaints import (
    complaint_progress_percent,
    complaint_status_class,
    complaint_status_key,
    ensure_complaint_workflow_columns,
    normalize_complaint_status,
)
from datetime import datetime

auth_bp = Blueprint('auth_bp', __name__)

# Helper to map roles to table names
ROLE_MAP = {
    'district_admin': 'district_admins',
    'admin': 'taluka_admins',
    'worker': 'village_workers',
    'user': 'users'
}

MAP_PRESET_CENTERS = {
    'akole': {'lat': 19.5318, 'lng': 73.9975},
}


def _post_redirect_target(default_endpoint):
    next_page = (request.form.get('next_page') or '').strip()
    if next_page.startswith('/'):
        return next_page

    referrer = (request.referrer or '').strip()
    if referrer.startswith(request.host_url):
        return referrer

    return url_for(default_endpoint)


def _empty_worker_counts():
    return {
        'total_tasks': 0,
        'completed_tasks': 0,
        'active_tasks': 0,
        'open_tasks': 0,
        'pending_tasks': 0,
        'in_progress_tasks': 0,
    }


def _merge_worker_counts(target, source):
    target['total_tasks'] += source.get('total_tasks') or 0
    target['completed_tasks'] += source.get('completed_tasks') or 0
    target['active_tasks'] += source.get('active_tasks') or 0
    target['open_tasks'] += source.get('active_tasks') or 0
    target['pending_tasks'] += source.get('pending_tasks') or 0
    target['in_progress_tasks'] += source.get('in_progress_tasks') or 0


def _format_timestamp(value, include_time=False):
    if not value:
        return 'N/A'
    return value.strftime('%d %b %Y %I:%M %p') if include_time else value.strftime('%d %b %Y')


def _slug_text(value):
    return (value or '').strip().lower()


def _build_map_query(*parts):
    return ', '.join([part.strip() for part in parts if part and str(part).strip()])


def _is_today(value):
    if not value or not hasattr(value, 'date'):
        return False
    return value.date() == datetime.now().date()


def _taluka_scope_center(taluka_name):
    return MAP_PRESET_CENTERS.get(_slug_text(taluka_name))


def _build_worker_map_config(worker_profile):
    if not worker_profile:
        return {
            'center': None,
            'center_query': '',
            'scope_label': 'Assigned Area',
        }

    return {
        'center': _taluka_scope_center(worker_profile.get('taluka_name')),
        'center_query': _build_map_query(
            worker_profile.get('village_name'),
            worker_profile.get('taluka_name'),
            worker_profile.get('district_name'),
            'Maharashtra',
            'India',
        ),
        'scope_label': worker_profile.get('taluka_name') or worker_profile.get('village_name') or 'Assigned Area',
    }


def _build_taluka_map_payload(admin_profile, complaints, requests, assigned_tasks):
    taluka_name = admin_profile.get('taluka_name')
    district_name = admin_profile.get('district_name')
    markers = []

    for complaint in complaints or []:
        status_label = complaint.get('status') or 'Pending'
        status_key = complaint_status_class(status_label)
        filed_at = complaint.get('created_at')
        updated_at = complaint.get('updated_at') or complaint.get('resolved_at') or complaint.get('assigned_at') or filed_at
        markers.append({
            'id': f"CMP-{complaint.get('id')}",
            'category': 'complaint',
            'category_label': 'Complaint',
            'title': complaint.get('title') or 'Complaint',
            'description': complaint.get('description') or 'Citizen complaint',
            'status': status_key,
            'status_label': status_label,
            'location_label': complaint.get('village') or taluka_name or 'Complaint Area',
            'map_query': _build_map_query(
                complaint.get('village'),
                complaint.get('taluka') or taluka_name,
                district_name,
                'Maharashtra',
                'India',
            ),
            'secondary_label': complaint.get('citizen_name') or 'Citizen',
            'assigned_to': complaint.get('worker_name') or 'Unassigned',
            'time_label': _format_timestamp(updated_at, include_time=True),
            'sort_at': updated_at.isoformat() if updated_at else '',
            'is_today': _is_today(filed_at),
            'is_open': status_key != 'completed',
        })

    for pickup_request in requests or []:
        status_key = (pickup_request.get('status') or 'pending').lower()
        created_at = pickup_request.get('created_at')
        markers.append({
            'id': f"REQ-{pickup_request.get('id')}",
            'category': 'request',
            'category_label': 'Pickup Request',
            'title': pickup_request.get('garbage_type') or 'Garbage Collection',
            'description': f"Pickup request from {pickup_request.get('citizen_name') or 'Citizen'}",
            'status': status_key,
            'status_label': status_key.replace('_', ' ').title(),
            'location_label': pickup_request.get('village_name') or taluka_name or 'Taluka Area',
            'map_query': _build_map_query(
                pickup_request.get('village_name'),
                taluka_name,
                district_name,
                'Maharashtra',
                'India',
            ),
            'secondary_label': pickup_request.get('citizen_name') or 'Citizen',
            'assigned_to': pickup_request.get('worker_name') or 'Unassigned',
            'time_label': _format_timestamp(created_at, include_time=True),
            'sort_at': created_at.isoformat() if created_at else '',
            'is_today': _is_today(created_at),
            'is_open': status_key != 'completed',
        })

    for assigned_task in assigned_tasks or []:
        status_key = (assigned_task.get('status') or 'pending').lower()
        assigned_at = assigned_task.get('assigned_at')
        markers.append({
            'id': f"TASK-{assigned_task.get('id')}",
            'category': 'assigned_task',
            'category_label': 'Assigned Task',
            'title': assigned_task.get('description') or assigned_task.get('location_name') or 'Assigned task',
            'description': assigned_task.get('description') or 'Manual task assigned by taluka office',
            'status': status_key,
            'status_label': status_key.replace('_', ' ').title(),
            'location_label': assigned_task.get('location_name') or assigned_task.get('village_name') or taluka_name or 'Assigned Area',
            'map_query': _build_map_query(
                assigned_task.get('location_name') or assigned_task.get('village_name'),
                taluka_name,
                district_name,
                'Maharashtra',
                'India',
            ),
            'secondary_label': assigned_task.get('worker_name') or 'Worker',
            'assigned_to': assigned_task.get('worker_name') or 'Worker',
            'time_label': _format_timestamp(assigned_at, include_time=True),
            'sort_at': assigned_at.isoformat() if assigned_at else '',
            'is_today': _is_today(assigned_at),
            'is_open': status_key != 'completed',
        })

    markers.sort(key=lambda item: item.get('sort_at') or '', reverse=True)

    today_counts = {
        'complaints': sum(1 for item in markers if item.get('category') == 'complaint' and item.get('is_today')),
        'requests': sum(1 for item in markers if item.get('category') == 'request' and item.get('is_today')),
        'assigned_tasks': sum(1 for item in markers if item.get('category') == 'assigned_task' and item.get('is_today')),
    }
    today_counts['total'] = sum(today_counts.values())

    return {
        'scope_label': f"{taluka_name or 'Taluka'} Scope",
        'center': _taluka_scope_center(taluka_name),
        'center_query': _build_map_query(taluka_name, district_name, 'Maharashtra', 'India'),
        'markers': markers,
        'today_counts': today_counts,
        'open_total': sum(1 for item in markers if item.get('is_open')),
    }


def _format_user_complaint(complaint):
    status_text = normalize_complaint_status(complaint.get('status'))
    normalized_status = complaint_status_class(status_text)
    last_update = complaint.get('updated_at') or complaint.get('resolved_at') or complaint.get('assigned_at') or complaint.get('created_at')
    return {
        'ticket_id': complaint.get('id'),
        'title': complaint.get('title') or 'Complaint',
        'village': complaint.get('village') or 'Unknown Village',
        'taluka': complaint.get('taluka') or 'Unknown Taluka',
        'priority': complaint.get('priority') or 'Normal',
        'status_text': status_text,
        'status_class': normalized_status,
        'progress_percent': complaint_progress_percent(status_text),
        'assigned_worker': complaint.get('worker_name') or 'Pending Assignment',
        'admin_name': complaint.get('admin_name') or 'Taluka Office',
        'date': _format_timestamp(complaint.get('created_at')),
        'last_update': _format_timestamp(last_update, include_time=True),
    }


def _get_user_complaints(user_id, cursor, limit=5):
    ensure_complaint_workflow_columns(cursor)
    query = """
        SELECT
            c.id,
            c.title,
            c.district,
            c.taluka,
            c.village,
            c.priority,
            c.status,
            c.created_at,
            c.assigned_at,
            c.updated_at,
            c.resolved_at,
            COALESCE(vw.name, 'Pending Assignment') AS worker_name,
            COALESCE(ta.name, 'Taluka Office') AS admin_name
        FROM complaints c
        LEFT JOIN village_workers vw ON c.worker_id = vw.id
        LEFT JOIN taluka_admins ta ON c.admin_id = ta.id
        WHERE c.user_id = %s
        ORDER BY c.created_at DESC
    """
    if limit is not None:
        query += f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(query, (user_id,))
    return [_format_user_complaint(complaint) for complaint in (cursor.fetchall() or [])]


def _get_taluka_complaints(admin_profile, cursor, limit=None):
    ensure_complaint_workflow_columns(cursor)

    query = """
        SELECT
            c.id,
            c.title,
            c.description,
            c.village,
            c.taluka,
            c.priority,
            c.status,
            c.created_at,
            c.assigned_at,
            c.updated_at,
            c.resolved_at,
            c.worker_id,
            COALESCE(u.name, 'Citizen') AS citizen_name,
            COALESCE(vw.name, 'Unassigned') AS worker_name
        FROM complaints c
        LEFT JOIN users u ON c.user_id = u.id
        LEFT JOIN village_workers vw ON c.worker_id = vw.id
        WHERE c.taluka = %s
        ORDER BY COALESCE(c.updated_at, c.assigned_at, c.created_at) DESC
    """
    if limit is not None:
        query += f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(query, (admin_profile.get('taluka_name'),))
    complaints = cursor.fetchall() or []
    for complaint in complaints:
        complaint['status'] = normalize_complaint_status(complaint.get('status'))
        complaint['status_class'] = complaint_status_class(complaint.get('status'))
        complaint['assigned_at_text'] = _format_timestamp(complaint.get('assigned_at'), include_time=True)
        complaint['updated_at_text'] = _format_timestamp(
            complaint.get('updated_at') or complaint.get('resolved_at') or complaint.get('assigned_at') or complaint.get('created_at'),
            include_time=True,
        )
    return complaints


def _get_worker_profile(worker_id, cursor):
    cursor.execute("""
        SELECT
            vw.id,
            vw.name,
            vw.email,
            vw.phone,
            vw.village_id,
            vw.vehicle_no,
            vw.status,
            vw.created_at,
            v.name AS village_name,
            t.name AS taluka_name,
            d.name AS district_name
        FROM village_workers vw
        LEFT JOIN villages v ON vw.village_id = v.id
        LEFT JOIN talukas t ON v.taluka_id = t.id
        LEFT JOIN districts d ON t.district_id = d.id
        WHERE vw.id = %s
    """, (worker_id,))
    return cursor.fetchone()


def _get_taluka_worker_options(taluka_id, cursor):
    cursor.execute("""
        SELECT
            vw.id,
            vw.name,
            vw.email,
            vw.phone,
            vw.vehicle_no,
            vw.status,
            vw.created_at,
            vw.village_id,
            COALESCE(v.name, 'Not assigned') AS village_name
        FROM village_workers vw
        LEFT JOIN villages v ON vw.village_id = v.id
        WHERE vw.village_id IN (SELECT id FROM villages WHERE taluka_id = %s)
        ORDER BY vw.name ASC
    """, (taluka_id,))
    workers = cursor.fetchall() or []
    if not workers:
        return []

    counts_by_worker = {worker['id']: _empty_worker_counts() for worker in workers}

    cursor.execute("""
        SELECT
            r.worker_id,
            COUNT(*) AS total_tasks,
            SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
            SUM(CASE WHEN r.status IN ('pending', 'in_progress') THEN 1 ELSE 0 END) AS active_tasks,
            SUM(CASE WHEN r.status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
            SUM(CASE WHEN r.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_tasks
        FROM requests r
        INNER JOIN village_workers vw ON vw.id = r.worker_id
        WHERE vw.village_id IN (SELECT id FROM villages WHERE taluka_id = %s)
        GROUP BY r.worker_id
    """, (taluka_id,))
    for row in cursor.fetchall() or []:
        counts = counts_by_worker.setdefault(row.get('worker_id'), _empty_worker_counts())
        _merge_worker_counts(counts, row)

    cursor.execute("""
        SELECT
            t.worker_id,
            COUNT(*) AS total_tasks,
            SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
            SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS active_tasks,
            SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
            0 AS in_progress_tasks
        FROM tasks t
        INNER JOIN village_workers vw ON vw.id = t.worker_id
        WHERE vw.village_id IN (SELECT id FROM villages WHERE taluka_id = %s)
        GROUP BY t.worker_id
    """, (taluka_id,))
    for row in cursor.fetchall() or []:
        counts = counts_by_worker.setdefault(row.get('worker_id'), _empty_worker_counts())
        _merge_worker_counts(counts, row)

    ensure_complaint_workflow_columns(cursor)
    cursor.execute("""
        SELECT
            c.worker_id,
            COUNT(*) AS total_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) IN ('pending', 'assigned', 'in progress', 'in_progress') THEN 1 ELSE 0 END) AS active_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) IN ('pending', 'assigned') THEN 1 ELSE 0 END) AS pending_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) IN ('in progress', 'in_progress') THEN 1 ELSE 0 END) AS in_progress_tasks
        FROM complaints c
        INNER JOIN village_workers vw ON vw.id = c.worker_id
        WHERE vw.village_id IN (SELECT id FROM villages WHERE taluka_id = %s)
        GROUP BY c.worker_id
    """, (taluka_id,))
    for row in cursor.fetchall() or []:
        counts = counts_by_worker.setdefault(row.get('worker_id'), _empty_worker_counts())
        _merge_worker_counts(counts, row)

    for worker in workers:
        worker.update(counts_by_worker.get(worker['id'], _empty_worker_counts()))

    return workers


def _get_taluka_village_rows(taluka_id, cursor):
    cursor.execute("""
        SELECT
            v.id,
            v.name,
            COUNT(DISTINCT u.id) AS citizens,
            COUNT(DISTINCT vw.id) AS workers,
            COUNT(r.id) AS total_requests,
            SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) AS completed_requests
        FROM villages v
        LEFT JOIN users u ON u.village_id = v.id
        LEFT JOIN village_workers vw ON vw.village_id = v.id
        LEFT JOIN requests r ON r.user_id = u.id
        WHERE v.taluka_id = %s
        GROUP BY v.id, v.name
        ORDER BY v.name ASC
    """, (taluka_id,))
    villages = cursor.fetchall() or []

    for village in villages:
        total_requests = village.get('total_requests') or 0
        completed_requests = village.get('completed_requests') or 0
        village['progress'] = round((completed_requests / total_requests) * 100) if total_requests else 0

    return villages


def _get_taluka_worker_record(taluka_id, worker_id, cursor):
    cursor.execute("""
        SELECT
            vw.id,
            vw.name,
            vw.village_id,
            COALESCE(v.name, 'Assigned Area') AS village_name
        FROM village_workers vw
        LEFT JOIN villages v ON vw.village_id = v.id
        WHERE vw.id = %s AND v.taluka_id = %s
    """, (worker_id, taluka_id))
    return cursor.fetchone()


def _get_taluka_recent_manual_tasks(taluka_id, cursor, limit=8):
    limit_clause = ""
    if limit is not None:
        limit_clause = f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(f"""
        SELECT
            t.id,
            t.worker_id,
            COALESCE(t.location_name, v.name, 'Assigned Area') AS location_name,
            COALESCE(t.description, 'Assigned task') AS description,
            COALESCE(t.priority, 'medium') AS priority,
            COALESCE(t.status, 'pending') AS status,
            t.assigned_at,
            COALESCE(vw.name, 'Unknown Worker') AS worker_name,
            COALESCE(v.name, 'Unknown Village') AS village_name
        FROM tasks t
        LEFT JOIN village_workers vw ON t.worker_id = vw.id
        LEFT JOIN villages v ON vw.village_id = v.id
        WHERE vw.village_id IN (SELECT id FROM villages WHERE taluka_id = %s)
        ORDER BY t.assigned_at DESC
        {limit_clause}
    """, (taluka_id,))
    return cursor.fetchall() or []


def _get_taluka_request_items(taluka_id, cursor, limit=None):
    limit_clause = ""
    if limit is not None:
        limit_clause = f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(f"""
        SELECT
            r.id,
            COALESCE(r.garbage_type, 'Garbage Collection') AS garbage_type,
            COALESCE(r.status, 'pending') AS status,
            COALESCE(r.amount, 0) AS amount,
            r.created_at,
            COALESCE(u.name, 'Citizen') AS citizen_name,
            COALESCE(v.name, 'Unknown Village') AS village_name,
            COALESCE(vw.name, 'Unassigned') AS worker_name,
            r.worker_id
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN villages v ON u.village_id = v.id
        LEFT JOIN village_workers vw ON r.worker_id = vw.id
        LEFT JOIN villages uv ON u.village_id = uv.id
        WHERE COALESCE(u.taluka_id, uv.taluka_id) = %s
        ORDER BY r.created_at DESC
        {limit_clause}
    """, (taluka_id,))

    request_items = cursor.fetchall() or []
    for request_item in request_items:
        request_item['status'] = (request_item.get('status') or 'pending').lower()
        request_item['status_label'] = request_item['status'].replace('_', ' ').title()
    return request_items


def _get_worker_assignment_stats(worker_id, cursor):
    cursor.execute("""
        SELECT
            COUNT(*) AS assigned,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'completed' AND DATE(created_at) = CURDATE() THEN 1 ELSE 0 END) AS completed_today,
            COALESCE(SUM(CASE WHEN MONTH(created_at) = MONTH(CURDATE()) AND YEAR(created_at) = YEAR(CURDATE()) THEN amount ELSE 0 END), 0) AS monthly_earnings,
            COALESCE(SUM(CASE WHEN DATE(created_at) = CURDATE() THEN amount ELSE 0 END), 0) AS today_earnings
        FROM requests
        WHERE worker_id = %s
    """, (worker_id,))
    request_stats = cursor.fetchone() or {}

    cursor.execute("""
        SELECT
            COUNT(*) AS assigned,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM tasks
        WHERE worker_id = %s
    """, (worker_id,))
    manual_task_stats = cursor.fetchone() or {}

    assigned = (request_stats.get('assigned') or 0) + (manual_task_stats.get('assigned') or 0)
    pending = (request_stats.get('pending') or 0) + (manual_task_stats.get('pending') or 0)
    in_progress = request_stats.get('in_progress') or 0
    completed = (request_stats.get('completed') or 0) + (manual_task_stats.get('completed') or 0)
    completed_today = request_stats.get('completed_today') or 0

    ensure_complaint_workflow_columns(cursor)
    cursor.execute("""
        SELECT
            COUNT(*) AS assigned,
            SUM(CASE WHEN LOWER(COALESCE(status, 'Pending')) IN ('pending', 'assigned') THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN LOWER(COALESCE(status, 'Pending')) IN ('in progress', 'in_progress') THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN LOWER(COALESCE(status, 'Pending')) = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(
                CASE
                    WHEN LOWER(COALESCE(status, 'Pending')) = 'completed'
                     AND DATE(COALESCE(resolved_at, updated_at, created_at)) = CURDATE()
                    THEN 1
                    ELSE 0
                END
            ) AS completed_today
        FROM complaints
        WHERE worker_id = %s
    """, (worker_id,))
    complaint_stats = cursor.fetchone() or {}

    assigned += complaint_stats.get('assigned') or 0
    pending += complaint_stats.get('pending') or 0
    in_progress += complaint_stats.get('in_progress') or 0
    completed += complaint_stats.get('completed') or 0
    completed_today += complaint_stats.get('completed_today') or 0

    return {
        'assigned': assigned,
        'pending': pending,
        'in_progress': in_progress,
        'completed': completed,
        'completed_today': completed_today,
        'monthly_earnings': request_stats.get('monthly_earnings') or 0,
        'today_earnings': request_stats.get('today_earnings') or 0,
        'total_tasks': assigned,
        'pending_tasks': pending,
        'in_progress_tasks': in_progress,
        'completed_tasks': completed,
    }


def _get_worker_work_items(worker_id, cursor, worker_profile=None, status_filter='all', limit=None):
    worker_village_id = worker_profile.get('village_id') if worker_profile else None
    worker_taluka_name = worker_profile.get('taluka_name') if worker_profile else None
    worker_district_name = worker_profile.get('district_name') if worker_profile else None

    request_status_clause = ""
    task_status_clause = ""
    complaint_status_clause = ""
    if status_filter == 'active':
        request_status_clause = "AND COALESCE(r.status, 'pending') IN ('pending', 'in_progress')"
        task_status_clause = "AND COALESCE(t.status, 'pending') = 'pending'"
        complaint_status_clause = "AND LOWER(COALESCE(c.status, 'Pending')) IN ('pending', 'assigned', 'in progress', 'in_progress')"
    elif status_filter == 'completed':
        request_status_clause = "AND COALESCE(r.status, 'pending') = 'completed'"
        task_status_clause = "AND COALESCE(t.status, 'pending') = 'completed'"
        complaint_status_clause = "AND LOWER(COALESCE(c.status, 'Pending')) = 'completed'"

    cursor.execute(f"""
        SELECT
            r.id,
            COALESCE(r.garbage_type, 'Garbage Collection') AS garbage_type,
            COALESCE(r.status, 'pending') AS status,
            COALESCE(r.amount, 0) AS amount,
            r.created_at,
            COALESCE(u.name, 'Citizen') AS citizen_name,
            COALESCE(v.name, worker_v.name, 'Assigned Area') AS area_name
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN villages v ON u.village_id = v.id
        LEFT JOIN villages worker_v ON worker_v.id = %s
        WHERE r.worker_id = %s
        {request_status_clause}
    """, (worker_village_id, worker_id))
    request_items = []
    for row in cursor.fetchall() or []:
        status = (row.get('status') or 'pending').lower()
        request_items.append({
            'id': row.get('id'),
            'ticket_id': f"REQ-{row.get('id')}",
            'source': 'request',
            'source_label': 'Citizen Request',
            'citizen_name': row.get('citizen_name') or 'Citizen',
            'area_name': row.get('area_name') or 'Assigned Area',
            'location_name': row.get('area_name') or 'Assigned Area',
            'description': row.get('garbage_type') or 'Garbage Collection',
            'garbage_type': row.get('garbage_type') or 'Garbage Collection',
            'priority': 'medium',
            'priority_label': 'Medium',
            'status': status,
            'status_class': status.replace('_', '-'),
            'status_label': status.replace('_', ' ').title(),
            'amount': row.get('amount') or 0,
            'created_at': row.get('created_at'),
            'map_query': _build_map_query(
                row.get('area_name'),
                worker_taluka_name,
                worker_district_name,
                'Maharashtra',
                'India',
            ),
            'can_start': status == 'pending',
            'can_complete': status in ('pending', 'in_progress'),
            'is_started': status == 'in_progress',
        })

    cursor.execute(f"""
        SELECT
            t.id,
            COALESCE(t.location_name, v.name, 'Assigned Area') AS location_name,
            COALESCE(t.description, 'Assigned task') AS description,
            COALESCE(t.status, 'pending') AS status,
            COALESCE(t.priority, 'medium') AS priority,
            t.assigned_at,
            COALESCE(v.name, 'Assigned Area') AS village_name
        FROM tasks t
        LEFT JOIN village_workers vw ON t.worker_id = vw.id
        LEFT JOIN villages v ON vw.village_id = v.id
        WHERE t.worker_id = %s
        {task_status_clause}
    """, (worker_id,))
    manual_task_items = []
    for row in cursor.fetchall() or []:
        status = (row.get('status') or 'pending').lower()
        priority = (row.get('priority') or 'medium').lower()
        if priority not in ('low', 'medium', 'high'):
            priority = 'medium'
        manual_task_items.append({
            'id': row.get('id'),
            'ticket_id': f"TASK-{row.get('id')}",
            'source': 'manual_task',
            'source_label': 'Admin Task',
            'citizen_name': 'Taluka Admin',
            'area_name': row.get('location_name') or row.get('village_name') or 'Assigned Area',
            'location_name': row.get('location_name') or row.get('village_name') or 'Assigned Area',
            'description': row.get('description') or 'Assigned task',
            'garbage_type': row.get('description') or 'Assigned task',
            'priority': priority,
            'priority_label': priority.title(),
            'status': status,
            'status_class': status.replace('_', '-'),
            'status_label': status.replace('_', ' ').title(),
            'amount': None,
            'created_at': row.get('assigned_at'),
            'map_query': _build_map_query(
                row.get('location_name') or row.get('village_name'),
                worker_taluka_name,
                worker_district_name,
                'Maharashtra',
                'India',
            ),
            'can_start': False,
            'can_complete': status == 'pending',
            'is_started': True,
        })

    ensure_complaint_workflow_columns(cursor)
    cursor.execute(f"""
        SELECT
            c.id,
            c.title,
            c.description,
            c.village,
            c.taluka,
            c.status,
            c.priority,
            c.created_at,
            c.assigned_at,
            c.updated_at,
            c.resolved_at,
            COALESCE(u.name, 'Citizen') AS citizen_name
        FROM complaints c
        LEFT JOIN users u ON c.user_id = u.id
        WHERE c.worker_id = %s
        {complaint_status_clause}
    """, (worker_id,))
    complaint_items = []
    for row in cursor.fetchall() or []:
        status_label = normalize_complaint_status(row.get('status'))
        status_key = complaint_status_key(row.get('status'))
        priority_label = (row.get('priority') or 'Normal').strip().title()
        priority_key = priority_label.lower()
        if priority_key in ('urgent', 'high'):
            task_priority = 'high'
        elif priority_key == 'low':
            task_priority = 'low'
        else:
            task_priority = 'medium'
        complaint_area = ', '.join([part for part in [row.get('village'), row.get('taluka')] if part]) or 'Complaint Area'
        complaint_items.append({
            'id': row.get('id'),
            'ticket_id': f"CMP-{row.get('id')}",
            'source': 'complaint',
            'source_label': 'Complaint',
            'citizen_name': row.get('citizen_name') or 'Citizen',
            'area_name': complaint_area,
            'location_name': row.get('village') or row.get('taluka') or 'Complaint Area',
            'description': row.get('description') or row.get('title') or 'Complaint',
            'garbage_type': row.get('title') or 'Complaint',
            'priority': task_priority,
            'priority_label': priority_label,
            'status': status_key,
            'status_class': complaint_status_class(status_label),
            'status_label': status_label,
            'amount': None,
            'created_at': row.get('resolved_at') or row.get('updated_at') or row.get('assigned_at') or row.get('created_at'),
            'map_query': _build_map_query(
                row.get('village'),
                row.get('taluka') or worker_taluka_name,
                worker_district_name,
                'Maharashtra',
                'India',
            ),
            'can_start': status_key in ('pending', 'assigned'),
            'can_complete': status_key in ('pending', 'assigned', 'in_progress'),
            'is_started': status_key == 'in_progress',
        })

    work_items = request_items + manual_task_items + complaint_items
    work_items.sort(key=lambda item: item.get('created_at') or datetime.min, reverse=True)

    if status_filter == 'all':
        status_order = {'pending': 0, 'assigned': 1, 'in_progress': 2, 'completed': 3}
        work_items.sort(key=lambda item: status_order.get(item.get('status'), 3))

    if limit is not None:
        work_items = work_items[:max(int(limit), 0)]

    return work_items


def _get_taluka_admin_profile(admin_id, cursor):
    cursor.execute("""
        SELECT
            ta.id,
            ta.name,
            ta.email,
            ta.phone,
            ta.taluka_id,
            ta.created_at,
            t.name AS taluka_name,
            d.id AS district_id,
            d.name AS district_name
        FROM taluka_admins ta
        LEFT JOIN talukas t ON ta.taluka_id = t.id
        LEFT JOIN districts d ON t.district_id = d.id
        WHERE ta.id = %s
    """, (admin_id,))
    return cursor.fetchone()


def _get_taluka_overview_data(admin_profile, cursor):
    taluka_id = admin_profile.get('taluka_id')
    taluka_name = admin_profile.get('taluka_name')

    cursor.execute("SELECT COUNT(*) AS total FROM villages WHERE taluka_id = %s", (taluka_id,))
    villages_count = (cursor.fetchone() or {}).get('total', 0)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM users
        WHERE COALESCE(taluka_id, 0) = %s
           OR village_id IN (SELECT id FROM villages WHERE taluka_id = %s)
    """, (taluka_id, taluka_id))
    citizens_count = (cursor.fetchone() or {}).get('total', 0)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM village_workers
        WHERE village_id IN (SELECT id FROM villages WHERE taluka_id = %s)
    """, (taluka_id,))
    workers_count = (cursor.fetchone() or {}).get('total', 0)

    ensure_complaint_workflow_columns(cursor)
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN LOWER(status) = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN LOWER(status) IN ('assigned', 'in progress', 'in_progress') THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN LOWER(status) = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM complaints
        WHERE taluka = %s
    """, (taluka_name,))
    complaints_stats = cursor.fetchone() or {}

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) AS completed_value
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN villages uv ON u.village_id = uv.id
        WHERE COALESCE(u.taluka_id, uv.taluka_id) = %s
    """, (taluka_id,))
    requests_stats = cursor.fetchone() or {}

    dashboard_stats = {
        'villages': villages_count or 0,
        'citizens': citizens_count or 0,
        'workers': workers_count or 0,
        'complaints_total': complaints_stats.get('total') or 0,
        'complaints_pending': complaints_stats.get('pending') or 0,
        'complaints_in_progress': complaints_stats.get('in_progress') or 0,
        'complaints_completed': complaints_stats.get('completed') or 0,
        'requests_total': requests_stats.get('total') or 0,
        'requests_pending': requests_stats.get('pending') or 0,
        'requests_in_progress': requests_stats.get('in_progress') or 0,
        'requests_completed': requests_stats.get('completed') or 0,
        'completed_value': requests_stats.get('completed_value') or 0,
    }

    recent_complaints = _get_taluka_complaints(admin_profile, cursor, limit=6)
    map_complaints = _get_taluka_complaints(admin_profile, cursor)

    cursor.execute("""
        SELECT
            v.id,
            v.name,
            COUNT(DISTINCT u.id) AS citizens,
            COUNT(DISTINCT vw.id) AS workers,
            COUNT(r.id) AS total_requests,
            SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) AS completed_requests
        FROM villages v
        LEFT JOIN users u ON u.village_id = v.id
        LEFT JOIN village_workers vw ON vw.village_id = v.id
        LEFT JOIN requests r ON r.user_id = u.id
        WHERE v.taluka_id = %s
        GROUP BY v.id, v.name
        ORDER BY total_requests DESC, v.name ASC
        LIMIT 8
    """, (taluka_id,))
    village_rows = cursor.fetchall() or []
    village_progress = []
    for row in village_rows:
        total_requests = row.get('total_requests') or 0
        completed_requests = row.get('completed_requests') or 0
        progress = round((completed_requests / total_requests) * 100) if total_requests else 0
        village_progress.append({
            'id': row.get('id'),
            'name': row.get('name'),
            'citizens': row.get('citizens') or 0,
            'workers': row.get('workers') or 0,
            'total_requests': total_requests,
            'completed_requests': completed_requests,
            'progress': progress,
        })

    taluka_workers = _get_taluka_worker_options(taluka_id, cursor)
    worker_summary = sorted(
        taluka_workers,
        key=lambda item: (
            -(item.get('completed_tasks') or 0),
            -(item.get('total_tasks') or 0),
            (item.get('name') or '').lower(),
        )
    )[:6]

    recent_requests = _get_taluka_request_items(taluka_id, cursor, limit=8)
    map_requests = _get_taluka_request_items(taluka_id, cursor)
    map_assigned_tasks = _get_taluka_recent_manual_tasks(taluka_id, cursor, limit=None)

    available_workers = [
        {
            'id': worker.get('id'),
            'name': worker.get('name'),
            'village_id': worker.get('village_id'),
            'village_name': worker.get('village_name'),
            'status': worker.get('status'),
        }
        for worker in taluka_workers
    ]

    chart_data = {
        'complaints': [
            dashboard_stats['complaints_pending'],
            dashboard_stats['complaints_in_progress'],
            dashboard_stats['complaints_completed'],
        ],
        'requests': [
            dashboard_stats['requests_pending'],
            dashboard_stats['requests_in_progress'],
            dashboard_stats['requests_completed'],
        ],
        'villages': [item['name'] for item in village_progress[:5]],
        'village_completion': [item['progress'] for item in village_progress[:5]],
    }

    return {
        'dashboard_stats': dashboard_stats,
        'recent_complaints': recent_complaints,
        'village_progress': village_progress,
        'worker_summary': worker_summary,
        'recent_requests': recent_requests,
        'available_workers': available_workers,
        'chart_data': chart_data,
        'taluka_map': _build_taluka_map_payload(admin_profile, map_complaints, map_requests, map_assigned_tasks),
    }


def _district_performance_band(completion_rate, open_work):
    if completion_rate >= 85 and open_work <= 5:
        return 'excellent', 'Excellent'
    if completion_rate >= 70 and open_work <= 14:
        return 'good', 'Stable'
    if completion_rate >= 50:
        return 'attention', 'Needs Attention'
    return 'critical', 'Critical'


def _district_hotspot_band(open_complaints, high_priority):
    pressure_score = (open_complaints or 0) * 2 + (high_priority or 0)
    if pressure_score >= 10:
        return 'high', 'High Pressure'
    if pressure_score >= 5:
        return 'medium', 'Watch Closely'
    return 'low', 'Stable'


def _get_district_admin_profile(admin_id, cursor):
    cursor.execute("""
        SELECT
            da.id,
            da.name,
            da.email,
            da.phone,
            da.district_id,
            da.created_at,
            d.name AS district_name
        FROM district_admins da
        LEFT JOIN districts d ON da.district_id = d.id
        WHERE da.id = %s
    """, (admin_id,))
    return cursor.fetchone()


def _get_district_complaints(admin_profile, cursor, limit=None):
    ensure_complaint_workflow_columns(cursor)

    query = """
        SELECT
            c.id,
            c.title,
            c.description,
            c.village,
            c.taluka,
            c.priority,
            c.status,
            c.created_at,
            c.assigned_at,
            c.updated_at,
            c.resolved_at,
            COALESCE(u.name, 'Citizen') AS citizen_name,
            COALESCE(vw.name, 'Unassigned') AS worker_name,
            COALESCE(ta.name, 'Taluka Office') AS admin_name,
            COALESCE(TIMESTAMPDIFF(HOUR, COALESCE(c.updated_at, c.assigned_at, c.created_at), NOW()), 0) AS hours_waiting
        FROM complaints c
        LEFT JOIN users u ON c.user_id = u.id
        LEFT JOIN village_workers vw ON c.worker_id = vw.id
        LEFT JOIN taluka_admins ta ON c.admin_id = ta.id
        WHERE c.district = %s
        ORDER BY COALESCE(c.updated_at, c.assigned_at, c.created_at) DESC
    """
    if limit is not None:
        query += f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(query, (admin_profile.get('district_name'),))
    complaints = cursor.fetchall() or []

    for complaint in complaints:
        status_text = normalize_complaint_status(complaint.get('status'))
        status_key = complaint_status_key(status_text)
        last_update = complaint.get('updated_at') or complaint.get('resolved_at') or complaint.get('assigned_at') or complaint.get('created_at')
        hours_waiting = complaint.get('hours_waiting') or 0
        complaint['status'] = status_text
        complaint['status_key'] = status_key
        complaint['status_class'] = status_key
        complaint['priority_key'] = _slug_text(complaint.get('priority') or 'normal')
        complaint['created_at_text'] = _format_timestamp(complaint.get('created_at'), include_time=True)
        complaint['updated_at_text'] = _format_timestamp(last_update, include_time=True)
        complaint['hours_waiting'] = hours_waiting
        complaint['age_label'] = f"{hours_waiting} hrs open"
        complaint['is_escalated'] = status_key != 'completed' and hours_waiting >= 48
        complaint['severity_class'] = 'critical' if hours_waiting >= 72 or complaint['priority_key'] == 'high' else 'attention'

    return complaints


def _get_district_request_items(district_id, cursor, limit=None):
    limit_clause = ""
    if limit is not None:
        limit_clause = f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(f"""
        SELECT
            r.id,
            COALESCE(r.garbage_type, 'Garbage Collection') AS garbage_type,
            COALESCE(r.status, 'pending') AS status,
            COALESCE(r.amount, 0) AS amount,
            COALESCE(r.weight, 0) AS weight,
            r.created_at,
            COALESCE(u.name, 'Citizen') AS citizen_name,
            COALESCE(uv.name, wv.name, 'Unknown Village') AS village_name,
            COALESCE(ut.name, uvt.name, wt.name, 'Unknown Taluka') AS taluka_name,
            COALESCE(vw.name, 'Unassigned') AS worker_name,
            r.worker_id
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN villages uv ON u.village_id = uv.id
        LEFT JOIN talukas ut ON u.taluka_id = ut.id
        LEFT JOIN talukas uvt ON uv.taluka_id = uvt.id
        LEFT JOIN village_workers vw ON r.worker_id = vw.id
        LEFT JOIN villages wv ON vw.village_id = wv.id
        LEFT JOIN talukas wt ON wv.taluka_id = wt.id
        WHERE COALESCE(u.district_id, ut.district_id, uvt.district_id, wt.district_id) = %s
        ORDER BY r.created_at DESC
        {limit_clause}
    """, (district_id,))

    request_items = cursor.fetchall() or []
    for request_item in request_items:
        request_item['status'] = (request_item.get('status') or 'pending').lower()
        request_item['status_label'] = request_item['status'].replace('_', ' ').title()
        request_item['created_at_text'] = _format_timestamp(request_item.get('created_at'), include_time=True)
    return request_items


def _get_district_recent_manual_tasks(district_id, cursor, limit=10):
    limit_clause = ""
    if limit is not None:
        limit_clause = f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(f"""
        SELECT
            t.id,
            t.worker_id,
            COALESCE(t.location_name, v.name, 'Assigned Area') AS location_name,
            COALESCE(t.description, 'Assigned task') AS description,
            COALESCE(t.priority, 'medium') AS priority,
            COALESCE(t.status, 'pending') AS status,
            t.assigned_at,
            COALESCE(vw.name, 'Unknown Worker') AS worker_name,
            COALESCE(v.name, 'Unknown Village') AS village_name,
            COALESCE(tl.name, 'Unknown Taluka') AS taluka_name
        FROM tasks t
        LEFT JOIN village_workers vw ON t.worker_id = vw.id
        LEFT JOIN villages v ON vw.village_id = v.id
        LEFT JOIN talukas tl ON v.taluka_id = tl.id
        WHERE tl.district_id = %s
        ORDER BY t.assigned_at DESC
        {limit_clause}
    """, (district_id,))

    tasks = cursor.fetchall() or []
    for task in tasks:
        task['status'] = (task.get('status') or 'pending').lower()
        task['status_label'] = task['status'].replace('_', ' ').title()
        task['priority_key'] = _slug_text(task.get('priority') or 'medium')
        task['assigned_at_text'] = _format_timestamp(task.get('assigned_at'), include_time=True)
    return tasks


def _get_district_worker_summary(district_id, cursor, limit=None):
    cursor.execute("""
        SELECT
            vw.id,
            vw.name,
            vw.email,
            vw.phone,
            vw.vehicle_no,
            vw.status,
            vw.created_at,
            COALESCE(v.name, 'Not assigned') AS village_name,
            COALESCE(t.name, 'Unknown Taluka') AS taluka_name
        FROM village_workers vw
        LEFT JOIN villages v ON vw.village_id = v.id
        LEFT JOIN talukas t ON v.taluka_id = t.id
        WHERE t.district_id = %s
        ORDER BY vw.name ASC
    """, (district_id,))
    workers = cursor.fetchall() or []
    if not workers:
        return []

    counts_by_worker = {worker['id']: _empty_worker_counts() for worker in workers}

    cursor.execute("""
        SELECT
            r.worker_id,
            COUNT(*) AS total_tasks,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) IN ('pending', 'in_progress') THEN 1 ELSE 0 END) AS active_tasks,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_tasks
        FROM requests r
        INNER JOIN village_workers vw ON vw.id = r.worker_id
        INNER JOIN villages v ON vw.village_id = v.id
        INNER JOIN talukas t ON v.taluka_id = t.id
        WHERE t.district_id = %s
        GROUP BY r.worker_id
    """, (district_id,))
    for row in cursor.fetchall() or []:
        counts = counts_by_worker.setdefault(row.get('worker_id'), _empty_worker_counts())
        _merge_worker_counts(counts, row)

    cursor.execute("""
        SELECT
            t.worker_id,
            COUNT(*) AS total_tasks,
            SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
            SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS active_tasks,
            SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
            0 AS in_progress_tasks
        FROM tasks t
        INNER JOIN village_workers vw ON vw.id = t.worker_id
        INNER JOIN villages v ON vw.village_id = v.id
        INNER JOIN talukas tl ON v.taluka_id = tl.id
        WHERE tl.district_id = %s
        GROUP BY t.worker_id
    """, (district_id,))
    for row in cursor.fetchall() or []:
        counts = counts_by_worker.setdefault(row.get('worker_id'), _empty_worker_counts())
        _merge_worker_counts(counts, row)

    ensure_complaint_workflow_columns(cursor)
    cursor.execute("""
        SELECT
            c.worker_id,
            COUNT(*) AS total_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) IN ('pending', 'assigned', 'in progress', 'in_progress') THEN 1 ELSE 0 END) AS active_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) IN ('pending', 'assigned') THEN 1 ELSE 0 END) AS pending_tasks,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) IN ('in progress', 'in_progress') THEN 1 ELSE 0 END) AS in_progress_tasks
        FROM complaints c
        INNER JOIN village_workers vw ON vw.id = c.worker_id
        INNER JOIN villages v ON vw.village_id = v.id
        INNER JOIN talukas t ON v.taluka_id = t.id
        WHERE t.district_id = %s
        GROUP BY c.worker_id
    """, (district_id,))
    for row in cursor.fetchall() or []:
        counts = counts_by_worker.setdefault(row.get('worker_id'), _empty_worker_counts())
        _merge_worker_counts(counts, row)

    for worker in workers:
        worker.update(counts_by_worker.get(worker['id'], _empty_worker_counts()))
        total_tasks = worker.get('total_tasks') or 0
        completed_tasks = worker.get('completed_tasks') or 0
        worker['completion_rate'] = round((completed_tasks / total_tasks) * 100) if total_tasks else 0
        worker['status_key'] = _slug_text(worker.get('status') or 'active').replace(' ', '_')

    workers.sort(
        key=lambda item: (
            -(item.get('completed_tasks') or 0),
            -(item.get('completion_rate') or 0),
            (item.get('name') or '').lower(),
        )
    )

    if limit is not None:
        return workers[:max(int(limit), 0)]
    return workers


def _get_district_taluka_performance(district_id, district_name, cursor):
    cursor.execute("""
        SELECT
            t.id,
            t.name,
            ta.id AS admin_id,
            COALESCE(ta.name, 'Not Assigned') AS admin_name
        FROM talukas t
        LEFT JOIN taluka_admins ta ON ta.taluka_id = t.id
        WHERE t.district_id = %s
        ORDER BY t.name ASC
    """, (district_id,))
    taluka_rows = cursor.fetchall() or []
    if not taluka_rows:
        return []

    taluka_map = {}
    name_to_id = {}
    for row in taluka_rows:
        taluka_map[row['id']] = {
            'id': row.get('id'),
            'name': row.get('name'),
            'admin_id': row.get('admin_id'),
            'admin_name': row.get('admin_name'),
            'villages': 0,
            'workers': 0,
            'citizens': 0,
            'total_requests': 0,
            'pending_requests': 0,
            'in_progress_requests': 0,
            'completed_requests': 0,
            'completed_value': 0,
            'total_complaints': 0,
            'complaints_pending': 0,
            'complaints_in_progress': 0,
            'complaints_completed': 0,
        }
        name_to_id[_slug_text(row.get('name'))] = row.get('id')

    cursor.execute("""
        SELECT taluka_id, COUNT(*) AS total
        FROM villages
        WHERE taluka_id IN (SELECT id FROM talukas WHERE district_id = %s)
        GROUP BY taluka_id
    """, (district_id,))
    for row in cursor.fetchall() or []:
        taluka = taluka_map.get(row.get('taluka_id'))
        if taluka:
            taluka['villages'] = row.get('total') or 0

    cursor.execute("""
        SELECT v.taluka_id, COUNT(*) AS total
        FROM village_workers vw
        INNER JOIN villages v ON vw.village_id = v.id
        WHERE v.taluka_id IN (SELECT id FROM talukas WHERE district_id = %s)
        GROUP BY v.taluka_id
    """, (district_id,))
    for row in cursor.fetchall() or []:
        taluka = taluka_map.get(row.get('taluka_id'))
        if taluka:
            taluka['workers'] = row.get('total') or 0

    cursor.execute("""
        SELECT
            COALESCE(u.taluka_id, v.taluka_id) AS taluka_id,
            COUNT(*) AS total
        FROM users u
        LEFT JOIN villages v ON u.village_id = v.id
        LEFT JOIN talukas ut ON u.taluka_id = ut.id
        LEFT JOIN talukas vt ON v.taluka_id = vt.id
        WHERE COALESCE(u.district_id, ut.district_id, vt.district_id) = %s
        GROUP BY COALESCE(u.taluka_id, v.taluka_id)
    """, (district_id,))
    for row in cursor.fetchall() or []:
        taluka = taluka_map.get(row.get('taluka_id'))
        if taluka:
            taluka['citizens'] = row.get('total') or 0

    cursor.execute("""
        SELECT
            COALESCE(u.taluka_id, uv.taluka_id, wv.taluka_id) AS taluka_id,
            COUNT(*) AS total_requests,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'pending' THEN 1 ELSE 0 END) AS pending_requests,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_requests,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'completed' THEN 1 ELSE 0 END) AS completed_requests,
            COALESCE(SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'completed' THEN r.amount ELSE 0 END), 0) AS completed_value
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN villages uv ON u.village_id = uv.id
        LEFT JOIN talukas ut ON u.taluka_id = ut.id
        LEFT JOIN talukas uvt ON uv.taluka_id = uvt.id
        LEFT JOIN village_workers vw ON r.worker_id = vw.id
        LEFT JOIN villages wv ON vw.village_id = wv.id
        LEFT JOIN talukas wt ON wv.taluka_id = wt.id
        WHERE COALESCE(u.district_id, ut.district_id, uvt.district_id, wt.district_id) = %s
        GROUP BY COALESCE(u.taluka_id, uv.taluka_id, wv.taluka_id)
    """, (district_id,))
    for row in cursor.fetchall() or []:
        taluka = taluka_map.get(row.get('taluka_id'))
        if taluka:
            taluka['total_requests'] = row.get('total_requests') or 0
            taluka['pending_requests'] = row.get('pending_requests') or 0
            taluka['in_progress_requests'] = row.get('in_progress_requests') or 0
            taluka['completed_requests'] = row.get('completed_requests') or 0
            taluka['completed_value'] = row.get('completed_value') or 0

    ensure_complaint_workflow_columns(cursor)
    cursor.execute("""
        SELECT
            COALESCE(c.taluka, 'Unknown Taluka') AS taluka_name,
            COUNT(*) AS total_complaints,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) = 'pending' THEN 1 ELSE 0 END) AS complaints_pending,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) IN ('assigned', 'in progress', 'in_progress') THEN 1 ELSE 0 END) AS complaints_in_progress,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) = 'completed' THEN 1 ELSE 0 END) AS complaints_completed
        FROM complaints c
        WHERE c.district = %s
        GROUP BY COALESCE(c.taluka, 'Unknown Taluka')
    """, (district_name,))
    for row in cursor.fetchall() or []:
        taluka_id = name_to_id.get(_slug_text(row.get('taluka_name')))
        taluka = taluka_map.get(taluka_id)
        if taluka:
            taluka['total_complaints'] = row.get('total_complaints') or 0
            taluka['complaints_pending'] = row.get('complaints_pending') or 0
            taluka['complaints_in_progress'] = row.get('complaints_in_progress') or 0
            taluka['complaints_completed'] = row.get('complaints_completed') or 0

    performance_rows = []
    for taluka in taluka_map.values():
        total_services = (taluka.get('total_requests') or 0) + (taluka.get('total_complaints') or 0)
        completed_services = (taluka.get('completed_requests') or 0) + (taluka.get('complaints_completed') or 0)
        open_work = (
            (taluka.get('pending_requests') or 0)
            + (taluka.get('in_progress_requests') or 0)
            + (taluka.get('complaints_pending') or 0)
            + (taluka.get('complaints_in_progress') or 0)
        )
        completion_rate = round((completed_services / total_services) * 100) if total_services else 0
        band_class, band_label = _district_performance_band(completion_rate, open_work)
        taluka['total_services'] = total_services
        taluka['completed_services'] = completed_services
        taluka['open_work'] = open_work
        taluka['completion_rate'] = completion_rate
        taluka['band_class'] = band_class
        taluka['band_label'] = band_label
        taluka['admin_assigned'] = bool(taluka.get('admin_id'))
        performance_rows.append(taluka)

    performance_rows.sort(
        key=lambda item: (
            -(item.get('completion_rate') or 0),
            item.get('open_work') or 0,
            (item.get('name') or '').lower(),
        )
    )
    return performance_rows


def _get_district_hotspots(district_name, cursor, limit=6):
    cursor.execute(f"""
        SELECT
            COALESCE(c.village, 'Unknown Village') AS village_name,
            COALESCE(c.taluka, 'Unknown Taluka') AS taluka_name,
            COUNT(*) AS total_complaints,
            SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) != 'completed' THEN 1 ELSE 0 END) AS open_complaints,
            SUM(CASE WHEN LOWER(COALESCE(c.priority, 'Normal')) = 'high' THEN 1 ELSE 0 END) AS high_priority_count
        FROM complaints c
        WHERE c.district = %s
        GROUP BY COALESCE(c.taluka, 'Unknown Taluka'), COALESCE(c.village, 'Unknown Village')
        ORDER BY open_complaints DESC, high_priority_count DESC, total_complaints DESC
        LIMIT {max(int(limit), 0)}
    """, (district_name,))

    hotspots = cursor.fetchall() or []
    for hotspot in hotspots:
        level_class, level_label = _district_hotspot_band(hotspot.get('open_complaints'), hotspot.get('high_priority_count'))
        hotspot['level_class'] = level_class
        hotspot['level_label'] = level_label
        hotspot['location_label'] = f"{hotspot.get('village_name')} • {hotspot.get('taluka_name')}"
    return hotspots


def _get_village_names_by_taluka(district_id, cursor):
    cursor.execute("""
        SELECT
            v.taluka_id,
            v.name
        FROM villages v
        INNER JOIN talukas t ON v.taluka_id = t.id
        WHERE t.district_id = %s
        ORDER BY t.name ASC, v.name ASC
    """, (district_id,))

    village_names_by_taluka = {}
    for row in cursor.fetchall() or []:
        taluka_id = row.get('taluka_id')
        if taluka_id is None:
            continue
        village_names_by_taluka.setdefault(taluka_id, []).append(row.get('name'))

    return village_names_by_taluka


def ensure_district_admin_task_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS district_admin_tasks (
                id INT NOT NULL AUTO_INCREMENT,
                district_admin_id INT NOT NULL,
                taluka_admin_id INT NOT NULL,
                location_name VARCHAR(255) DEFAULT NULL,
                description TEXT NOT NULL,
                priority ENUM('low', 'medium', 'high') DEFAULT 'medium',
                status ENUM('pending', 'completed') DEFAULT 'pending',
                assigned_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL DEFAULT NULL,
                PRIMARY KEY (id),
                KEY idx_district_admin_tasks_district_admin_id (district_admin_id),
                KEY idx_district_admin_tasks_taluka_admin_id (taluka_admin_id),
                CONSTRAINT district_admin_tasks_district_admin_fk
                    FOREIGN KEY (district_admin_id) REFERENCES district_admins (id) ON DELETE CASCADE,
                CONSTRAINT district_admin_tasks_taluka_admin_fk
                    FOREIGN KEY (taluka_admin_id) REFERENCES taluka_admins (id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """)
    except mysql.connector.Error as err:
        if getattr(err, 'errno', None) != 1050:
            raise


def _get_district_taluka_rows(district_id, cursor):
    village_names_by_taluka = _get_village_names_by_taluka(district_id, cursor)

    cursor.execute("""
        SELECT
            t.id,
            t.name,
            ta.id AS admin_id,
            COALESCE(ta.name, 'Not Assigned') AS admin_name,
            COALESCE(ta.email, '') AS admin_email,
            COALESCE(ta.phone, '') AS admin_phone,
            COALESCE(
                (SELECT COUNT(*) FROM villages v WHERE v.taluka_id = t.id),
                0
            ) AS villages,
            COALESCE(
                (SELECT COUNT(*)
                 FROM users u
                 LEFT JOIN villages uv ON u.village_id = uv.id
                 WHERE COALESCE(u.taluka_id, uv.taluka_id) = t.id),
                0
            ) AS citizens,
            COALESCE(
                (SELECT COUNT(*)
                 FROM village_workers vw
                 LEFT JOIN villages vv ON vw.village_id = vv.id
                 WHERE vv.taluka_id = t.id),
                0
            ) AS workers,
            COALESCE(
                (SELECT COUNT(*)
                 FROM requests r
                 LEFT JOIN users u ON r.user_id = u.id
                 LEFT JOIN villages uv ON u.village_id = uv.id
                 WHERE COALESCE(u.taluka_id, uv.taluka_id) = t.id),
                0
            ) AS total_requests,
            COALESCE(
                (SELECT SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'completed' THEN 1 ELSE 0 END)
                 FROM requests r
                 LEFT JOIN users u ON r.user_id = u.id
                 LEFT JOIN villages uv ON u.village_id = uv.id
                 WHERE COALESCE(u.taluka_id, uv.taluka_id) = t.id),
                0
            ) AS completed_requests,
            COALESCE(
                (SELECT COUNT(*)
                 FROM complaints c
                 LEFT JOIN districts d ON d.id = t.district_id
                 WHERE c.taluka = t.name AND c.district = d.name),
                0
            ) AS total_complaints,
            COALESCE(
                (SELECT SUM(CASE WHEN LOWER(COALESCE(c.status, 'Pending')) != 'completed' THEN 1 ELSE 0 END)
                 FROM complaints c
                 LEFT JOIN districts d ON d.id = t.district_id
                 WHERE c.taluka = t.name AND c.district = d.name),
                0
            ) AS open_complaints
        FROM talukas t
        LEFT JOIN taluka_admins ta ON ta.taluka_id = t.id
        WHERE t.district_id = %s
        ORDER BY t.name ASC
    """, (district_id,))
    talukas = cursor.fetchall() or []

    for taluka in talukas:
        total_requests = taluka.get('total_requests') or 0
        completed_requests = taluka.get('completed_requests') or 0
        village_names = village_names_by_taluka.get(taluka.get('id'), [])
        taluka['progress'] = round((completed_requests / total_requests) * 100) if total_requests else 0
        taluka['villages_list'] = village_names[:8]
        taluka['villages_more_count'] = max(len(village_names) - 8, 0)
        taluka['admin_assigned'] = bool(taluka.get('admin_id'))

    return talukas


def _get_district_taluka_record(district_id, taluka_id, cursor):
    cursor.execute("""
        SELECT
            t.id,
            t.name,
            t.district_id,
            d.name AS district_name,
            ta.id AS admin_id,
            COALESCE(ta.name, 'Not Assigned') AS admin_name,
            COALESCE(ta.email, '') AS admin_email,
            COALESCE(ta.phone, '') AS admin_phone
        FROM talukas t
        LEFT JOIN districts d ON t.district_id = d.id
        LEFT JOIN taluka_admins ta ON ta.taluka_id = t.id
        WHERE t.id = %s AND t.district_id = %s
    """, (taluka_id, district_id))
    return cursor.fetchone()


def _get_district_unassigned_talukas(district_id, cursor):
    cursor.execute("""
        SELECT
            t.id,
            t.name
        FROM talukas t
        LEFT JOIN taluka_admins ta ON ta.taluka_id = t.id
        WHERE t.district_id = %s AND ta.id IS NULL
        ORDER BY t.name ASC
    """, (district_id,))
    return cursor.fetchall() or []


def _get_district_taluka_admin_record(district_id, taluka_admin_id, cursor):
    cursor.execute("""
        SELECT
            ta.id,
            ta.name,
            ta.email,
            ta.phone,
            ta.created_at,
            ta.taluka_id,
            t.name AS taluka_name,
            d.id AS district_id,
            d.name AS district_name
        FROM taluka_admins ta
        INNER JOIN talukas t ON ta.taluka_id = t.id
        LEFT JOIN districts d ON t.district_id = d.id
        WHERE ta.id = %s AND t.district_id = %s
    """, (taluka_admin_id, district_id))
    return cursor.fetchone()


def _get_district_taluka_admin_options(district_id, cursor):
    ensure_district_admin_task_table(cursor)
    village_names_by_taluka = _get_village_names_by_taluka(district_id, cursor)

    cursor.execute("""
        SELECT
            ta.id,
            ta.name,
            ta.email,
            ta.phone,
            ta.created_at,
            ta.taluka_id,
            t.name AS taluka_name,
            COALESCE(
                (SELECT COUNT(*) FROM villages v WHERE v.taluka_id = t.id),
                0
            ) AS villages,
            COALESCE(
                (SELECT COUNT(*)
                 FROM village_workers vw
                 LEFT JOIN villages v ON vw.village_id = v.id
                 WHERE v.taluka_id = t.id),
                0
            ) AS workers,
            COALESCE(
                (SELECT COUNT(*) FROM district_admin_tasks dat WHERE dat.taluka_admin_id = ta.id),
                0
            ) AS total_district_tasks,
            COALESCE(
                (SELECT COUNT(*) FROM district_admin_tasks dat WHERE dat.taluka_admin_id = ta.id AND dat.status = 'pending'),
                0
            ) AS pending_district_tasks,
            COALESCE(
                (SELECT COUNT(*) FROM district_admin_tasks dat WHERE dat.taluka_admin_id = ta.id AND dat.status = 'completed'),
                0
            ) AS completed_district_tasks
        FROM taluka_admins ta
        INNER JOIN talukas t ON ta.taluka_id = t.id
        WHERE t.district_id = %s
        ORDER BY t.name ASC, ta.name ASC
    """, (district_id,))
    taluka_admins = cursor.fetchall() or []

    for taluka_admin in taluka_admins:
        village_names = village_names_by_taluka.get(taluka_admin.get('taluka_id'), [])
        taluka_admin['villages_list'] = village_names[:8]
        taluka_admin['villages_more_count'] = max(len(village_names) - 8, 0)

    return taluka_admins


def _get_district_admin_task_items(district_admin_id, cursor, limit=None):
    ensure_district_admin_task_table(cursor)
    limit_clause = ""
    if limit is not None:
        limit_clause = f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(f"""
        SELECT
            dat.id,
            dat.district_admin_id,
            dat.taluka_admin_id,
            COALESCE(dat.location_name, '') AS location_name,
            dat.description,
            COALESCE(dat.priority, 'medium') AS priority,
            COALESCE(dat.status, 'pending') AS status,
            dat.assigned_at,
            dat.completed_at,
            COALESCE(ta.name, 'Taluka Admin') AS taluka_admin_name,
            COALESCE(t.name, 'Taluka') AS taluka_name
        FROM district_admin_tasks dat
        LEFT JOIN taluka_admins ta ON dat.taluka_admin_id = ta.id
        LEFT JOIN talukas t ON ta.taluka_id = t.id
        WHERE dat.district_admin_id = %s
        ORDER BY dat.assigned_at DESC
        {limit_clause}
    """, (district_admin_id,))
    tasks = cursor.fetchall() or []

    for task in tasks:
        task['status'] = (task.get('status') or 'pending').lower()
        task['status_label'] = task['status'].replace('_', ' ').title()
        task['priority_key'] = _slug_text(task.get('priority') or 'medium')
        task['assigned_at_text'] = _format_timestamp(task.get('assigned_at'), include_time=True)
        task['completed_at_text'] = _format_timestamp(task.get('completed_at'), include_time=True)

    return tasks


def _get_taluka_admin_district_tasks(taluka_admin_id, cursor, limit=None):
    ensure_district_admin_task_table(cursor)
    limit_clause = ""
    if limit is not None:
        limit_clause = f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(f"""
        SELECT
            dat.id,
            dat.taluka_admin_id,
            COALESCE(dat.location_name, '') AS location_name,
            dat.description,
            COALESCE(dat.priority, 'medium') AS priority,
            COALESCE(dat.status, 'pending') AS status,
            dat.assigned_at,
            dat.completed_at,
            COALESCE(da.name, 'District Office') AS district_admin_name
        FROM district_admin_tasks dat
        LEFT JOIN district_admins da ON dat.district_admin_id = da.id
        WHERE dat.taluka_admin_id = %s
        ORDER BY dat.assigned_at DESC
        {limit_clause}
    """, (taluka_admin_id,))
    tasks = cursor.fetchall() or []

    for task in tasks:
        task['status'] = (task.get('status') or 'pending').lower()
        task['status_label'] = task['status'].replace('_', ' ').title()
        task['priority_key'] = _slug_text(task.get('priority') or 'medium')
        task['assigned_at_text'] = _format_timestamp(task.get('assigned_at'), include_time=True)
        task['completed_at_text'] = _format_timestamp(task.get('completed_at'), include_time=True)

    return tasks


def _build_district_map_payload(admin_profile, complaints, requests, assigned_tasks):
    district_name = admin_profile.get('district_name')
    markers = []

    for complaint in complaints or []:
        status_key = complaint.get('status_key') or complaint_status_key(complaint.get('status'))
        created_at = complaint.get('created_at')
        updated_at = complaint.get('updated_at') or complaint.get('resolved_at') or complaint.get('assigned_at') or created_at
        markers.append({
            'id': f"CMP-{complaint.get('id')}",
            'category': 'complaint',
            'category_label': 'Complaint',
            'title': complaint.get('title') or 'Complaint',
            'description': complaint.get('description') or 'Citizen complaint',
            'status': status_key,
            'status_label': complaint.get('status') or 'Pending',
            'location_label': f"{complaint.get('village') or 'Unknown Village'} • {complaint.get('taluka') or district_name or 'District'}",
            'map_query': _build_map_query(
                complaint.get('village'),
                complaint.get('taluka'),
                district_name,
                'Maharashtra',
                'India',
            ),
            'secondary_label': complaint.get('citizen_name') or 'Citizen',
            'assigned_to': complaint.get('worker_name') or 'Unassigned',
            'time_label': _format_timestamp(updated_at, include_time=True),
            'sort_at': updated_at.isoformat() if updated_at else '',
            'is_today': _is_today(created_at),
            'is_open': status_key != 'completed',
        })

    for pickup_request in requests or []:
        status_key = (pickup_request.get('status') or 'pending').lower()
        created_at = pickup_request.get('created_at')
        markers.append({
            'id': f"REQ-{pickup_request.get('id')}",
            'category': 'request',
            'category_label': 'Pickup Request',
            'title': pickup_request.get('garbage_type') or 'Garbage Collection',
            'description': f"Pickup request from {pickup_request.get('citizen_name') or 'Citizen'}",
            'status': status_key,
            'status_label': pickup_request.get('status_label') or status_key.replace('_', ' ').title(),
            'location_label': f"{pickup_request.get('village_name') or 'Unknown Village'} • {pickup_request.get('taluka_name') or district_name or 'District'}",
            'map_query': _build_map_query(
                pickup_request.get('village_name'),
                pickup_request.get('taluka_name'),
                district_name,
                'Maharashtra',
                'India',
            ),
            'secondary_label': pickup_request.get('citizen_name') or 'Citizen',
            'assigned_to': pickup_request.get('worker_name') or 'Unassigned',
            'time_label': _format_timestamp(created_at, include_time=True),
            'sort_at': created_at.isoformat() if created_at else '',
            'is_today': _is_today(created_at),
            'is_open': status_key != 'completed',
        })

    for assigned_task in assigned_tasks or []:
        status_key = (assigned_task.get('status') or 'pending').lower()
        assigned_at = assigned_task.get('assigned_at')
        markers.append({
            'id': f"TASK-{assigned_task.get('id')}",
            'category': 'assigned_task',
            'category_label': 'Assigned Task',
            'title': assigned_task.get('description') or assigned_task.get('location_name') or 'Assigned task',
            'description': assigned_task.get('description') or 'Manual task assigned by district office',
            'status': status_key,
            'status_label': assigned_task.get('status_label') or status_key.replace('_', ' ').title(),
            'location_label': f"{assigned_task.get('location_name') or assigned_task.get('village_name') or 'Assigned Area'} • {assigned_task.get('taluka_name') or district_name or 'District'}",
            'map_query': _build_map_query(
                assigned_task.get('location_name') or assigned_task.get('village_name'),
                assigned_task.get('taluka_name'),
                district_name,
                'Maharashtra',
                'India',
            ),
            'secondary_label': assigned_task.get('worker_name') or 'Worker',
            'assigned_to': assigned_task.get('worker_name') or 'Worker',
            'time_label': _format_timestamp(assigned_at, include_time=True),
            'sort_at': assigned_at.isoformat() if assigned_at else '',
            'is_today': _is_today(assigned_at),
            'is_open': status_key != 'completed',
        })

    markers.sort(key=lambda item: item.get('sort_at') or '', reverse=True)

    today_counts = {
        'complaints': sum(1 for item in markers if item.get('category') == 'complaint' and item.get('is_today')),
        'requests': sum(1 for item in markers if item.get('category') == 'request' and item.get('is_today')),
        'assigned_tasks': sum(1 for item in markers if item.get('category') == 'assigned_task' and item.get('is_today')),
    }
    today_counts['total'] = sum(today_counts.values())

    return {
        'scope_label': f"{district_name or 'District'} Scope",
        'center': None,
        'center_query': _build_map_query(district_name, 'Maharashtra', 'India'),
        'markers': markers,
        'today_counts': today_counts,
        'open_total': sum(1 for item in markers if item.get('is_open')),
    }


def _empty_district_overview_data(admin_profile):
    return {
        'dashboard_stats': {
            'talukas': 0,
            'villages': 0,
            'taluka_admins': 0,
            'citizens': 0,
            'workers': 0,
            'active_workers': 0,
            'complaints_total': 0,
            'complaints_pending': 0,
            'complaints_in_progress': 0,
            'complaints_completed': 0,
            'requests_total': 0,
            'requests_pending': 0,
            'requests_in_progress': 0,
            'requests_completed': 0,
            'tasks_total': 0,
            'tasks_pending': 0,
            'tasks_completed': 0,
            'completed_value': 0,
            'open_work': 0,
            'escalated_open': 0,
            'service_completion_rate': 0,
            'admin_coverage_rate': 0,
        },
        'district_insights': [],
        'taluka_performance': [],
        'hotspots': [],
        'recent_complaints': [],
        'recent_requests': [],
        'worker_summary': [],
        'escalations': [],
        'revenue_rows': [],
        'recent_assigned_tasks': [],
        'district_talukas': [],
        'district_taluka_admins': [],
        'chart_data': {
            'service_mix': {
                'labels': ['Pending', 'In Progress', 'Completed'],
                'complaints': [0, 0, 0],
                'requests': [0, 0, 0],
                'tasks': [0, 0, 0],
            },
            'taluka_performance': {
                'labels': [],
                'completion': [],
                'open_work': [],
            },
        },
        'district_map': _build_district_map_payload(admin_profile or {}, [], [], []),
    }


def _get_district_overview_data(admin_profile, cursor):
    district_id = admin_profile.get('district_id')
    district_name = admin_profile.get('district_name')

    cursor.execute("SELECT COUNT(*) AS total FROM talukas WHERE district_id = %s", (district_id,))
    talukas_count = (cursor.fetchone() or {}).get('total', 0)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM villages
        WHERE taluka_id IN (SELECT id FROM talukas WHERE district_id = %s)
    """, (district_id,))
    villages_count = (cursor.fetchone() or {}).get('total', 0)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM taluka_admins
        WHERE taluka_id IN (SELECT id FROM talukas WHERE district_id = %s)
    """, (district_id,))
    taluka_admin_count = (cursor.fetchone() or {}).get('total', 0)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM users u
        LEFT JOIN villages v ON u.village_id = v.id
        LEFT JOIN talukas ut ON u.taluka_id = ut.id
        LEFT JOIN talukas vt ON v.taluka_id = vt.id
        WHERE COALESCE(u.district_id, ut.district_id, vt.district_id) = %s
    """, (district_id,))
    citizens_count = (cursor.fetchone() or {}).get('total', 0)

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN LOWER(COALESCE(vw.status, 'Active')) = 'active' THEN 1 ELSE 0 END) AS active_total
        FROM village_workers vw
        LEFT JOIN villages v ON vw.village_id = v.id
        LEFT JOIN talukas t ON v.taluka_id = t.id
        WHERE t.district_id = %s
    """, (district_id,))
    worker_counts = cursor.fetchone() or {}
    workers_count = worker_counts.get('total') or 0
    active_workers = worker_counts.get('active_total') or 0

    ensure_complaint_workflow_columns(cursor)
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN LOWER(COALESCE(status, 'Pending')) = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN LOWER(COALESCE(status, 'Pending')) IN ('assigned', 'in progress', 'in_progress') THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN LOWER(COALESCE(status, 'Pending')) = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM complaints
        WHERE district = %s
    """, (district_name,))
    complaints_stats = cursor.fetchone() or {}

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'completed' THEN 1 ELSE 0 END) AS completed,
            COALESCE(SUM(CASE WHEN LOWER(COALESCE(r.status, 'pending')) = 'completed' THEN r.amount ELSE 0 END), 0) AS completed_value
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN villages uv ON u.village_id = uv.id
        LEFT JOIN talukas ut ON u.taluka_id = ut.id
        LEFT JOIN talukas uvt ON uv.taluka_id = uvt.id
        LEFT JOIN village_workers vw ON r.worker_id = vw.id
        LEFT JOIN villages wv ON vw.village_id = wv.id
        LEFT JOIN talukas wt ON wv.taluka_id = wt.id
        WHERE COALESCE(u.district_id, ut.district_id, uvt.district_id, wt.district_id) = %s
    """, (district_id,))
    requests_stats = cursor.fetchone() or {}

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM tasks t
        INNER JOIN village_workers vw ON vw.id = t.worker_id
        INNER JOIN villages v ON vw.village_id = v.id
        INNER JOIN talukas tl ON v.taluka_id = tl.id
        WHERE tl.district_id = %s
    """, (district_id,))
    task_stats = cursor.fetchone() or {}

    all_complaints = _get_district_complaints(admin_profile, cursor)
    all_requests = _get_district_request_items(district_id, cursor)
    recent_assigned_tasks = _get_district_recent_manual_tasks(district_id, cursor, limit=8)
    map_assigned_tasks = _get_district_recent_manual_tasks(district_id, cursor, limit=None)
    worker_summary = _get_district_worker_summary(district_id, cursor, limit=8)
    taluka_performance = _get_district_taluka_performance(district_id, district_name, cursor)
    district_talukas = _get_district_taluka_rows(district_id, cursor)
    district_taluka_admins = _get_district_taluka_admin_options(district_id, cursor)
    hotspots = _get_district_hotspots(district_name, cursor, limit=6)

    escalations = sorted(
        [complaint for complaint in all_complaints if complaint.get('is_escalated')],
        key=lambda item: (
            -(item.get('hours_waiting') or 0),
            str(item.get('created_at') or ''),
        )
    )[:6]

    total_service_items = (
        (complaints_stats.get('total') or 0)
        + (requests_stats.get('total') or 0)
        + (task_stats.get('total') or 0)
    )
    total_completed_items = (
        (complaints_stats.get('completed') or 0)
        + (requests_stats.get('completed') or 0)
        + (task_stats.get('completed') or 0)
    )

    dashboard_stats = {
        'talukas': talukas_count or 0,
        'villages': villages_count or 0,
        'taluka_admins': taluka_admin_count or 0,
        'citizens': citizens_count or 0,
        'workers': workers_count or 0,
        'active_workers': active_workers or 0,
        'complaints_total': complaints_stats.get('total') or 0,
        'complaints_pending': complaints_stats.get('pending') or 0,
        'complaints_in_progress': complaints_stats.get('in_progress') or 0,
        'complaints_completed': complaints_stats.get('completed') or 0,
        'requests_total': requests_stats.get('total') or 0,
        'requests_pending': requests_stats.get('pending') or 0,
        'requests_in_progress': requests_stats.get('in_progress') or 0,
        'requests_completed': requests_stats.get('completed') or 0,
        'tasks_total': task_stats.get('total') or 0,
        'tasks_pending': task_stats.get('pending') or 0,
        'tasks_completed': task_stats.get('completed') or 0,
        'completed_value': requests_stats.get('completed_value') or 0,
        'open_work': (
            (complaints_stats.get('pending') or 0)
            + (complaints_stats.get('in_progress') or 0)
            + (requests_stats.get('pending') or 0)
            + (requests_stats.get('in_progress') or 0)
            + (task_stats.get('pending') or 0)
        ),
        'escalated_open': len(escalations),
        'service_completion_rate': round((total_completed_items / total_service_items) * 100) if total_service_items else 0,
        'admin_coverage_rate': round((taluka_admin_count / talukas_count) * 100) if talukas_count else 0,
    }

    revenue_rows = sorted(
        taluka_performance,
        key=lambda item: (
            -(item.get('completed_value') or 0),
            (item.get('name') or '').lower(),
        )
    )[:8]

    active_talukas = [item for item in taluka_performance if item.get('total_services')]
    best_taluka = active_talukas[0] if active_talukas else None
    watch_taluka = max(
        taluka_performance or [{}],
        key=lambda item: (
            item.get('open_work') or 0,
            item.get('total_services') or 0,
            100 - (item.get('completion_rate') or 0),
        )
    ) if taluka_performance else None
    top_hotspot = hotspots[0] if hotspots else None
    lead_worker = worker_summary[0] if worker_summary else None

    district_insights = [
        {
            'title': 'Best Taluka',
            'value': best_taluka.get('name') if best_taluka else 'Awaiting activity',
            'description': (
                f"{best_taluka.get('completion_rate', 0)}% completion with {best_taluka.get('open_work', 0)} open items."
                if best_taluka else
                'The highest-performing taluka will appear here after service activity is recorded.'
            ),
            'tone': 'mint',
            'icon': 'fa-circle-check',
        },
        {
            'title': 'Needs Review',
            'value': watch_taluka.get('name') if watch_taluka else 'All clear',
            'description': (
                f"{watch_taluka.get('open_work', 0)} open items need follow-up."
                if watch_taluka else
                'No taluka has an elevated backlog right now.'
            ),
            'tone': 'rose',
            'icon': 'fa-triangle-exclamation',
        },
        {
            'title': 'Top Hotspot',
            'value': top_hotspot.get('location_label') if top_hotspot else 'No complaint hotspots',
            'description': (
                f"{top_hotspot.get('open_complaints', 0)} open complaints across this area."
                if top_hotspot else
                'Complaint pressure by village will appear here as soon as reports come in.'
            ),
            'tone': 'amber',
            'icon': 'fa-fire-flame-curved',
        },
        {
            'title': 'Top Worker',
            'value': lead_worker.get('name') if lead_worker else 'No workers yet',
            'description': (
                f"{lead_worker.get('completed_tasks', 0)} completed assignments in {lead_worker.get('taluka_name', 'district scope')}."
                if lead_worker else
                'Worker performance rankings will update automatically once assignments are created.'
            ),
            'tone': 'navy',
            'icon': 'fa-user-shield',
        },
    ]

    chart_data = {
        'service_mix': {
            'labels': ['Pending', 'In Progress', 'Completed'],
            'complaints': [
                dashboard_stats['complaints_pending'],
                dashboard_stats['complaints_in_progress'],
                dashboard_stats['complaints_completed'],
            ],
            'requests': [
                dashboard_stats['requests_pending'],
                dashboard_stats['requests_in_progress'],
                dashboard_stats['requests_completed'],
            ],
            'tasks': [
                dashboard_stats['tasks_pending'],
                0,
                dashboard_stats['tasks_completed'],
            ],
        },
        'taluka_performance': {
            'labels': [item.get('name') for item in taluka_performance[:8]],
            'completion': [item.get('completion_rate') or 0 for item in taluka_performance[:8]],
            'open_work': [item.get('open_work') or 0 for item in taluka_performance[:8]],
        },
    }

    return {
        'dashboard_stats': dashboard_stats,
        'district_insights': district_insights,
        'taluka_performance': taluka_performance,
        'hotspots': hotspots,
        'recent_complaints': all_complaints[:6],
        'recent_requests': all_requests[:8],
        'worker_summary': worker_summary,
        'escalations': escalations,
        'revenue_rows': revenue_rows,
        'recent_assigned_tasks': recent_assigned_tasks,
        'district_talukas': district_talukas,
        'district_taluka_admins': district_taluka_admins,
        'chart_data': chart_data,
        'district_map': _build_district_map_payload(admin_profile, all_complaints, all_requests, map_assigned_tasks),
    }


def _get_citizen_dashboard_data(user_id, cursor):
    cursor.execute("""
        SELECT
            id,
            name,
            phone,
            email,
            district_id,
            taluka_id,
            village_id,
            created_at
        FROM users
        WHERE id = %s
    """, (user_id,))
    user_profile = cursor.fetchone() or {}

    ensure_complaint_workflow_columns(cursor)
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN LOWER(status) = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN LOWER(status) IN ('assigned', 'in progress', 'in_progress') THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN LOWER(status) = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM complaints
        WHERE user_id = %s
    """, (user_id,))
    stats_row = cursor.fetchone() or {}
    stats = {
        'total': stats_row.get('total') or 0,
        'pending': stats_row.get('pending') or 0,
        'in_progress': stats_row.get('in_progress') or 0,
        'completed': stats_row.get('completed') or 0,
    }

    recent_complaints = _get_user_complaints(user_id, cursor, limit=5)

    cursor.execute("""
        SELECT
            id,
            COALESCE(garbage_type, 'Garbage Collection') AS garbage_type,
            COALESCE(status, 'pending') AS status,
            COALESCE(amount, 0) AS amount,
            created_at
        FROM requests
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 10
    """, (user_id,))
    user_requests = cursor.fetchall() or []

    cursor.execute("""
        SELECT
            p.id,
            p.request_id,
            p.total,
            p.owner_share,
            p.admin_share,
            p.worker_share,
            p.created_at,
            COALESCE(r.garbage_type, 'General Payment') AS garbage_type
        FROM payments p
        INNER JOIN requests r ON p.request_id = r.id
        WHERE r.user_id = %s
        ORDER BY p.created_at DESC
        LIMIT 10
    """, (user_id,))
    payment_history = cursor.fetchall() or []

    return {
        'stats': stats,
        'recent_complaints': recent_complaints,
        'user_requests': user_requests,
        'payment_history': payment_history,
        'user_profile': user_profile,
    }

# --- 🟢 REGISTRATION ROUTE ---
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        
        # Location IDs
        dist_id = request.form.get('district_id')
        tal_id = request.form.get('taluka_id')
        vil_id = request.form.get('village_id')

        if not name or not email or not password:
            flash("Name, Email, and Password are required!", "danger")
            return redirect(url_for('auth_bp.register'))

        table_name = ROLE_MAP.get(role, 'users')
        hashed_pw = generate_password_hash(password)
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        try:
            # 🔴 DUPLICATE CHECK (Dynamic)
            check_query = f"SELECT id FROM {table_name} WHERE email=%s OR phone=%s"
            cursor.execute(check_query, (email, phone))
            if cursor.fetchone():
                flash(f"User with this Email or Mobile already exists in {role.replace('_', ' ').title()}.", "danger")
                return redirect(url_for('auth_bp.register'))

            # 🔹 INSERT LOGIC
            if role == 'district_admin':
                query = "INSERT INTO district_admins (name, email, phone, password, district_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, dist_id))
            elif role == 'admin':
                query = "INSERT INTO taluka_admins (name, email, phone, password, taluka_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, tal_id))
            elif role == 'worker':
                query = "INSERT INTO village_workers (name, email, phone, password, village_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, vil_id))
            else:
                query = "INSERT INTO users (name, email, phone, password, role, village_id) VALUES (%s, %s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, 'user', vil_id))

            conn.commit()
            flash("Registration Successful! Please login.", "success")
            return redirect(url_for('auth_bp.login'))

        except Exception as e:
            conn.rollback()
            print(f"Database Error: {e}")
            flash("Registration failed due to a server error.", "danger")
        finally:
            conn.close()

    # GET Request: Fetch states for the dropdown
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM states ORDER BY name ASC")
    states = cursor.fetchall()
    conn.close()
    return render_template('auth/register.html', states=states)


# --- 🔵 LOGIN ROUTE ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        password = request.form.get('password')
        form_role = request.form.get('role') 

        table_name = ROLE_MAP.get(form_role, 'users')
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        try:
            # Using f-string for table name is okay here since it's mapped from a hardcoded dict
            query = f"SELECT * FROM {table_name} WHERE email = %s OR phone = %s"
            cursor.execute(query, (identifier, identifier))
            user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                session.clear()
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['email'] = user.get('email')
                session['role'] = form_role
                
                flash(f"Welcome back, {user['name']}!", "success")
                
                # Redirect Map
                redirect_map = {
                    'district_admin': 'auth_bp.district_dashboard',
                    'admin': 'auth_bp.taluka_dashboard',
                    'worker': 'auth_bp.worker_dashboard',
                    'user': 'auth_bp.citizen_dashboard'
                }
                return redirect(url_for(redirect_map.get(form_role, 'auth_bp.citizen_dashboard')))
            
            flash("Invalid credentials for the selected role.", "danger")
        except Exception as e:
            print(f"Login Error: {e}")
            flash("An error occurred during login.", "danger")
        finally:
            conn.close()
            
    return render_template('auth/login.html')

# --- 🔴 LOGOUT ROUTE ---
@auth_bp.route('/logout')
def logout():
    reason = (request.args.get('reason') or '').strip().lower()
    session.clear()
    if reason == 'expired':
        flash("Your session expired after 60 minutes. Please log in again.", "warning")
    else:
        flash("Successfully logged out.", "success")
    return redirect(url_for('auth_bp.login'))

# --- 🟡 DASHBOARD ROUTES (Unified Check) ---

@auth_bp.route('/citizen-dashboard')
def citizen_dashboard():
    if session.get('role') != 'user':
        return redirect(url_for('auth_bp.login'))
    
    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        data = _get_citizen_dashboard_data(user_id, cursor)
    except Exception as e:
        print(f"Error fetching stats: {e}")
        data = {
            'stats': {'total': 0, 'pending': 0, 'in_progress': 0, 'completed': 0},
            'recent_complaints': [],
            'user_requests': [],
            'payment_history': [],
            'user_profile': {},
        }
    finally:
        conn.close()

    return render_template('dashboard/citizen_dash.html', **data, citizen_page='dashboard')

@auth_bp.route('/district-dashboard')
def district_dashboard():
    if session.get('role') != 'district_admin':
        return redirect(url_for('auth_bp.login'))

    admin_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        district_profile = _get_district_admin_profile(admin_id, cursor)
        if not district_profile:
            flash("Unable to find your district profile.", "warning")
            return redirect(url_for('auth_bp.login'))

        try:
            overview = _get_district_overview_data(district_profile, cursor)
        except Exception as e:
            print(f"Error loading district dashboard overview: {e}")
            flash("Some district dashboard data is unavailable right now. Showing the basic district view instead.", "warning")
            overview = _empty_district_overview_data(district_profile)

        return render_template(
            'dashboard/district_admin.html',
            district_profile=district_profile,
            district_page='dashboard',
            **overview
        )
    except Exception as e:
        print(f"Error loading district dashboard: {e}")
        flash("Unable to load the district dashboard right now.", "danger")
        return redirect(url_for('auth_bp.login'))
    finally:
        conn.close()


@auth_bp.route('/district-talukas')
def district_talukas_page():
    if session.get('role') != 'district_admin':
        return redirect(url_for('auth_bp.login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        district_profile = _get_district_admin_profile(session.get('user_id'), cursor)
        if not district_profile:
            flash("Unable to find your district profile.", "warning")
            return redirect(url_for('auth_bp.login'))

        talukas = _get_district_taluka_rows(district_profile.get('district_id'), cursor)
        return render_template(
            'dashboard/district_talukas.html',
            district_profile=district_profile,
            district_talukas=talukas,
            district_page='talukas'
        )
    except Exception as e:
        print(f"Error loading district talukas: {e}")
        flash("Unable to load district talukas right now.", "danger")
        return redirect(url_for('auth_bp.district_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/district-taluka/<int:taluka_id>')
def district_taluka_detail(taluka_id):
    if session.get('role') != 'district_admin':
        return redirect(url_for('auth_bp.login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        district_profile = _get_district_admin_profile(session.get('user_id'), cursor)
        if not district_profile:
            flash("Unable to find your district profile.", "warning")
            return redirect(url_for('auth_bp.login'))

        taluka = _get_district_taluka_record(district_profile.get('district_id'), taluka_id, cursor)
        if not taluka:
            flash("That taluka is outside your district scope.", "warning")
            return redirect(url_for('auth_bp.district_talukas_page'))

        taluka_scope = _get_taluka_overview_data({
            'taluka_id': taluka.get('id'),
            'taluka_name': taluka.get('name'),
            'district_name': district_profile.get('district_name'),
        }, cursor)

        return render_template(
            'dashboard/district_taluka_detail.html',
            district_profile=district_profile,
            taluka=taluka,
            villages=_get_taluka_village_rows(taluka_id, cursor),
            workers=_get_taluka_worker_options(taluka_id, cursor),
            assigned_tasks=_get_taluka_recent_manual_tasks(taluka_id, cursor, limit=10),
            recent_requests=_get_taluka_request_items(taluka_id, cursor, limit=10),
            dashboard_stats=taluka_scope['dashboard_stats'],
            district_page='talukas'
        )
    except Exception as e:
        print(f"Error loading district taluka detail: {e}")
        flash("Unable to load that taluka right now.", "danger")
        return redirect(url_for('auth_bp.district_talukas_page'))
    finally:
        conn.close()


@auth_bp.route('/district-taluka-admins')
def district_taluka_admins_page():
    if session.get('role') != 'district_admin':
        return redirect(url_for('auth_bp.login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        district_profile = _get_district_admin_profile(session.get('user_id'), cursor)
        if not district_profile:
            flash("Unable to find your district profile.", "warning")
            return redirect(url_for('auth_bp.login'))

        taluka_admins = _get_district_taluka_admin_options(district_profile.get('district_id'), cursor)
        return render_template(
            'dashboard/district_taluka_admins.html',
            district_profile=district_profile,
            district_taluka_admins=taluka_admins,
            district_page='taluka_admins'
        )
    except Exception as e:
        print(f"Error loading district taluka admins: {e}")
        flash("Unable to load taluka admins right now.", "danger")
        return redirect(url_for('auth_bp.district_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/district-taluka-admin/<int:taluka_admin_id>')
def district_taluka_admin_detail(taluka_admin_id):
    if session.get('role') != 'district_admin':
        return redirect(url_for('auth_bp.login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        district_profile = _get_district_admin_profile(session.get('user_id'), cursor)
        if not district_profile:
            flash("Unable to find your district profile.", "warning")
            return redirect(url_for('auth_bp.login'))

        taluka_admin = _get_district_taluka_admin_record(district_profile.get('district_id'), taluka_admin_id, cursor)
        if not taluka_admin:
            flash("That taluka admin is outside your district scope.", "warning")
            return redirect(url_for('auth_bp.district_taluka_admins_page'))

        taluka_scope = _get_taluka_overview_data(taluka_admin, cursor)

        return render_template(
            'dashboard/district_taluka_admin_detail.html',
            district_profile=district_profile,
            taluka_admin=taluka_admin,
            villages=_get_taluka_village_rows(taluka_admin.get('taluka_id'), cursor),
            workers=_get_taluka_worker_options(taluka_admin.get('taluka_id'), cursor),
            district_tasks=_get_taluka_admin_district_tasks(taluka_admin_id, cursor, limit=10),
            dashboard_stats=taluka_scope['dashboard_stats'],
            district_page='taluka_admins'
        )
    except Exception as e:
        print(f"Error loading district taluka admin detail: {e}")
        flash("Unable to load that taluka admin right now.", "danger")
        return redirect(url_for('auth_bp.district_taluka_admins_page'))
    finally:
        conn.close()


@auth_bp.route('/taluka-dashboard')
def taluka_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    admin_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(admin_id, cursor)
        overview = _get_taluka_overview_data(admin_profile, cursor)
        return render_template(
            'dashboard/taluka_admin.html',
            admin_profile=admin_profile,
            worker_page='dashboard',
            **overview
        )
    except Exception as e:
        print(f"Error loading taluka dashboard: {e}")
        flash("Unable to load taluka dashboard right now.", "danger")
        return redirect(url_for('auth_bp.login'))
    finally:
        conn.close()


@auth_bp.route('/taluka-workers')
def taluka_workers():
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    admin_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(admin_id, cursor)
        workers = _get_taluka_worker_options(admin_profile.get('taluka_id'), cursor)
        assigned_tasks = _get_taluka_recent_manual_tasks(admin_profile.get('taluka_id'), cursor, limit=10)
        return render_template(
            'dashboard/taluka_workers.html',
            admin_profile=admin_profile,
            workers=workers,
            assigned_tasks=assigned_tasks,
            worker_page='workers'
        )
    except Exception as e:
        print(f"Error loading taluka workers: {e}")
        flash("Unable to load worker management right now.", "danger")
        return redirect(url_for('auth_bp.taluka_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/taluka-complaints')
def taluka_complaints():
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    admin_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(admin_id, cursor)
        complaints = _get_taluka_complaints(admin_profile, cursor)
        available_workers = _get_taluka_worker_options(admin_profile.get('taluka_id'), cursor)
        map_requests = _get_taluka_request_items(admin_profile.get('taluka_id'), cursor)
        map_assigned_tasks = _get_taluka_recent_manual_tasks(admin_profile.get('taluka_id'), cursor, limit=None)
        return render_template(
            'dashboard/taluka_complaints.html',
            admin_profile=admin_profile,
            complaints=complaints,
            available_workers=available_workers,
            taluka_map=_build_taluka_map_payload(admin_profile, complaints, map_requests, map_assigned_tasks),
            worker_page='complaints'
        )
    except Exception as e:
        print(f"Error loading taluka complaints: {e}")
        flash("Unable to load complaints right now.", "danger")
        return redirect(url_for('auth_bp.taluka_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/taluka-manage-complaint/<int:complaint_id>', methods=['POST'])
def taluka_manage_complaint(complaint_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.taluka_complaints')
    requested_worker_id = request.form.get('worker_id', type=int)
    requested_status = normalize_complaint_status(request.form.get('status') or 'Pending')

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(session.get('user_id'), cursor)
        ensure_complaint_workflow_columns(cursor)
        cursor.execute("""
            SELECT
                id,
                worker_id,
                COALESCE(status, 'Pending') AS status
            FROM complaints
            WHERE id = %s AND taluka = %s
        """, (complaint_id, admin_profile.get('taluka_name')))
        complaint = cursor.fetchone()
        if not complaint:
            flash("That complaint is outside your taluka scope.", "warning")
            return redirect(redirect_target)

        worker_id = requested_worker_id if requested_worker_id is not None else complaint.get('worker_id')
        if request.form.get('worker_id') == '':
            worker_id = None

        worker = None
        if worker_id:
            worker = _get_taluka_worker_record(admin_profile.get('taluka_id'), worker_id, cursor)
            if not worker:
                flash("Choose a worker from your taluka before saving the complaint.", "warning")
                return redirect(redirect_target)

        status_key = complaint_status_key(requested_status)
        if worker_id and status_key == 'pending':
            status_key = 'assigned'
        if not worker_id and status_key in ('assigned', 'in_progress'):
            status_key = 'pending'
        if status_key == 'completed' and not worker_id:
            flash("Assign the complaint to a worker before marking it completed.", "warning")
            return redirect(redirect_target)

        columns = [
            "worker_id = %s",
            "admin_id = %s",
            "status = %s",
            "updated_at = NOW()",
        ]
        values = [worker_id, session.get('user_id'), normalize_complaint_status(status_key)]

        if worker_id and not complaint.get('worker_id'):
            columns.append("assigned_at = NOW()")
        elif not worker_id:
            columns.append("assigned_at = NULL")

        if status_key == 'completed':
            columns.append("resolved_at = NOW()")
        else:
            columns.append("resolved_at = NULL")

        cursor.execute(f"""
            UPDATE complaints
            SET {', '.join(columns)}
            WHERE id = %s
        """, tuple(values + [complaint_id]))
        conn.commit()

        if worker and status_key == 'assigned':
            flash(f"Complaint assigned to {worker.get('name')}.", "success")
        else:
            flash(f"Complaint status updated to {normalize_complaint_status(status_key)}.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error updating taluka complaint: {e}")
        flash("Unable to update the complaint right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@auth_bp.route('/taluka-villages')
def taluka_villages():
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    admin_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(admin_id, cursor)
        return render_template(
            'dashboard/taluka_villages.html',
            admin_profile=admin_profile,
            villages=_get_taluka_village_rows(admin_profile.get('taluka_id'), cursor),
            worker_page='villages'
        )
    except Exception as e:
        print(f"Error loading taluka villages: {e}")
        flash("Unable to load villages right now.", "danger")
        return redirect(url_for('auth_bp.taluka_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/taluka-profile')
def taluka_profile():
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    admin_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(admin_id, cursor)
        overview = _get_taluka_overview_data(admin_profile, cursor)
        return render_template(
            'dashboard/taluka_profile.html',
            admin_profile=admin_profile,
            dashboard_stats=overview['dashboard_stats'],
            worker_page='profile'
        )
    except Exception as e:
        print(f"Error loading taluka profile: {e}")
        flash("Unable to load profile right now.", "danger")
        return redirect(url_for('auth_bp.taluka_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/taluka-assign-request/<int:request_id>', methods=['POST'])
def taluka_assign_request(request_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.taluka_dashboard')
    worker_id = request.form.get('worker_id', type=int)
    if not worker_id:
        flash("Please choose a worker before assigning a request.", "warning")
        return redirect(redirect_target)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(session.get('user_id'), cursor)
        worker = _get_taluka_worker_record(admin_profile.get('taluka_id'), worker_id, cursor)
        if not worker:
            flash("Select a worker from your taluka before assigning the request.", "warning")
            return redirect(redirect_target)

        cursor.execute("""
            SELECT
                r.id
            FROM requests r
            LEFT JOIN users u ON r.user_id = u.id
            LEFT JOIN villages v ON u.village_id = v.id
            WHERE r.id = %s AND COALESCE(u.taluka_id, v.taluka_id) = %s
        """, (request_id, admin_profile.get('taluka_id')))
        request_row = cursor.fetchone()
        if not request_row:
            flash("That request is outside your taluka scope.", "warning")
            return redirect(redirect_target)

        cursor.execute("""
            UPDATE requests
            SET worker_id = %s,
                admin_id = %s,
                status = 'pending'
            WHERE id = %s
        """, (worker_id, session.get('user_id'), request_id))
        conn.commit()
        flash(f"Request assigned to {worker.get('name')} successfully.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error assigning taluka request: {e}")
        flash("Unable to assign the request right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@auth_bp.route('/taluka-assign-task', methods=['POST'])
def taluka_assign_task():
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.taluka_workers')
    worker_id = request.form.get('worker_id', type=int)
    location_name = (request.form.get('location_name') or '').strip()
    description = (request.form.get('description') or '').strip()
    priority = (request.form.get('priority') or 'medium').strip().lower()

    if priority not in {'low', 'medium', 'high'}:
        priority = 'medium'

    if not worker_id or not location_name or not description:
        flash("Choose a worker, area, and task description before assigning work.", "warning")
        return redirect(redirect_target)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        admin_profile = _get_taluka_admin_profile(session.get('user_id'), cursor)
        worker = _get_taluka_worker_record(admin_profile.get('taluka_id'), worker_id, cursor)
        if not worker:
            flash("You can only assign tasks to workers inside your taluka.", "warning")
            return redirect(redirect_target)

        cursor.execute("""
            INSERT INTO tasks (worker_id, location_name, description, status, priority, assigned_at)
            VALUES (%s, %s, %s, 'pending', %s, NOW())
        """, (worker_id, location_name, description, priority))
        conn.commit()
        flash(f"Task assigned to {worker.get('name')} for {worker.get('village_name')}.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error assigning taluka task: {e}")
        flash("Unable to assign the task right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)

@auth_bp.route('/worker-dashboard')
def worker_dashboard():
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))
    
    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        worker_profile = _get_worker_profile(worker_id, cursor)
        worker_stats = _get_worker_assignment_stats(worker_id, cursor)
        completed = worker_stats.get('completed') or 0
        assigned = worker_stats.get('assigned') or 0
        worker_stats['rating'] = round(min(5, max(1, completed / 5)), 1) if completed else 0
        worker_stats['efficiency'] = round((completed / assigned) * 100) if assigned else 0
        recent_active_tasks = _get_worker_work_items(worker_id, cursor, worker_profile=worker_profile, status_filter='active', limit=5)
        
        return render_template('dashboard/worker_dash.html', 
                             worker_profile=worker_profile,
                             worker_stats=worker_stats,
                             recent_active_tasks=recent_active_tasks if recent_active_tasks else [],
                             worker_map=_build_worker_map_config(worker_profile),
                             worker_page='dashboard')
    
    except Exception as e:
        print(f"Error fetching worker data: {e}")
        flash("Error loading dashboard data.", "danger")
        return redirect(url_for('auth_bp.login'))
    finally:
        conn.close()


@auth_bp.route('/worker-stats-api')
def worker_stats_api():
    if session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 403

    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        stats = _get_worker_assignment_stats(worker_id, cursor)
        assigned = stats.get('assigned') or 0
        completed = stats.get('completed') or 0
        efficiency = round((completed / assigned) * 100) if assigned else 0
        rating = round(min(5, max(1, completed / 5)), 1) if completed else 0

        return jsonify({
            'assigned': assigned,
            'pending': stats.get('pending') or 0,
            'in_progress': stats.get('in_progress') or 0,
            'completed': completed,
            'completed_today': stats.get('completed_today') or 0,
            'monthly_earnings': stats.get('monthly_earnings') or 0,
            'today_earnings': stats.get('today_earnings') or 0,
            'efficiency': efficiency,
            'rating': rating,
        })
    except Exception as e:
        print(f"Error fetching worker stats api data: {e}")
        return jsonify({'assigned': 0, 'pending': 0, 'in_progress': 0, 'completed': 0, 'completed_today': 0, 'monthly_earnings': 0, 'today_earnings': 0, 'efficiency': 0, 'rating': 0})
    finally:
        conn.close()


@auth_bp.route('/worker-tasks-api')
def worker_tasks_api():
    if session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 403

    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        worker_profile = _get_worker_profile(worker_id, cursor)
        tasks = _get_worker_work_items(worker_id, cursor, worker_profile=worker_profile, status_filter='active', limit=10)
        return jsonify({'active_tasks': tasks})
    except Exception as e:
        print(f"Error fetching worker tasks api data: {e}")
        return jsonify({'active_tasks': []})
    finally:
        conn.close()


@auth_bp.route('/worker-start-task/<int:task_id>', methods=['POST'])
def worker_start_task(task_id):
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.worker_dashboard')
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE requests
            SET status = 'in_progress'
            WHERE id = %s AND worker_id = %s AND status = 'pending'
        """, (task_id, session.get('user_id')))
        conn.commit()
        if cursor.rowcount:
            flash("Task started successfully.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error starting worker task: {e}")
        flash("Unable to start the task right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@auth_bp.route('/worker-start-complaint/<int:complaint_id>', methods=['POST'])
def worker_start_complaint(complaint_id):
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.worker_dashboard')
    conn = get_db()
    cursor = conn.cursor()

    try:
        ensure_complaint_workflow_columns(cursor)
        cursor.execute("""
            UPDATE complaints
            SET status = 'In Progress',
                updated_at = NOW()
            WHERE id = %s
              AND worker_id = %s
              AND LOWER(COALESCE(status, 'Pending')) IN ('pending', 'assigned', 'in progress', 'in_progress')
        """, (complaint_id, session.get('user_id')))
        conn.commit()
        if cursor.rowcount:
            flash("Complaint work started successfully.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error starting worker complaint: {e}")
        flash("Unable to start the complaint right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@auth_bp.route('/worker-complete-task/<int:task_id>', methods=['POST'])
def worker_complete_task(task_id):
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.worker_dashboard')
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE requests
            SET status = 'completed'
            WHERE id = %s AND worker_id = %s AND status IN ('pending', 'in_progress')
        """, (task_id, session.get('user_id')))
        conn.commit()
        if cursor.rowcount:
            flash("Task marked as completed.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error completing worker task: {e}")
        flash("Unable to complete the task right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@auth_bp.route('/worker-complete-complaint/<int:complaint_id>', methods=['POST'])
def worker_complete_complaint(complaint_id):
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.worker_dashboard')
    conn = get_db()
    cursor = conn.cursor()

    try:
        ensure_complaint_workflow_columns(cursor)
        cursor.execute("""
            UPDATE complaints
            SET status = 'Completed',
                updated_at = NOW(),
                resolved_at = NOW()
            WHERE id = %s
              AND worker_id = %s
              AND LOWER(COALESCE(status, 'Pending')) IN ('pending', 'assigned', 'in progress', 'in_progress')
        """, (complaint_id, session.get('user_id')))
        conn.commit()
        if cursor.rowcount:
            flash("Complaint marked as completed.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error completing worker complaint: {e}")
        flash("Unable to complete the complaint right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@auth_bp.route('/worker-complete-assigned-task/<int:task_id>', methods=['POST'])
def worker_complete_assigned_task(task_id):
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    redirect_target = _post_redirect_target('auth_bp.worker_dashboard')
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE tasks
            SET status = 'completed'
            WHERE id = %s AND worker_id = %s AND status = 'pending'
        """, (task_id, session.get('user_id')))
        conn.commit()
        if cursor.rowcount:
            flash("Assigned task marked as completed.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Error completing assigned task: {e}")
        flash("Unable to complete the assigned task right now.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@auth_bp.route('/worker-requests')
def worker_requests():
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        worker_profile = _get_worker_profile(worker_id, cursor)
        tasks = _get_worker_work_items(worker_id, cursor, worker_profile=worker_profile, status_filter='all')

        return render_template(
            'dashboard/worker_requests.html',
            worker_profile=worker_profile,
            tasks=tasks,
            worker_page='tasks'
        )
    except Exception as e:
        print(f"Error loading worker requests: {e}")
        flash("Unable to load worker tasks right now.", "danger")
        return redirect(url_for('auth_bp.worker_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/worker-assigned-areas')
def worker_assigned_areas():
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        worker_profile = _get_worker_profile(worker_id, cursor)
        area_stats = _get_worker_assignment_stats(worker_id, cursor)

        assigned_areas = []
        if worker_profile:
            assigned_areas.append({
                'village_name': worker_profile.get('village_name') or 'Village not assigned',
                'vehicle_no': worker_profile.get('vehicle_no') or 'Not assigned',
                'status': worker_profile.get('status') or 'Active',
                'total_tasks': area_stats.get('total_tasks') or 0,
                'pending_tasks': area_stats.get('pending_tasks') or 0,
                'in_progress_tasks': area_stats.get('in_progress_tasks') or 0,
                'completed_tasks': area_stats.get('completed_tasks') or 0,
            })

        return render_template(
            'dashboard/worker_assigned_areas.html',
            worker_profile=worker_profile,
            assigned_areas=assigned_areas,
            worker_page='areas'
        )
    except Exception as e:
        print(f"Error loading assigned areas: {e}")
        flash("Unable to load assigned area details right now.", "danger")
        return redirect(url_for('auth_bp.worker_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/worker-history')
def worker_history():
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        worker_profile = _get_worker_profile(worker_id, cursor)
        history_items = _get_worker_work_items(worker_id, cursor, worker_profile=worker_profile, status_filter='completed')

        return render_template(
            'dashboard/worker_history.html',
            worker_profile=worker_profile,
            history_items=history_items,
            worker_page='history'
        )
    except Exception as e:
        print(f"Error loading worker history: {e}")
        flash("Unable to load worker history right now.", "danger")
        return redirect(url_for('auth_bp.worker_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/worker-earnings')
def worker_earnings():
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        worker_profile = _get_worker_profile(worker_id, cursor)
        cursor.execute("""
            SELECT
                id,
                COALESCE(garbage_type, 'Garbage Collection') AS garbage_type,
                COALESCE(amount, 0) AS amount,
                COALESCE(status, 'pending') AS status,
                created_at
            FROM requests
            WHERE worker_id = %s
            ORDER BY created_at DESC
        """, (worker_id,))
        earnings_rows = cursor.fetchall() or []

        total_earned = sum((row.get('amount') or 0) for row in earnings_rows if row.get('status') == 'completed')
        pending_amount = sum((row.get('amount') or 0) for row in earnings_rows if row.get('status') != 'completed')

        return render_template(
            'dashboard/worker_earnings.html',
            worker_profile=worker_profile,
            earnings_rows=earnings_rows,
            total_earned=total_earned,
            pending_amount=pending_amount,
            worker_page='earnings'
        )
    except Exception as e:
        print(f"Error loading worker earnings: {e}")
        flash("Unable to load worker earnings right now.", "danger")
        return redirect(url_for('auth_bp.worker_dashboard'))
    finally:
        conn.close()


@auth_bp.route('/worker-profile')
def worker_profile():
    if session.get('role') != 'worker':
        return redirect(url_for('auth_bp.login'))

    worker_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        profile = _get_worker_profile(worker_id, cursor)
        profile_stats = _get_worker_assignment_stats(worker_id, cursor)

        return render_template(
            'dashboard/worker_profile.html',
            worker_profile=profile,
            profile_stats=profile_stats,
            worker_page='profile'
        )
    except Exception as e:
        print(f"Error loading worker profile: {e}")
        flash("Unable to load worker profile right now.", "danger")
        return redirect(url_for('auth_bp.worker_dashboard'))
    finally:
        conn.close()

# --- 🟡 API ROUTES FOR DROPDOWNS ---

@auth_bp.route('/get_districts/<int:state_id>')
def get_districts(state_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM districts WHERE state_id = %s ORDER BY name ASC", (state_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

@auth_bp.route('/get_talukas/<int:district_id>')
def get_talukas(district_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM talukas WHERE district_id = %s ORDER BY name ASC", (district_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

@auth_bp.route('/get_villages/<int:taluka_id>')
def get_villages(taluka_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM villages WHERE taluka_id = %s ORDER BY name ASC", (taluka_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)
