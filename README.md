# Peru Budget Lakehouse 🇵🇪

Proyecto de ingeniería de datos enfocado en la arquitectura de **Local Lakehouse** para el análisis del presupuesto público peruano (MEF).

## 🚀 Arquitectura Técnica
- **Motor de Procesamiento:** Polars (Rust-based DataFrame library)
- **Motor de Consultas:** DuckDB (In-process OLAP database)
- **Gestión de Entorno:** `uv`
- **Formato de Datos:** Apache Parquet (Columnar storage)

## 📂 Capas de Datos (Medallion Architecture)
1. **Bronze:** Datos crudos (CSV/Excel) del MEF (~8.5 GB).
2. **Silver:** Limpieza, tipado y normalización en Parquet.
3. **Gold:** Modelo Estrella para Business Intelligence.