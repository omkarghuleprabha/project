import pandas as pd
import mysql.connector
import os
import sys

# 1. AUTO-LOCATE THE CSV FILE
# This looks for 'villages.csv' in the same folder as this script
base_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(base_dir, "villages.csv")

if not os.path.exists(csv_path):
    print(f"❌ Error: Could not find '{csv_path}'")
    print("Ensure 'villages.csv' is in the same folder as this script.")
    sys.exit()

# 2. LOAD DATA
print("📂 Loading CSV data...")
df = pd.read_csv(csv_path)
df = df.dropna(subset=['Village Name', 'Taluka', 'District'])

# 3. DATABASE CONNECTION
try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="smart_garbage_db"
    )
    cursor = conn.cursor(dictionary=True)
    print("🔗 Connected to smart_garbage_db")

    # 4. CLEAN RESET (Optional - Remove if you want to keep old data)
    print("🗑️  Cleaning old location data...")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    cursor.execute("TRUNCATE TABLE villages;")
    cursor.execute("TRUNCATE TABLE talukas;")
    cursor.execute("TRUNCATE TABLE districts;")
    cursor.execute("TRUNCATE TABLE states;")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

    # 5. INITIALIZE STATE
    cursor.execute("INSERT INTO states (id, name) VALUES (1, 'Maharashtra')")
    state_id = 1

    # 6. IMPORT LOGIC WITH CACHING
    districts_cache = {}
    talukas_cache = {}
    village_count = 0

    print("🚀 Starting Import of 9,441 records...")

    for _, row in df.iterrows():
        d_name = str(row['District']).strip()
        t_name = str(row['Taluka']).strip()
        v_name = str(row['Village Name']).strip()

        # Handle District
        if d_name not in districts_cache:
            cursor.execute("INSERT INTO districts (name, state_id) VALUES (%s, %s)", (d_name, state_id))
            dist_id = cursor.lastrowid
            districts_cache[d_name] = dist_id
        else:
            dist_id = districts_cache[d_name]

        # Handle Taluka
        t_key = (t_name, dist_id)
        if t_key not in talukas_cache:
            cursor.execute("INSERT INTO talukas (name, district_id) VALUES (%s, %s)", (t_name, dist_id))
            tal_id = cursor.lastrowid
            talukas_cache[t_key] = tal_id
        else:
            tal_id = talukas_cache[t_key]

        # Handle Village
        cursor.execute("INSERT INTO villages (name, taluka_id) VALUES (%s, %s)", (v_name, tal_id))
        
        village_count += 1
        if village_count % 1000 == 0:
            print(f"✅ {village_count} villages imported...")

    conn.commit()
    print(f"\n✨ DONE! Total Villages Imported: {village_count}")

except mysql.connector.Error as err:
    print(f"❌ Database Error: {err}")
finally:
    if 'conn' in locals() and conn.is_connected():
        cursor.close()
        conn.close()
        print("🔌 Database connection closed.")