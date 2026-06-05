import polars as pl
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()
DATA_DIR = Path(os.getenv("DATA_DIR_PATH", "./data"))

def get_layer_stats(layer_name: str):
    """Audita una capa específica (Bronze, Silver o Gold)."""
    layer_dir = next(DATA_DIR.glob(f"*{layer_name}*"), None)
    if not layer_dir:
        return None
    
    total_size = sum(f.stat().st_size for f in layer_dir.rglob('*') if f.is_file()) / (1024**3)
    # Contar archivos parquet para saber la cantidad de particiones
    parquet_files = list(layer_dir.rglob("*.parquet"))
    return {"size_gb": total_size, "files": len(parquet_files)}

def audit_layers():
    print("=== TECHNICAL AUDIT: ARCHITECTURE MEDALLION ===")
    
    layers = ["01_bronze", "02_silver", "03_gold"]
    
    for layer in layers:
        stats = get_layer_stats(layer)
        if stats:
            print(f"[{layer.upper()}] Size: {stats['size_gb']:.2f} GB | Files: {stats['files']}")
        else:
            print(f"[{layer.upper()}] Not found.")

    # Auditoría específica de filas en la capa GOLD (Fact Table)
    gold_dir = next(DATA_DIR.glob("*gold*"), None)
    fact_table = gold_dir / "fact_presupuesto.parquet"
    if fact_table.exists():
        df = pl.scan_parquet(fact_table).collect()
        print(f"\n[GOLD DETAIL] Fact Table Rows: {df.shape[0]:,}")
    
    print("=== AUDIT COMPLETED ===")

if __name__ == "__main__":
    audit_layers()