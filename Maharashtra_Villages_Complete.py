import pandas as pd
import os

print("Loading Maharashtra village dataset...")

# 👇 Put correct CSV file name here
file_path = "villageofSpecificState20191224033059092.csv"

if not os.path.exists(file_path):
    print("ERROR: CSV file not found!")
    print("👉 Please download dataset from Kaggle and place it in this folder")
    exit()

df = pd.read_csv(file_path)

# Normalize columns
df.columns = [c.lower().strip() for c in df.columns]

print("Total villages loaded:", len(df))

# -------------------------
# FULL EXCEL FILE
# -------------------------
df.to_excel("Maharashtra_All_Villages.xlsx", index=False)

# -------------------------
# DISTRICT-WISE FILE
# -------------------------
with pd.ExcelWriter("Maharashtra_District_Wise.xlsx") as writer:
    for district in df["district_name"].unique():
        temp = df[df["district_name"] == district]
        sheet = str(district)[:31]
        temp.to_excel(writer, sheet_name=sheet, index=False)

print("DONE ✔ Excel files created successfully")