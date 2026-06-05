import duckdb
import pandas as pd
from pathlib import Path

FACT_PATH = "data/03_gold/fact_presupuesto.parquet"
OUTPUT_PATH = "data/00_demo/fact_presupuesto_demo.parquet"

# objetivo técnico realista
TARGET_TOTAL_ROWS = 450_000

YEARS = [2022, 2023, 2024, 2025]

con = duckdb.connect()

# 1. cargar dataset filtrado (sin 2026)
df = con.execute(f"""
    SELECT *
    FROM read_parquet('{FACT_PATH}')
    WHERE ano_eje IN (2022, 2023, 2024, 2025)
""").df()

total = len(df)

print(f"Base dataset (2022–2025): {total:,} filas")

# 2. sampling estratificado por año
parts = []

for year in YEARS:
    df_year = df[df["ano_eje"] == year]

    # proporción del año en el dataset
    ratio = len(df_year) / total

    # asignación proporcional del sample
    n = int(TARGET_TOTAL_ROWS * ratio)

    # seguridad: no exceder tamaño real
    n = min(n, len(df_year))

    df_sample = df_year.sample(n=n, random_state=42)

    parts.append(df_sample)

# 3. merge final
df_demo = pd.concat(parts)

# 4. shuffle final (evita orden temporal artificial)
df_demo = df_demo.sample(frac=1, random_state=42).reset_index(drop=True)

print(f"Demo final: {len(df_demo):,} filas")

# 5. export
Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
df_demo.to_parquet(OUTPUT_PATH, index=False)

print(f"Guardado en: {OUTPUT_PATH}")