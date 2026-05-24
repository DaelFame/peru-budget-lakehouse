import os
import multiprocessing
from pathlib import Path
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

# ==========================================
# DYNAMIC HARDWARE DETECTOR (SENIOR LEVEL)
# ==========================================
def get_optimal_memory_limit() -> str:
    """
    Detecta la RAM total del sistema y asigna el 80% para evitar colapsar el OS.
    Falla de forma segura a 4GB si no puede leer el hardware.
    """
    try:
        # Lee la RAM física real directo del sistema operativo (Linux/Mac)
        total_bytes = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
        total_gb = total_bytes / (1024 ** 3)
        # Reservamos el 80% para el procesamiento de datos (mínimo 1GB)
        optimal_gb = max(1, int(total_gb * 0.8)) 
        return f"{optimal_gb}GB"
    except (ValueError, AttributeError):
        return "4GB"

# 2. Environment and Hardware Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Piloto Automático: Si no está en .env, usa TODOS los núcleos de la máquina
MAX_THREADS = int(os.getenv("MAX_THREADS", multiprocessing.cpu_count()))

# Piloto Automático: Si no está en .env, calcula dinámicamente la memoria ideal (80%)
MEMORY_LIMIT = os.getenv("MEMORY_LIMIT", get_optimal_memory_limit())

# 3. Base Directory Setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR_PATH", "./data")

# 4. Medallion Architecture Layers
BRONZE_DIR = DATA_DIR / "01_bronze"
SILVER_DIR = DATA_DIR / "02_silver"
GOLD_DIR = DATA_DIR / "03_gold"

# 5. Specific File Path Mappings
DICTIONARY_PATH = DATA_DIR / "Diccionario_gastos.csv"
FINAL_SILVER_PATH = SILVER_DIR / "mef_final_silver.parquet"
INTERMEDIATE_SILVER_PATH = SILVER_DIR / "mef_consolidated_silver.parquet"

# Temporary Processing Directories
TMP_CONSOLIDATED_DIR = SILVER_DIR / "00_tmp_consolidated"
TMP_UNPIVOT_DIR = SILVER_DIR / "00_tmp_unpivot"

# Gold Layer Star Schema Paths
GOLD_FACT_PATH = GOLD_DIR / "fact_presupuesto.parquet"
GOLD_DIM_GEO_PATH = GOLD_DIR / "dim_geografia.parquet"
GOLD_DIM_INST_PATH = GOLD_DIR / "dim_institucion.parquet"
GOLD_DIM_PROG_PATH = GOLD_DIR / "dim_programatica.parquet"
GOLD_DIM_ECON_PATH = GOLD_DIR / "dim_economica.parquet"
GOLD_DIM_FIN_PATH = GOLD_DIR / "dim_financiamiento.parquet"

# 6. Automated Directory Validation
for directory in [BRONZE_DIR, SILVER_DIR, GOLD_DIR, TMP_CONSOLIDATED_DIR, TMP_UNPIVOT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)