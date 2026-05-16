import time
import re
import gc
from pathlib import Path
import polars as pl
import polars.selectors as cs

BRONZE_DIR = Path("../data/01_bronze")
TMP_DIR = Path("../data/00_tmp")
SILVER_DIR = Path("../data/02_silver")

TMP_DIR.mkdir(parents=True, exist_ok=True)
SILVER_DIR.mkdir(parents=True, exist_ok=True)

# 1. Cargar el esquema seguro
print("📖 Leyendo diccionario de variables...")
df_dict = pl.read_csv("../data/Diccionario_gastos.csv")
columnas_texto = df_dict.filter(pl.col("TIPO_DATO").str.strip_chars() == "Carácter").select("VARIABLE").to_series().to_list()
codigos_a_texto = {col: pl.String for col in columnas_texto}

# 2. Caracteres del Hash Hexadecimal para dividir el trabajo
caracteres_hash = [str(i) for i in range(10)] + ["a", "b", "c", "d", "e", "f"]

print(f"🚀 Iniciando procesamiento por partición de Hash (16 lotes)...")
global_start = time.time()

for idx, char in enumerate(caracteres_hash):
    print(f"📦 [{idx+1}/16] Procesando lote de llaves que inician con: '{char}'...")
    
    # Escaneo limpio en cada iteración
    lazy_mef = pl.scan_csv(
        BRONZE_DIR / "*.csv", separator=",", infer_schema_length=10000,
        encoding="utf8", ignore_errors=True, schema_overrides=codigos_a_texto
    )
    
    # Forzar nombres a minúsculas
    columnas_raw = lazy_mef.collect_schema().names()
    lazy_mef = lazy_mef.rename({col: col.lower() for col in columnas_raw})
    
    # Filtrar el chunk ANTES de hacer transformaciones pesadas
    lazy_chunk = lazy_mef.filter(pl.col("key_value").str.starts_with(char))
    
    # Paso 1: Sanitización de textos dentro del chunk
    lazy_limpio = lazy_chunk.with_columns(
        cs.string()
        .str.strip_chars()
        .str.to_lowercase()
        .str.replace_all("á", "a").str.replace_all("é", "e")
        .str.replace_all("í", "i").str.replace_all("ó", "o")
        .str.replace_all("ú", "u")
    )
    
    # Paso 2: Consolidación (Group By) a nivel de mini-lote
    columnas_actuales = lazy_limpio.collect_schema().names()
    metricas_financieras = [col for col in columnas_actuales if re.search(r'_\d{4}$', col)]
    descriptivas = [col for col in columnas_actuales if col not in metricas_financieras and col != "key_value"]
    
    lazy_consolidado = lazy_limpio.group_by("key_value").agg(
        *[pl.col(c).first() for c in descriptivas],
        *[pl.col(c).sum() for c in metricas_financieras]
    )
    
    # Materializar lote temporal
    df_chunk_resultado = lazy_consolidado.collect()
    df_chunk_resultado.write_parquet(TMP_DIR / f"part_{char}.parquet")
    
    # Liberar memoria explícitamente
    del df_chunk_resultado
    gc.collect()

print("🔀 Unificando las 16 particiones consolidadas...")
# Escaneamos los parquets temporales ya reducidos sin duplicados
lazy_unificado = pl.scan_parquet(TMP_DIR / "part_*.parquet")

# Guardamos el archivo final consolidado de la capa Silver
lazy_unificado.sink_parquet(SILVER_DIR / "mef_consolidado_silver.parquet")

print(f"✅ Capa Silver consolidada con éxito en {round((time.time() - global_start)/60, 2)} minutos.")