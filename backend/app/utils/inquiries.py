def ensure_inquiries_table(cursor):
    cursor.execute("SHOW TABLES LIKE 'inquiries'")
    if cursor.fetchone():
        return

    cursor.execute(
        """
        CREATE TABLE inquiries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(120) NOT NULL,
            mobile_number VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_inquiries_created_at (created_at)
        )
        """
    )


def create_inquiry(cursor, full_name, mobile_number, message):
    ensure_inquiries_table(cursor)
    cursor.execute(
        """
        INSERT INTO inquiries (full_name, mobile_number, message)
        VALUES (%s, %s, %s)
        """,
        (full_name, mobile_number, message),
    )
    return cursor.lastrowid


def fetch_inquiries(cursor, limit=None):
    ensure_inquiries_table(cursor)

    query = """
        SELECT
            id,
            full_name,
            mobile_number,
            message,
            created_at
        FROM inquiries
        ORDER BY created_at DESC, id DESC
    """

    if limit is not None:
        query += f"\n        LIMIT {max(int(limit), 0)}"

    cursor.execute(query)
    return cursor.fetchall() or []
