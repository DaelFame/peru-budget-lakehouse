# Peru Budget Lakehouse 🇵🇪 🏦
> **A High-Performance Local Data Lakehouse processing 47M+ financial records and S/. 8.4 Trillion under strict hardware constraints (4 Cores / 4GB RAM).**

[![Engine](https://img.shields.io/badge/Engine-Polars%20%7C%20DuckDB-blue?style=flat-square)](#)
[![Format](https://img.shields.io/badge/Storage-Apache%20Parquet%20%28ZSTD%29-green?style=flat-square)](#)
[![DX](https://img.shields.io/badge/Env%20Manager-uv%20%28Rust%29-orange?style=flat-square)](#)
[![Architecture](https://img.shields.io/badge/Architecture-Medallion%20%7C%20Kimball%20Star-purple?style=flat-square)](#)

---

## 💼 Why This Project Matters (Hiring Manager Executive Summary)

As a Data Engineer, writing code that runs on infinite cloud resources is easy. **Engineering under strict local hardware boundaries to maximize efficiency and minimize cost is where true seniority lies.**

This project processes **47,219,640 records** and reconciles **S/. 8,448,492,418,465.24 PEN (equivalent to $2.2+ Trillion USD)** of historical public expenditure from the Ministry of Economy and Finance of Peru (MEF). 

Faced with a massive **8.5 GB raw CSV file**, standard Pandas or PySpark pipelines would immediately crash due to Out-Of-Memory (OOM) errors on typical development hardware. This architecture was built using **Polars (Rust engine)** and **DuckDB**, demonstrating how to achieve **sub-second analytical query performance** on a standard 4-Core CPU / 4GB RAM local setup—representing a **$0 infrastructure spend** for massive-scale analytics.

---

## 🏗️ System Architecture & Data Flow

The pipeline follows a modern **Medallion Architecture** coupled with **Kimball Dimensional Modeling** at the presentation layer, optimized with columnar physical storage.

```
[ Bronze Layer (8.5 GB Raw CSV) ]
               │
               ▼  (ETL Phase 1: 16-Batch Hexadecimal Hash-Chunking & Text Sanitization)
[ Intermediate Consolidated Silver ]
               │
               ▼  (ETL Phase 2: Iterative Dynamic Unpivot / Melt per Fiscal Metric)
[ Silver Layer (3.2 GB Normalized Parquet) ]
               │
               ▼  (ELT Phase 3: Pure Streaming & Cryptographic u64 Surrogate Hashing)
[ Gold Layer (Star Schema: 5 Dimensions + 1 Fact Table) ]
               │
      ┌────────┴────────┐
      ▼ (Governance)    ▼ (Query Execution)
[ 0.46s QA Audit ]   [ DuckDB Virtual SQL Mapping ] ──► [ C-Level OLAP Reports in 0.37s ]
  • Volumetrics        • Zero-Copy Reads
  • Amount Sync        • Pushdown Projection
```

### 🏎️ Architectural Design Decisions
* **Polars LazyFrame & Streaming Engine:** Leveraged instead of Pandas (too slow/RAM intensive) or Spark (requires JVM overhead and complex local clusters). Polars utilizes native multi-threading in Rust and out-of-core streaming.
* **DuckDB OLAP Engine:** Utilized as an embedded in-memory database to query Parquet files directly, performing vectorized query execution in sub-second times.
* **Apache Parquet (ZSTD Compression):** Used as the primary columnar storage format across Silver and Gold layers to minimize disk footprint and optimize read projection.

---

## 🛠️ The Engineering Challenges & Solutions

### 1. The Out-Of-Memory (OOM) Challenge
* **The Problem:** The raw CSV file in the Bronze layer is **8.5 GB**. Standard CSV parsers attempt to load the entire file into memory, causing instant crashes on a 4GB RAM machine.
* **The Solution:** Implemented a **16-batch Hexadecimal Hash-Chunking Strategy** in [`01_silver_ingestion.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/01_silver_ingestion.py). By scanning the CSV lazily, we filter the dataset incrementally using the starting character of the record's hash key (`0-9` and `a-f`). This processes the giant file in 16 highly predictable, isolated batches, guaranteeing it never exceeds the RAM limit.

### 2. Eliminating Semantic Drift & Duplicate Entanglements
* **The Problem:** Government employees frequently modify text columns from year to year (adding/removing accents, changing word spacing), creating artificial duplicates. Dropping duplicates with standard functions (`drop_duplicates`) would discard actual financial records, corrupting the financial ledger.
* **The Solution:** Developed a robust two-step cleaning system:
  1. **Orthographic Sanitization:** Lowercases, strips white spaces, and strips Spanish accents (`á, é, í, ó, ú`) dynamically from all string columns.
  2. **Historical Consolidation:** Grouped by the business ledger key (`key_value`), selected the first occurrence for descriptive columns (`.first()`), and summed all financial columns (`.sum()`), consolidating the timeline of money without losing a single cent.

### 3. Iterative Dynamic Column Transposition (Unpivot)
* **The Problem:** The source file is "wide", having columns for each phase and year (e.g., `pim_2022`, `devengado_2022`, `girado_2022`, etc.). Performing an unpivot (melt) of 35 columns across millions of rows causes exponential RAM expansion.
* **The Solution:** Processed the unpivot **column-by-column iteratively**. For each financial column, we scan the consolidated dataset, filter out zero/null records to discard sparse data, map the metric name and fiscal year into separate rows, calculate the transaction hash, and stream it to a temporary Parquet file. These are then joined back via Polars' streaming engine into the final Silver dataset.

### 4. High-Performance Surrogate Keys Generation
* **The Problem:** Performing joins in analytical OLAP queries using long concatenated string keys (e.g., `nivel_gobierno_sector_pliego...`) increases memory footprints and degrades query performance.
* **The Solution:** Designed a hashing pipeline in [`02_star_schema.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/02_star_schema.py) to generate numeric surrogate keys. By concatenating dimension keys and applying a numeric `.hash()` function, we produce ultra-compact 64-bit unsigned integers (`u64`). These represent a massive improvement in storage and join throughput compared to standard string joins or UUIDs.

---

## 📊 Performance Benchmarks & Quality Gates

### Automated QA Audit Gatekeeper (Runs in 0.46 seconds)
Data integrity is protected by automated assertions in [`03_data_quality_audit.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/03_data_quality_audit.py):
* **Financial Reconciliation:** Performs a total sum comparison of all financial stages between the Silver layer and the Gold Fact Table. Any difference greater than **S/. 0.01** (to tolerate Float64 precision handling) raises a critical execution error and halts deployment.
* **Volumetric Audit:** Validates that row counts strictly match the expected drops resulting from null-filtering rules.

### OLAP Query Performance (Runs in 0.37 seconds)
Using DuckDB to map virtual views over physical Parquet files in [`04_analytical_reports.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/04_analytical_reports.py), we achieve the following times over 47M+ rows:

| Report / Analytical Query | Execution Time | Memory Overhead | Business Metric Evaluated |
| :--- | :--- | :--- | :--- |
| **Top 5 Spending Departments (2024)** | **~0.15s** | Zero-Copy (Mapped Views) | Real Expenditure (*Devengado*) |
| **Historical PIM Budget Trend** | **~0.08s** | Zero-Copy (Mapped Views) | Annual trend evolution |
| **Sector Project Density vs Budget** | **~0.14s** | Zero-Copy (Mapped Views) | Estimated unique project count vs sum |

---

## ⚡ Developer Experience & Quickstart

This project uses **`uv`**, the high-performance Python package manager written in Rust, ensuring environment setup is done in seconds.

### 1. Clone & Initialize Environment
```bash
git clone https://github.com/your-username/peru-budget-lakehouse.git
cd peru-budget-lakehouse

# Install 'uv' if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | bash # Or standard install methods

# Create virtual environment and install dependencies in sub-second times
uv venv
source .venv/bin/activate
uv pip install -r pyproject.toml
```

### 2. Execution Pipeline
Run the pipelines sequentially:
```bash
# Phase 1: Bronze to Silver Ingestion & Unpivoting
python src/01_silver_ingestion.py

# Phase 2: Silver to Gold Dimensional Modeling (Star Schema)
python src/02_star_schema.py

# Phase 3: Automated Data Quality Audit Gatekeeper
python src/03_data_quality_audit.py

# Phase 4: DuckDB Analytical Engine Execution
python src/04_analytical_reports.py
```

---

<br>

# Peru Budget Lakehouse 🇵🇪 🏦 (Versión en Español)
> **Data Lakehouse local de alto rendimiento que procesa más de 47M de registros financieros y S/. 8.4 Billones bajo severas restricciones de hardware (4 Cores / 4GB RAM).**

---

## 💼 Por Qué Importa Este Proyecto (Resumen Ejecutivo para Líderes Técnicos)

Escribir código de datos que corre en infraestructuras de nube infinitas es fácil. **Hacer ingeniería de datos eficiente bajo severas limitaciones de hardware locales para maximizar el rendimiento y reducir costos a cero es donde radica la verdadera experiencia.**

Este proyecto procesa **47,219,640 registros** y concilia **S/. 8,448,492,418,465.24 PEN (más de $2.2 Billones de USD)** de historial de gastos públicos del Ministerio de Economía y Finanzas de Perú (MEF).

Al enfrentarse a un archivo **CSV original de 8.5 GB**, cualquier pipeline convencional en Pandas o PySpark colapsaría debido a errores de memoria (OOM) en una computadora promedio. Esta arquitectura, construida con **Polars (motor Rust)** y **DuckDB**, demuestra cómo lograr **rendimiento analítico de subsegundos** en un hardware estándar de 4 núcleos y 4 GB de RAM, representando un **gasto de infraestructura de $0**.

---

## 🏗️ Arquitectura del Sistema y Flujo de Datos

El pipeline sigue una **Arquitectura Medallón** combinada con **Modelado Dimensional Kimball (Esquema Estrella)** en la capa de presentación, optimizada mediante almacenamiento físico columnar en Parquet.

```
[ Capa Bronze (8.5 GB CSV Crudo) ]
               │
               ▼  (ETL Fase 1: Hash-Chunking Hexadecimal de 16 Lotes y Sanitización)
[ Silver Intermedio Consolidado ]
               │
               ▼  (ETL Fase 2: Unpivot Dinámico e Iterativo por Métrica Financiera)
[ Capa Silver (3.2 GB Parquet Normalizado) ]
               │
               ▼  (ELT Fase 3: Streaming y Hasheo u64 de Llaves Subrogadas)
[ Capa Gold (Esquema Estrella: 5 Dimensiones + 1 Tabla de Hechos de 47M+ filas) ]
               │
      ┌────────┴────────┐
      ▼ (Gobernanza)    ▼ (Motor de Consultas)
[ Auditoría QA - 0.46s ]   [ Mapeo de Vistas Virtuales DuckDB ] ──► [ Reportes OLAP en 0.37s ]
  • Volumetría              • Lecturas Zero-Copy
  • Sincronía de Montos     • Pushdown de Proyecciones
```

---

## 🛠️ Retos de Ingeniería y Soluciones

### 1. El Desafío de Out-Of-Memory (OOM)
* **El Problema:** El archivo CSV crudo en Bronze pesa **8.5 GB**. Intentar cargarlo de forma directa en un sistema de 4GB de RAM resulta en un colapso del sistema.
* **La Solución:** Con una estrategia de **Hash-Chunking Hexadecimal de 16 lotes** en [`01_silver_ingestion.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/01_silver_ingestion.py). Polars escanea el CSV perezosamente (`scan_csv`) y procesa de manera incremental filtrando los registros según el primer caracter de su clave hash (`0-9` y `a-f`). Esto fragmenta el archivo gigante en 16 bloques aislados y sumamente predecibles, evitando exceder los límites de RAM.

### 2. Eliminación de Duplicados Falsos sin Pérdida de Dinero
* **El Problema:** Variaciones tipográficas de los funcionarios año tras año (tildes, espacios) crean registros que parecen duplicados en el texto pero representan transacciones financieras reales del SIAF. Eliminar filas con un simple `drop_duplicates` destruiría dinero real y descuadraría el balance general.
* **La Solución:** Diseño de un proceso de dos etapas:
  1. **Sanitización Ortográfica:** Normalización dinámica a minúsculas, remoción de espacios extremos y remoción de tildes (`á, é, í, ó, ú`) en todas las columnas de texto.
  2. **Consolidación Histórica:** Agrupación por la clave única de negocio (`key_value`), conservando el primer valor de los textos (`.first()`) y sumando todas las fases financieras (`.sum()`), consolidando la línea de tiempo del dinero sin perder un solo centavo.

### 3. Transposición de Columnas (Unpivot) Iterativa de Alto Rendimiento
* **El Problema:** El dataset original posee columnas horizontales para cada año y fase (ej. `pim_2022`, `devengado_2022`). Realizar un unpivot simultáneo de 35 columnas genera una expansión exponencial de registros en memoria.
* **La Solución:** Se estructuró un procesamiento unpivot **columna por columna de forma iterativa**. Por cada métrica financiera, se escanea el archivo consolidado, se filtran registros en cero o nulos, se transforma el nombre de la columna y el año a filas, se genera su hash único y se escribe un archivo Parquet temporal comprimido con ZSTD. Finalmente, la API de streaming de Polars unifica todos los archivos temporales y escribe el archivo Silver definitivo.

### 4. Llaves Subrogadas Numéricas vs Joins de Texto
* **El Problema:** Realizar Joins en queries analíticas utilizando largas cadenas de texto concatenadas (ej. `departamento_provincia_distrito...`) consume demasiada memoria RAM y ralentiza las consultas de negocio.
* **La Solución:** Diseñado un pipeline en [`02_star_schema.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/02_star_schema.py) que concatena las combinaciones de llaves y les aplica un hasheo numérico `.hash()`, generando enteros sin signo de 64 bits (`u64`). Esto reduce el peso de las claves al mínimo y optimiza drásticamente el rendimiento de los joins en comparación con el uso de strings o UUIDs.

---

## 📊 Rendimiento y Auditoría de Datos

### Auditoría QA Automatizada (Ejecución en 0.46 segundos)
La integridad financiera está custodiada por controles de calidad estrictos en [`03_data_quality_audit.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/03_data_quality_audit.py):
* **Conciliación Financiera:** Suma total de todos los montos entre la capa Silver y la Tabla de Hechos de Gold. Cualquier desviación mayor a **S/. 0.01** (para tolerar precisión Float64) aborta inmediatamente la ejecución levantando un error crítico.
* **Consistencia Volumétrica:** Monitorea que la cantidad de registros inyectados en Gold corresponda estrictamente con las reglas de negocio de filtrado de ceros y nulos.

### Rendimiento OLAP (Ejecución en 0.37 segundos)
Utilizando DuckDB para mapear vistas virtuales sobre los Parquet estructurados en [`04_analytical_reports.py`](file:///home/jcc/Proyectos/peru-budget-lakehouse/src/04_analytical_reports.py), se obtienen los siguientes tiempos sobre los 47M+ de registros:

| Reporte Analítico / Consulta SQL | Tiempo de Ejecución | Uso de Memoria Adicional | Métrica de Negocio Evaluada |
| :--- | :--- | :--- | :--- |
| **Top 5 Departamentos con Mayor Gasto (2024)** | **~0.15s** | Zero-Copy (Vistas Mapeadas) | Gasto Real (*Devengado*) |
| **Evolución Histórica del Presupuesto PIM** | **~0.08s** | Zero-Copy (Vistas Mapeadas) | Tendencia anual |
| **Densidad de Proyectos por Sector vs Presupuesto** | **~0.14s** | Zero-Copy (Vistas Mapeadas) | Conteo aproximado de proyectos únicos vs suma total |