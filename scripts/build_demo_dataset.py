"""
build_demo_dataset.py

Production-grade demo dataset builder for the Peru Budget Lakehouse.
Generates a ~450K row stratified sample of fact_presupuesto (years 2022-2025)
with strict validation gates, MD5 reproducibility signature, and schema preservation.

Usage:
    python scripts/build_demo_dataset.py

Output:
    data/00_demo/fact_presupuesto_demo.parquet
"""

import hashlib

import duckdb
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
FACT_PATH = Path("data/03_gold/fact_presupuesto.parquet")
OUTPUT_PATH = Path("data/00_demo/fact_presupuesto.parquet")
TARGET_TOTAL_ROWS = 450_000
RANDOM_STATE = 42
YEARS = [2022, 2023, 2024, 2025]

REQUIRED_COLUMNS = [
    "sk_geografia_id",
    "sk_institucion_id",
    "sk_programatica_id",
    "sk_economica_id",
    "sk_financiamiento_id",
    "anio",
    "fase",
    "monto",
]

# ---------------------------------------------------------------------------
# 1. LOAD
# ---------------------------------------------------------------------------
con = duckdb.connect()
df = con.execute(f"""
    SELECT *
    FROM read_parquet('{FACT_PATH}')
    WHERE anio IN ({','.join(map(str, YEARS))})
""").df()

total_before = len(df)
print(f"Gold dataset (2022–2025): {total_before:,} rows")

# ---------------------------------------------------------------------------
# 2. COMPUTE YEAR PROPORTIONS FROM FULL DATASET
# ---------------------------------------------------------------------------
year_counts = df["anio"].value_counts().sort_index()
total_count = year_counts.sum()

# ---------------------------------------------------------------------------
# 3. STRATIFIED SAMPLING (exact row count enforcement)
# ---------------------------------------------------------------------------
allocations = {}
remaining = TARGET_TOTAL_ROWS

for year in YEARS[:-1]:
    count = year_counts[year]
    proportion = count / total_count
    n = min(int(TARGET_TOTAL_ROWS * proportion), count)
    allocations[year] = n
    remaining -= n

# Last year gets whatever remains (ensures exact TARGET_TOTAL_ROWS)
allocations[YEARS[-1]] = min(remaining, year_counts[YEARS[-1]])
remaining_after = TARGET_TOTAL_ROWS - sum(allocations.values())

# Distribute any remaining slack to years with capacity
if remaining_after > 0:
    for year in YEARS:
        if remaining_after <= 0:
            break
        cap = year_counts[year] - allocations[year]
        add = min(remaining_after, cap)
        allocations[year] += add
        remaining_after -= add

# Safety: clamp any overflow back to zero
if remaining_after != 0:
    import sys
    print(f"WARNING: Could not allocate {remaining_after} rows exactly", file=sys.stderr)

parts = []
for year in YEARS:
    n = allocations[year]
    df_year = df[df["anio"] == year]
    df_sample = df_year.sample(n=n, random_state=RANDOM_STATE)
    parts.append(df_sample)

# ---------------------------------------------------------------------------
# 4. CONCATENATE + SHUFFLE
# ---------------------------------------------------------------------------
df_demo = pd.concat(parts, ignore_index=True)
df_demo = df_demo.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)

# ---------------------------------------------------------------------------
# 5. STRICT VALIDATION GATE
# ---------------------------------------------------------------------------
actual_rows = len(df_demo)
assert actual_rows == TARGET_TOTAL_ROWS, (
    f"Row count mismatch: expected {TARGET_TOTAL_ROWS}, got {actual_rows}"
)

nulls = {col: int(df_demo[col].isnull().sum()) for col in REQUIRED_COLUMNS}
for col, count in nulls.items():
    assert count == 0, f"Column '{col}' has {count} null values"

demo_year_counts = df_demo["anio"].value_counts().sort_index()
for year in YEARS:
    assert year in demo_year_counts.index, f"Year {year} is missing from demo dataset"
    assert demo_year_counts[year] > 0, f"Year {year} has 0 rows"

assert not df_demo.empty, "Dataset is empty"

# ---------------------------------------------------------------------------
# 6. COMPUTE SIGNATURE
# ---------------------------------------------------------------------------
signature_content = f"{len(df_demo)}-{df_demo['anio'].value_counts().sort_index().to_dict()}"
signature = hashlib.md5(signature_content.encode()).hexdigest()

# ---------------------------------------------------------------------------
# 7. EXPORT
# ---------------------------------------------------------------------------
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
df_demo.to_parquet(OUTPUT_PATH, index=False)

# ---------------------------------------------------------------------------
# 8. REPORT
# ---------------------------------------------------------------------------
monto_min = df_demo["monto"].min()
monto_max = df_demo["monto"].max()

year_distribution = demo_year_counts.to_dict()
year_total = sum(year_distribution.values())

print()
print("=== DATASET VALIDATION ===")
print(f"Rows: {actual_rows}")
print(f"Signature: {signature}")
print()
print("Year distribution:")
for y in YEARS:
    cnt = year_distribution.get(y, 0)
    pct = cnt / year_total * 100 if year_total else 0
    print(f"  {y}: {cnt:,} ({pct:.1f}%)")
print()
print("Null check:")
for col in REQUIRED_COLUMNS:
    print(f"  {col}: {nulls[col]}")
print()
print("monto range:")
print(f"  min: {monto_min}")
print(f"  max: {monto_max}")
print()
print(f"Saved to {OUTPUT_PATH}")

# ---------------------------------------------------------------------------
# 9. DEMO DIMENSIONS MIGRATION (MINI STAR SCHEMA)
# ---------------------------------------------------------------------------

DIM_TABLES = {
    "dim_geografia": "sk_geografia_id",
    "dim_institucion": "sk_institucion_id",
    "dim_programatica": "sk_programatica_id",
    "dim_economica": "sk_economica_id",
    "dim_financiamiento": "sk_financiamiento_id",
}

DIM_PATH_GOLD = Path("data/03_gold")
DIM_PATH_DEMO = Path("data/00_demo")

def build_demo_dimension(table_name, key_col):
    gold_path = DIM_PATH_GOLD / f"{table_name}.parquet"
    demo_path = DIM_PATH_DEMO / f"{table_name}.parquet"

    if not gold_path.exists():
        print(f"[WARN] Missing gold dimension: {table_name}")
        return

    print(f"Processing {table_name}...")

    dim = pd.read_parquet(gold_path)

    # Keep only keys that exist in fact demo (minimizes size + ensures consistency)
    valid_keys = set(df_demo[key_col].unique())
    dim_demo = dim[dim[key_col].isin(valid_keys)].copy()

    # Safety: remove duplicates if any
    dim_demo = dim_demo.drop_duplicates(subset=[key_col])

    demo_path.parent.mkdir(parents=True, exist_ok=True)
    dim_demo.to_parquet(demo_path, index=False)

    print(f"{table_name}: {len(dim):,} → {len(dim_demo):,} rows")


for table, key in DIM_TABLES.items():
    build_demo_dimension(table, key)