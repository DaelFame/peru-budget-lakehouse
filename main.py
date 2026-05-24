import subprocess
import sys
from prefect import flow, task

@task(name="Ingesta Capa Silver", retries=1, retry_delay_seconds=10)
def ejecutar_silver():
    print("[Prefect] Ejecutando 01_silver_ingestion.py...")
    resultado = subprocess.run([sys.executable, "src/01_silver_ingestion.py"])
    if resultado.returncode != 0:
        raise RuntimeError("Fallo en la Capa Silver")

@task(name="Modelo Dimensional Gold")
def ejecutar_gold():
    print("[Prefect] Ejecutando 02_star_schema.py...")
    resultado = subprocess.run([sys.executable, "src/02_star_schema.py"])
    if resultado.returncode != 0:
        raise RuntimeError("Fallo en la Capa Gold")

@task(name="Auditoría de Calidad (QA)")
def ejecutar_qa():
    print("[Prefect] Ejecutando 03_data_quality_audit.py...")
    resultado = subprocess.run([sys.executable, "src/03_data_quality_audit.py"])
    if resultado.returncode != 0:
        raise RuntimeError("Fallo en Auditoría QA")

@task(name="Reportes Analíticos DuckDB")
def ejecutar_reportes():
    print("[Prefect] Ejecutando 04_analytical_reports.py...")
    resultado = subprocess.run([sys.executable, "src/04_analytical_reports.py"])
    if resultado.returncode != 0:
        raise RuntimeError("Fallo en Reportes Analíticos")

@flow(name="Lakehouse-Pipeline-MEF", log_prints=True)
def pipeline_principal():
    print("Iniciando orquestación con Prefect...")
    # Ejecución secuencial del pipeline
    ejecutar_silver()
    ejecutar_gold()
    ejecutar_qa()
    ejecutar_reportes()
    print("✅ Pipeline finalizado con éxito.")

if __name__ == "__main__":
    pipeline_principal()