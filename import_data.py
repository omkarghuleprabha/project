import pandas as pd
import mysql.connector
import sys

# =========================
# 1. FILE PATH
# =========================
csv_path = r"D:\INTERSHIP\mini project\smart-garbage-management\villageofSpecificState20191224033059092.csv"

# =========================
# 2. LOAD CSV (ENCODING FIX)
# =========================
print("📂 Loading CSV...")

try:
    df = pd.read_csv(csv_path, encoding="utf-8", low_memory=False)
except UnicodeDecodeError:
    print("⚠️ UTF-8 failed, trying latin1 encoding...")
    df = pd.read_csv(csv_path, encoding="latin1", low_memory=False)

# Clean column names
df.columns = [c.strip().lower() for c in df.columns]

print("✅ Total Records:", len(df))

# =========================
# 3. DATABASE CONNECTION
# =========================
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="1234",
    database="smart_garbage_db"
)
cursor = conn.cursor()

print("🔗 Connected to DB")

# =========================
# 4. DELETE OLD DATA (RESET DB)
# =========================
print("🗑️ Clearing old data...")

cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
cursor.execute("TRUNCATE TABLE villages;")
cursor.execute("TRUNCATE TABLE talukas;")
cursor.execute("TRUNCATE TABLE districts;")
cursor.execute("TRUNCATE TABLE states;")
cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

conn.commit()

# =========================
# 5. INSERT STATE
# =========================
cursor.execute("INSERT INTO states (id, name) VALUES (%s, %s)", (1, "Maharashtra"))
state_id = 1

# =========================
# 6. CACHE SYSTEM (FAST IMPORT)
# =========================
district_cache = {}
taluka_cache = {}

count = 0

print("🚀 Importing LGD data...")

# =========================
# 7. MAIN LOOP
# =========================
for _, row in df.iterrows():

    try:
        district = str(row["district name"]).strip()
        taluka = str(row["sub-district name (in english)"]).strip()
        village = str(row["village name"]).strip()
    except:
        continue

    if not district or not taluka or not village:
        continue

    # =========================
    # DISTRICT INSERT
    # =========================
    if district not in district_cache:
        cursor.execute(
            "INSERT INTO districts (name, state_id) VALUES (%s, %s)",
            (district, state_id)
        )
        district_cache[district] = cursor.lastrowid

    district_id = district_cache[district]

    # =========================
    # TALUKA INSERT
    # =========================
    t_key = (taluka, district_id)

    if t_key not in taluka_cache:
        cursor.execute(
            "INSERT INTO talukas (name, district_id) VALUES (%s, %s)",
            (taluka, district_id)
        )
        taluka_cache[t_key] = cursor.lastrowid

    taluka_id = taluka_cache[t_key]

    # =========================
    # VILLAGE INSERT
    # =========================
    cursor.execute(
        "INSERT INTO villages (name, taluka_id) VALUES (%s, %s)",
        (village, taluka_id)
    )

    count += 1

    if count % 1000 == 0:
        print(f"✅ Imported {count} villages...")

# =========================
# 8. FINAL COMMIT
# =========================
conn.commit()

print("\n🎉 IMPORT COMPLETED SUCCESSFULLY!")
print(f"Total Villages Imported: {count}")

cursor.close()
conn.close()

print("🔌 Database connection closed")