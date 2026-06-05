"""
audit_schema.py

Read-only Star Schema Auditor.

Generates:
    schema_audit.md

Purpose:
    Quickly inventory the Gold Layer for semantic analysis.

Usage:
    python audit_schema.py
"""

from pathlib import Path
import duckdb

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GOLD_DIR = PROJECT_ROOT / "data" / "03_gold"

TABLES = {
    "fact_presupuesto": GOLD_DIR / "fact_presupuesto.parquet",
    "dim_geografia": GOLD_DIR / "dim_geografia.parquet",
    "dim_institucion": GOLD_DIR / "dim_institucion.parquet",
    "dim_programatica": GOLD_DIR / "dim_programatica.parquet",
    "dim_economica": GOLD_DIR / "dim_economica.parquet",
    "dim_financiamiento": GOLD_DIR / "dim_financiamiento.parquet",
}

OUTPUT_FILE = PROJECT_ROOT / "schema_audit.md"

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def safe_fetch_df(con, sql):
    try:
        return con.execute(sql).df()
    except Exception as e:
        return f"ERROR: {e}"


def markdown_table(df):
    try:
        return df.to_markdown(index=False)
    except Exception:
        return str(df)


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    con = duckdb.connect()

    lines = []

    lines.append("# Star Schema Audit")
    lines.append("")

    # --------------------------------------------------
    # FILE INVENTORY
    # --------------------------------------------------

    lines.append("## File Inventory")
    lines.append("")

    for table_name, path in TABLES.items():

        exists = path.exists()
        size_mb = round(path.stat().st_size / 1024 / 1024, 2) if exists else 0

        lines.append(
            f"- **{table_name}** | exists={exists} | size={size_mb} MB"
        )

    lines.append("")

    # --------------------------------------------------
    # TABLE ANALYSIS
    # --------------------------------------------------

    for table_name, path in TABLES.items():

        lines.append("---")
        lines.append("")
        lines.append(f"# {table_name}")
        lines.append("")

        if not path.exists():

            lines.append("FILE NOT FOUND")
            lines.append("")
            continue

        # Register View
        con.execute(
            f"""
            CREATE OR REPLACE VIEW {table_name}
            AS
            SELECT *
            FROM '{path}'
            """
        )

        # ------------------------------------------
        # Row Count
        # ------------------------------------------

        row_count = con.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]

        lines.append(f"## Row Count")
        lines.append("")
        lines.append(str(row_count))
        lines.append("")

        # ------------------------------------------
        # Schema
        # ------------------------------------------

        lines.append("## Schema")
        lines.append("")

        schema_df = safe_fetch_df(
            con,
            f"DESCRIBE {table_name}"
        )

        lines.append(markdown_table(schema_df))
        lines.append("")

        # ------------------------------------------
        # Cardinality
        # ------------------------------------------

        try:

            cols = con.execute(
                f"DESCRIBE {table_name}"
            ).df()["column_name"].tolist()

            sk_cols = [
                c for c in cols
                if c.startswith("sk_")
            ]

            if sk_cols:

                lines.append("## Surrogate Key Cardinality")
                lines.append("")

                for col in sk_cols:

                    distinct_count = con.execute(
                        f"""
                        SELECT COUNT(DISTINCT {col})
                        FROM {table_name}
                        """
                    ).fetchone()[0]

                    lines.append(
                        f"- {col}: {distinct_count:,}"
                    )

                lines.append("")

        except Exception as e:

            lines.append(f"Cardinality Error: {e}")
            lines.append("")

        # ------------------------------------------
        # Sample Data
        # ------------------------------------------

        lines.append("## Sample Rows")
        lines.append("")

        sample_df = safe_fetch_df(
            con,
            f"""
            SELECT *
            FROM {table_name}
            LIMIT 10
            """
        )

        lines.append(markdown_table(sample_df))
        lines.append("")

    # --------------------------------------------------
    # FACT RELATIONSHIPS
    # --------------------------------------------------

    lines.append("---")
    lines.append("")
    lines.append("# Fact Relationship Audit")
    lines.append("")

    fact_keys = [
        "sk_geografia_id",
        "sk_institucion_id",
        "sk_programatica_id",
        "sk_economica_id",
        "sk_financiamiento_id",
    ]

    for key in fact_keys:

        try:

            result = con.execute(
                f"""
                SELECT
                    COUNT(DISTINCT {key})
                FROM fact_presupuesto
                """
            ).fetchone()[0]

            lines.append(
                f"- {key}: {result:,} distinct values in fact table"
            )

        except Exception as e:

            lines.append(
                f"- {key}: ERROR -> {e}"
            )

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    con.close()

    print()
    print("Audit complete")
    print(f"Output: {OUTPUT_FILE}")
    print()


if __name__ == "__main__":
    main()