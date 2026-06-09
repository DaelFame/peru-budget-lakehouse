import os
import multiprocessing
from pathlib import Path
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

# ==========================================
# DYNAMIC HARDWARE DETECTOR
# ==========================================
def get_optimal_memory_limit() -> str:
    try:
        total_bytes = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
        total_gb = total_bytes / (1024 ** 3)
        optimal_gb = max(1, int(total_gb * 0.8))
        return f"{optimal_gb}GB"
    except (ValueError, AttributeError):
        return "4GB"

# 2. Environment and Hardware Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
MAX_THREADS = int(os.getenv("MAX_THREADS", multiprocessing.cpu_count()))
MEMORY_LIMIT = os.getenv("MEMORY_LIMIT", get_optimal_memory_limit())

# 3. Base Directory Setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR_PATH", "./data")

# 4. Medallion Architecture Layers
BRONZE_DIR = DATA_DIR / "01_bronze"
SILVER_DIR = DATA_DIR / "02_silver"
GOLD_DIR   = DATA_DIR / "03_gold"

# 5. Specific File Path Mappings
DICTIONARY_PATH          = DATA_DIR  / "Diccionario_gastos.csv"
FINAL_SILVER_PATH        = SILVER_DIR / "step2_long.parquet"        # ← CAMBIADO
INTERMEDIATE_SILVER_PATH = SILVER_DIR / "mef_consolidated_silver.parquet"

# Temporary Processing Directories
TMP_CONSOLIDATED_DIR = SILVER_DIR / "00_tmp_consolidated"
TMP_UNPIVOT_DIR      = SILVER_DIR / "00_tmp_unpivot"

# =====================================================
# SMART DATA RESOLVER (PROD → DEMO → FAIL SAFE)
# =====================================================
def resolve_data_path(filename: str) -> Path:
    prod_path = GOLD_DIR / filename
    demo_path = DATA_DIR / "00_demo" / filename

    if prod_path.exists():
        return prod_path
    if demo_path.exists():
        return demo_path
    return prod_path

# =====================================================
# GOLD LAYER STAR SCHEMA PATHS (DYNAMIC)
# =====================================================
GOLD_FACT_PATH     = resolve_data_path("fact_presupuesto.parquet")
GOLD_DIM_GEO_PATH  = resolve_data_path("dim_geografia.parquet")
GOLD_DIM_INST_PATH = resolve_data_path("dim_institucion.parquet")
GOLD_DIM_PROG_PATH = resolve_data_path("dim_programatica.parquet")
GOLD_DIM_ECON_PATH = resolve_data_path("dim_economica.parquet")
GOLD_DIM_FIN_PATH  = resolve_data_path("dim_financiamiento.parquet")

# 6. Automated Directory Validation
for directory in [BRONZE_DIR, SILVER_DIR, GOLD_DIR, TMP_CONSOLIDATED_DIR, TMP_UNPIVOT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
