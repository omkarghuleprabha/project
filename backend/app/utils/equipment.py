from datetime import datetime

import mysql.connector

from app.utils.staff_portal import role_display_name


EQUIPMENT_CATALOG = [
    {
        'category_key': 'ppe',
        'category_name': 'Personal Protective Equipment (PPE)',
        'items': [
            {
                'item_key': 'gloves_heavy_duty',
                'item_name': 'Gloves (heavy-duty, cut-resistant)',
                'description': 'Protects from sharp objects and direct waste contact.',
            },
            {
                'item_key': 'face_mask_respirator',
                'item_name': 'Face mask / respirator',
                'description': 'Prevents inhalation of dust, bacteria, and strong odors.',
            },
            {
                'item_key': 'safety_boots',
                'item_name': 'Safety boots (steel-toe, waterproof)',
                'description': 'Protects feet from injuries and waste liquids.',
            },
            {
                'item_key': 'reflective_jacket',
                'item_name': 'Reflective jacket / uniform',
                'description': 'Improves visibility during road and night operations.',
            },
            {
                'item_key': 'helmet',
                'item_name': 'Helmet',
                'description': 'Provides extra protection in hazardous operating zones.',
            },
            {
                'item_key': 'safety_goggles',
                'item_name': 'Safety goggles',
                'description': 'Protects eyes from splashes, dust, and debris.',
            },
        ],
    },
    {
        'category_key': 'collection_tools',
        'category_name': 'Waste Collection Tools',
        'items': [
            {
                'item_key': 'garbage_bins',
                'item_name': 'Garbage bins / containers',
                'description': 'Segregated containers for wet and dry waste collection.',
            },
            {
                'item_key': 'hand_carts',
                'item_name': 'Hand carts / push carts',
                'description': 'Supports local collection runs and door-to-door service.',
            },
            {
                'item_key': 'wheelbarrows',
                'item_name': 'Wheelbarrows',
                'description': 'Useful for narrow streets, lanes, and village routes.',
            },
            {
                'item_key': 'garbage_grabbers',
                'item_name': 'Garbage grabbers / pick-up sticks',
                'description': 'Helps avoid direct contact with hazardous waste.',
            },
            {
                'item_key': 'shovels_brooms',
                'item_name': 'Shovels and brooms',
                'description': 'For street cleaning and loose waste collection.',
            },
            {
                'item_key': 'rakes',
                'item_name': 'Rakes',
                'description': 'Useful for gathering scattered dry waste efficiently.',
            },
        ],
    },
    {
        'category_key': 'transport',
        'category_name': 'Transportation Equipment',
        'items': [
            {
                'item_key': 'garbage_trucks',
                'item_name': 'Garbage trucks / compactors',
                'description': 'For large-scale waste movement and compact collection.',
            },
            {
                'item_key': 'mini_trucks',
                'item_name': 'Mini trucks / auto tippers',
                'description': 'Ideal for cities, towns, and mixed urban-rural routes.',
            },
            {
                'item_key': 'tractors_trailers',
                'item_name': 'Tractors with trailers',
                'description': 'Commonly used for village and rural transport coverage.',
            },
            {
                'item_key': 'dump_bins',
                'item_name': 'Dump bins / community containers',
                'description': 'Supports fixed-point collection and aggregation.',
            },
        ],
    },
    {
        'category_key': 'hygiene',
        'category_name': 'Hygiene & Cleaning Supplies',
        'items': [
            {
                'item_key': 'hand_sanitizer',
                'item_name': 'Hand sanitizer / disinfectant',
                'description': 'Improves hygiene and reduces contamination risk.',
            },
            {
                'item_key': 'soap_water_access',
                'item_name': 'Soap and water access',
                'description': 'Maintains sanitation during and after field work.',
            },
            {
                'item_key': 'first_aid_kit',
                'item_name': 'First aid kit',
                'description': 'Provides essential support for minor injuries and emergencies.',
            },
            {
                'item_key': 'deodorizing_sprays',
                'item_name': 'Deodorizing sprays',
                'description': 'Helps manage odor in vehicles, bins, and work zones.',
            },
            {
                'item_key': 'uniform_washing_facilities',
                'item_name': 'Uniform washing facilities',
                'description': 'Supports cleaning and reuse of uniforms and safety wear.',
            },
        ],
    },
]

EQUIPMENT_ITEMS = []
EQUIPMENT_ITEM_LOOKUP = {}
for category in EQUIPMENT_CATALOG:
    for item in category['items']:
        enriched_item = {
            **item,
            'category_key': category['category_key'],
            'category_name': category['category_name'],
        }
        EQUIPMENT_ITEMS.append(enriched_item)
        EQUIPMENT_ITEM_LOOKUP[item['item_key']] = enriched_item

REQUEST_STATUS_LABELS = {
    'pending': 'Pending',
    'fulfilled': 'Fulfilled',
    'rejected': 'Rejected',
}

INVENTORY_SCOPE_LABELS = {
    'state': 'State Reserve',
    'district': 'District Reserve',
    'taluka': 'Taluka Reserve',
    'worker': 'Worker Allocation',
}


def equipment_catalog_groups():
    return EQUIPMENT_CATALOG


def equipment_item(item_key):
    return EQUIPMENT_ITEM_LOOKUP.get(item_key)


def normalize_equipment_item(item_key, default=None):
    if item_key in EQUIPMENT_ITEM_LOOKUP:
        return item_key
    return default


def normalize_request_status(status, default='pending'):
    clean_status = (status or '').strip().lower()
    if clean_status not in REQUEST_STATUS_LABELS:
        return default
    return clean_status


def request_status_label(status):
    return REQUEST_STATUS_LABELS.get(normalize_request_status(status), REQUEST_STATUS_LABELS['pending'])


def request_status_class(status):
    return normalize_request_status(status).replace('_', '-')


def scope_role_label(scope_role):
    return INVENTORY_SCOPE_LABELS.get(scope_role, role_display_name(scope_role))


def format_datetime_text(value, fallback='Recently'):
    if isinstance(value, datetime):
        return value.strftime('%d %b %Y %I:%M %p')
    return fallback


def equipment_inventory_tone(quantity):
    amount = int(quantity or 0)
    if amount <= 0:
        return 'critical', 'Out of stock'
    if amount < 5:
        return 'low', 'Low stock'
    if amount < 15:
        return 'watch', 'Monitor'
    return 'healthy', 'Healthy stock'


def _table_columns(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    columns = {}
    for row in cursor.fetchall() or []:
        if isinstance(row, dict):
            columns[row.get('Field')] = row
        else:
            columns[row[0]] = row
    return columns


def _legacy_item_key(item_label):
    raw = (item_label or '').strip().lower()
    if not raw:
        return None

    for item in EQUIPMENT_ITEMS:
        if raw in {
            item['item_key'].strip().lower(),
            item['item_name'].strip().lower(),
        }:
            return item['item_key']

    compact = raw.replace('-', ' ').replace('_', ' ')
    for item in EQUIPMENT_ITEMS:
        item_key_text = item['item_key'].replace('_', ' ').strip().lower()
        item_name_text = item['item_name'].strip().lower()
        if compact == item_key_text or compact == item_name_text:
            return item['item_key']
        if compact in item_name_text or item_name_text in compact:
            return item['item_key']

    return None


def ensure_equipment_schema(cursor):
    def _safe_execute(statement):
        try:
            cursor.execute(statement)
        except mysql.connector.Error as err:
            if getattr(err, 'errno', None) != 1050:
                raise

    try:
        _safe_execute("""
            CREATE TABLE IF NOT EXISTS equipment_inventory (
                id INT NOT NULL AUTO_INCREMENT,
                scope_role VARCHAR(30) NOT NULL,
                scope_id INT NOT NULL,
                item_key VARCHAR(80) NOT NULL,
                item_name VARCHAR(180) NOT NULL,
                category_name VARCHAR(140) NOT NULL,
                quantity INT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uniq_equipment_inventory_scope_item (scope_role, scope_id, item_key),
                KEY idx_equipment_inventory_scope (scope_role, scope_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        _safe_execute("""
            CREATE TABLE IF NOT EXISTS equipment_requests (
                id INT NOT NULL AUTO_INCREMENT,
                requester_role VARCHAR(30) NOT NULL,
                requester_id INT NOT NULL,
                requester_scope_role VARCHAR(30) DEFAULT NULL,
                requester_scope_id INT DEFAULT NULL,
                target_role VARCHAR(30) NOT NULL,
                target_scope_role VARCHAR(30) DEFAULT NULL,
                target_scope_id INT NOT NULL,
                item_key VARCHAR(80) NOT NULL,
                item_name VARCHAR(180) NOT NULL,
                category_name VARCHAR(140) NOT NULL,
                quantity_requested INT NOT NULL DEFAULT 0,
                quantity_fulfilled INT NOT NULL DEFAULT 0,
                priority VARCHAR(20) DEFAULT 'normal',
                reason TEXT DEFAULT NULL,
                notes TEXT DEFAULT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                fulfilled_at TIMESTAMP NULL DEFAULT NULL,
                PRIMARY KEY (id),
                KEY idx_equipment_requests_requester (requester_role, requester_id),
                KEY idx_equipment_requests_target (target_role, target_scope_id),
                KEY idx_equipment_requests_status (status),
                KEY idx_equipment_requests_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        _safe_execute("""
            CREATE TABLE IF NOT EXISTS equipment_transactions (
                id INT NOT NULL AUTO_INCREMENT,
                transaction_type VARCHAR(40) NOT NULL,
                actor_role VARCHAR(30) DEFAULT NULL,
                actor_id INT DEFAULT NULL,
                from_scope_role VARCHAR(30) DEFAULT NULL,
                from_scope_id INT DEFAULT NULL,
                to_scope_role VARCHAR(30) DEFAULT NULL,
                to_scope_id INT DEFAULT NULL,
                item_key VARCHAR(80) NOT NULL,
                item_name VARCHAR(180) NOT NULL,
                category_name VARCHAR(140) NOT NULL,
                quantity INT NOT NULL DEFAULT 0,
                notes TEXT DEFAULT NULL,
                related_request_id INT DEFAULT NULL,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY idx_equipment_transactions_from_scope (from_scope_role, from_scope_id),
                KEY idx_equipment_transactions_to_scope (to_scope_role, to_scope_id),
                KEY idx_equipment_transactions_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        request_columns = _table_columns(cursor, 'equipment_requests')
        request_column_definitions = {
            'requester_role': "requester_role VARCHAR(30) DEFAULT NULL",
            'requester_id': "requester_id INT DEFAULT NULL",
            'requester_scope_role': "requester_scope_role VARCHAR(30) DEFAULT NULL",
            'requester_scope_id': "requester_scope_id INT DEFAULT NULL",
            'target_role': "target_role VARCHAR(30) DEFAULT NULL",
            'target_scope_role': "target_scope_role VARCHAR(30) DEFAULT NULL",
            'target_scope_id': "target_scope_id INT DEFAULT NULL",
            'item_key': "item_key VARCHAR(80) DEFAULT NULL",
            'item_name': "item_name VARCHAR(180) DEFAULT NULL",
            'category_name': "category_name VARCHAR(140) DEFAULT NULL",
            'quantity_requested': "quantity_requested INT NOT NULL DEFAULT 0",
            'quantity_fulfilled': "quantity_fulfilled INT NOT NULL DEFAULT 0",
            'notes': "notes TEXT DEFAULT NULL",
            'updated_at': "updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
            'fulfilled_at': "fulfilled_at TIMESTAMP NULL DEFAULT NULL",
        }
        legacy_request_table = 'worker_id' in request_columns and 'requester_role' not in request_columns

        for column_name, column_definition in request_column_definitions.items():
            if column_name not in request_columns:
                cursor.execute(f"ALTER TABLE equipment_requests ADD COLUMN {column_definition}")
                request_columns[column_name] = {'Field': column_name}

        if legacy_request_table:
            cursor.execute("""
                SELECT id, worker_id, item_type, quantity, priority, reason, status, created_at
                FROM equipment_requests
                WHERE requester_role IS NULL
            """)
            legacy_rows = cursor.fetchall() or []
            for row in legacy_rows:
                row_id = row.get('id') if isinstance(row, dict) else row[0]
                item_type = row.get('item_type') if isinstance(row, dict) else row[2]
                quantity = row.get('quantity') if isinstance(row, dict) else row[3]

                item_key = _legacy_item_key(item_type)
                item = equipment_item(item_key) if item_key else None

                cursor.execute("""
                    UPDATE equipment_requests er
                    LEFT JOIN village_workers vw ON er.worker_id = vw.id
                    LEFT JOIN villages v ON vw.village_id = v.id
                    SET
                        er.requester_role = 'worker',
                        er.requester_id = er.worker_id,
                        er.requester_scope_role = 'worker',
                        er.requester_scope_id = er.worker_id,
                        er.target_role = 'admin',
                        er.target_scope_role = 'taluka',
                        er.target_scope_id = v.taluka_id,
                        er.item_key = %s,
                        er.item_name = %s,
                        er.category_name = %s,
                        er.quantity_requested = COALESCE(er.quantity, %s),
                        er.quantity_fulfilled = CASE
                            WHEN LOWER(COALESCE(er.status, 'pending')) = 'fulfilled' THEN COALESCE(er.quantity, %s)
                            ELSE 0
                        END,
                        er.notes = er.reason
                    WHERE er.id = %s
                """, (
                    item['item_key'] if item else None,
                    item['item_name'] if item else item_type,
                    item['category_name'] if item else 'Legacy Equipment Request',
                    quantity or 0,
                    quantity or 0,
                    row_id,
                ))
    except mysql.connector.Error as err:
        raise


def ensure_inventory_rows(cursor, scope_role, scope_id):
    ensure_equipment_schema(cursor)
    for item in EQUIPMENT_ITEMS:
        cursor.execute("""
            INSERT INTO equipment_inventory (
                scope_role,
                scope_id,
                item_key,
                item_name,
                category_name,
                quantity
            ) VALUES (%s, %s, %s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE
                item_name = %s,
                category_name = %s
        """, (
            scope_role,
            scope_id,
            item['item_key'],
            item['item_name'],
            item['category_name'],
            item['item_name'],
            item['category_name'],
        ))


def fetch_inventory(cursor, scope_role, scope_id):
    ensure_inventory_rows(cursor, scope_role, scope_id)
    cursor.execute("""
        SELECT
            scope_role,
            scope_id,
            item_key,
            item_name,
            category_name,
            quantity,
            updated_at
        FROM equipment_inventory
        WHERE scope_role = %s AND scope_id = %s
        ORDER BY category_name ASC, item_name ASC
    """, (scope_role, scope_id))

    inventory_rows = []
    for row in cursor.fetchall() or []:
        tone, stock_label = equipment_inventory_tone(row.get('quantity'))
        inventory_rows.append({
            **row,
            'quantity': row.get('quantity') or 0,
            'updated_at_text': format_datetime_text(row.get('updated_at'), fallback='Not updated yet'),
            'stock_tone': tone,
            'stock_label': stock_label,
        })
    return inventory_rows


def inventory_summary(rows):
    total_quantity = sum((row.get('quantity') or 0) for row in (rows or []))
    low_stock_count = sum(1 for row in (rows or []) if (row.get('quantity') or 0) < 5)
    healthy_count = sum(1 for row in (rows or []) if (row.get('quantity') or 0) >= 5)
    return {
        'total_quantity': total_quantity,
        'low_stock_count': low_stock_count,
        'healthy_count': healthy_count,
        'item_count': len(rows or []),
    }


def adjust_inventory(cursor, scope_role, scope_id, item_key, quantity_delta):
    ensure_inventory_rows(cursor, scope_role, scope_id)
    cursor.execute("""
        UPDATE equipment_inventory
        SET quantity = quantity + %s
        WHERE scope_role = %s AND scope_id = %s AND item_key = %s
    """, (int(quantity_delta or 0), scope_role, scope_id, item_key))


def current_inventory_quantity(cursor, scope_role, scope_id, item_key):
    ensure_inventory_rows(cursor, scope_role, scope_id)
    cursor.execute("""
        SELECT quantity
        FROM equipment_inventory
        WHERE scope_role = %s AND scope_id = %s AND item_key = %s
    """, (scope_role, scope_id, item_key))
    row = cursor.fetchone() or {}
    return int(row.get('quantity') or 0)


def create_equipment_request(
    cursor,
    *,
    requester_role,
    requester_id,
    requester_scope_role,
    requester_scope_id,
    target_role,
    target_scope_role,
    target_scope_id,
    item_key,
    quantity_requested,
    reason,
    priority='normal',
    notes=None,
):
    ensure_equipment_schema(cursor)
    item = equipment_item(item_key)
    if not item:
        raise ValueError('Unknown equipment item.')

    cursor.execute("""
        INSERT INTO equipment_requests (
            requester_role,
            requester_id,
            requester_scope_role,
            requester_scope_id,
            target_role,
            target_scope_role,
            target_scope_id,
            item_key,
            item_name,
            category_name,
            quantity_requested,
            quantity_fulfilled,
            priority,
            reason,
            notes,
            status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, 'pending')
    """, (
        requester_role,
        requester_id,
        requester_scope_role,
        requester_scope_id,
        target_role,
        target_scope_role,
        target_scope_id,
        item['item_key'],
        item['item_name'],
        item['category_name'],
        max(int(quantity_requested), 1),
        priority,
        reason,
        notes,
    ))
    return cursor.lastrowid


def add_transaction(
    cursor,
    *,
    transaction_type,
    actor_role,
    actor_id,
    from_scope_role,
    from_scope_id,
    to_scope_role,
    to_scope_id,
    item_key,
    quantity,
    notes=None,
    related_request_id=None,
):
    ensure_equipment_schema(cursor)
    item = equipment_item(item_key)
    if not item:
        raise ValueError('Unknown equipment item.')

    cursor.execute("""
        INSERT INTO equipment_transactions (
            transaction_type,
            actor_role,
            actor_id,
            from_scope_role,
            from_scope_id,
            to_scope_role,
            to_scope_id,
            item_key,
            item_name,
            category_name,
            quantity,
            notes,
            related_request_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        transaction_type,
        actor_role,
        actor_id,
        from_scope_role,
        from_scope_id,
        to_scope_role,
        to_scope_id,
        item['item_key'],
        item['item_name'],
        item['category_name'],
        max(int(quantity), 0),
        notes,
        related_request_id,
    ))
    return cursor.lastrowid


def issue_inventory(
    cursor,
    *,
    actor_role,
    actor_id,
    from_scope_role,
    from_scope_id,
    to_scope_role,
    to_scope_id,
    item_key,
    quantity,
    notes=None,
    related_request_id=None,
    transaction_type='issue',
):
    quantity = max(int(quantity), 1)
    available_quantity = current_inventory_quantity(cursor, from_scope_role, from_scope_id, item_key)
    if available_quantity < quantity:
        raise ValueError('Not enough stock available for this transfer.')

    adjust_inventory(cursor, from_scope_role, from_scope_id, item_key, -quantity)
    if to_scope_role in {'state', 'district', 'taluka', 'worker'}:
        adjust_inventory(cursor, to_scope_role, to_scope_id, item_key, quantity)

    add_transaction(
        cursor,
        transaction_type=transaction_type,
        actor_role=actor_role,
        actor_id=actor_id,
        from_scope_role=from_scope_role,
        from_scope_id=from_scope_id,
        to_scope_role=to_scope_role,
        to_scope_id=to_scope_id,
        item_key=item_key,
        quantity=quantity,
        notes=notes,
        related_request_id=related_request_id,
    )


def restock_inventory(cursor, *, actor_role, actor_id, scope_role, scope_id, item_key, quantity, notes=None):
    quantity = max(int(quantity), 1)
    adjust_inventory(cursor, scope_role, scope_id, item_key, quantity)
    add_transaction(
        cursor,
        transaction_type='restock',
        actor_role=actor_role,
        actor_id=actor_id,
        from_scope_role='supplier',
        from_scope_id=0,
        to_scope_role=scope_role,
        to_scope_id=scope_id,
        item_key=item_key,
        quantity=quantity,
        notes=notes,
        related_request_id=None,
    )


def mark_request_fulfilled(cursor, request_id, quantity, notes=None):
    cursor.execute("""
        UPDATE equipment_requests
        SET status = 'fulfilled',
            quantity_fulfilled = %s,
            notes = %s,
            fulfilled_at = NOW()
        WHERE id = %s
    """, (max(int(quantity), 1), notes, request_id))


def mark_request_rejected(cursor, request_id, notes=None):
    cursor.execute("""
        UPDATE equipment_requests
        SET status = 'rejected',
            notes = %s
        WHERE id = %s
    """, (notes, request_id))


def _request_actor_details(cursor, request_rows):
    worker_ids = {row.get('requester_id') for row in request_rows if row.get('requester_role') == 'worker' and row.get('requester_id')}
    taluka_ids = {row.get('requester_id') for row in request_rows if row.get('requester_role') == 'admin' and row.get('requester_id')}
    district_ids = {row.get('requester_id') for row in request_rows if row.get('requester_role') == 'district_admin' and row.get('requester_id')}

    workers = {}
    talukas = {}
    districts = {}

    if worker_ids:
        placeholders = ', '.join(['%s'] * len(worker_ids))
        cursor.execute(f"""
            SELECT
                vw.id,
                vw.name,
                COALESCE(v.name, 'Assigned Village') AS scope_name
            FROM village_workers vw
            LEFT JOIN villages v ON vw.village_id = v.id
            WHERE vw.id IN ({placeholders})
        """, tuple(worker_ids))
        workers = {row['id']: row for row in (cursor.fetchall() or [])}

    if taluka_ids:
        placeholders = ', '.join(['%s'] * len(taluka_ids))
        cursor.execute(f"""
            SELECT
                ta.id,
                ta.name,
                COALESCE(t.name, 'Taluka') AS scope_name
            FROM taluka_admins ta
            LEFT JOIN talukas t ON ta.taluka_id = t.id
            WHERE ta.id IN ({placeholders})
        """, tuple(taluka_ids))
        talukas = {row['id']: row for row in (cursor.fetchall() or [])}

    if district_ids:
        placeholders = ', '.join(['%s'] * len(district_ids))
        cursor.execute(f"""
            SELECT
                da.id,
                da.name,
                COALESCE(d.name, 'District') AS scope_name
            FROM district_admins da
            LEFT JOIN districts d ON da.district_id = d.id
            WHERE da.id IN ({placeholders})
        """, tuple(district_ids))
        districts = {row['id']: row for row in (cursor.fetchall() or [])}

    return workers, talukas, districts


def format_request_rows(cursor, request_rows):
    workers, talukas, districts = _request_actor_details(cursor, request_rows)

    formatted_rows = []
    for row in request_rows or []:
        requester_role = row.get('requester_role')
        requester_id = row.get('requester_id')
        requester_name = role_display_name(requester_role)
        requester_scope_name = ''

        if requester_role == 'worker' and requester_id in workers:
            requester_name = workers[requester_id].get('name') or requester_name
            requester_scope_name = workers[requester_id].get('scope_name') or ''
        elif requester_role == 'admin' and requester_id in talukas:
            requester_name = talukas[requester_id].get('name') or requester_name
            requester_scope_name = talukas[requester_id].get('scope_name') or ''
        elif requester_role == 'district_admin' and requester_id in districts:
            requester_name = districts[requester_id].get('name') or requester_name
            requester_scope_name = districts[requester_id].get('scope_name') or ''

        formatted_rows.append({
            **row,
            'status': normalize_request_status(row.get('status')),
            'status_label': request_status_label(row.get('status')),
            'status_class': request_status_class(row.get('status')),
            'priority_label': (row.get('priority') or 'normal').replace('_', ' ').title(),
            'created_at_text': format_datetime_text(row.get('created_at')),
            'updated_at_text': format_datetime_text(row.get('updated_at')),
            'fulfilled_at_text': format_datetime_text(row.get('fulfilled_at'), fallback='Pending'),
            'requester_role_label': role_display_name(requester_role),
            'target_role_label': role_display_name(row.get('target_role')),
            'requester_name': requester_name,
            'requester_scope_name': requester_scope_name,
            'quantity_pending': max((row.get('quantity_requested') or 0) - (row.get('quantity_fulfilled') or 0), 0),
        })
    return formatted_rows


def fetch_request_rows(cursor, where_sql='', params=(), limit=30):
    ensure_equipment_schema(cursor)
    limit_value = max(int(limit), 1)
    query = f"""
        SELECT
            id,
            requester_role,
            requester_id,
            requester_scope_role,
            requester_scope_id,
            target_role,
            target_scope_role,
            target_scope_id,
            item_key,
            item_name,
            category_name,
            quantity_requested,
            quantity_fulfilled,
            priority,
            reason,
            notes,
            status,
            created_at,
            updated_at,
            fulfilled_at
        FROM equipment_requests
        {where_sql}
        ORDER BY created_at DESC
        LIMIT {limit_value}
    """
    cursor.execute(query, tuple(params))
    return format_request_rows(cursor, cursor.fetchall() or [])


def fetch_transaction_rows(cursor, where_sql='', params=(), limit=40):
    ensure_equipment_schema(cursor)
    limit_value = max(int(limit), 1)
    query = f"""
        SELECT
            id,
            transaction_type,
            actor_role,
            actor_id,
            from_scope_role,
            from_scope_id,
            to_scope_role,
            to_scope_id,
            item_key,
            item_name,
            category_name,
            quantity,
            notes,
            related_request_id,
            created_at
        FROM equipment_transactions
        {where_sql}
        ORDER BY created_at DESC
        LIMIT {limit_value}
    """
    cursor.execute(query, tuple(params))

    rows = []
    for row in cursor.fetchall() or []:
        rows.append({
            **row,
            'transaction_label': (row.get('transaction_type') or 'transaction').replace('_', ' ').title(),
            'actor_role_label': role_display_name(row.get('actor_role')),
            'from_scope_label': scope_role_label(row.get('from_scope_role')),
            'to_scope_label': scope_role_label(row.get('to_scope_role')),
            'created_at_text': format_datetime_text(row.get('created_at')),
        })
    return rows
