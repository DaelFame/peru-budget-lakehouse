"""
demo_stats.py

Prints the figures the README quotes for the committed demo layer, so every
number can be re-derived from the repository without the full dataset.

Usage:
    uv run python scripts/demo_stats.py
"""

from pathlib import Path

import duckdb

DEMO_DIR = Path("data/00_demo")
TABLES = [
    "fact_presupuesto",
    "dim_economica",
    "dim_financiamiento",
    "dim_geografia",
    "dim_institucion",
    "dim_programatica",
]


def main() -> None:
    con = duckdb.connect()
    print("=== DEMO ROW COUNTS ===")
    for table in TABLES:
        path = DEMO_DIR / f"{table}.parquet"
        if not path.exists():
            print(f"{table}: missing")
            continue
        count = con.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]
        print(f"{table:<22} {count:>10,}")

    fact = DEMO_DIR / "fact_presupuesto.parquet"
    if not fact.exists():
        return

    print("\n=== YEAR RANGE ===")
    print(con.execute(f"SELECT min(anio), max(anio) FROM read_parquet('{fact}')").fetchone())

    print("\n=== EXECUTION RATE (devengado / pim) ===")
    rows = con.execute(
        f"""
        SELECT anio,
               sum(CASE WHEN fase = 'pim' THEN monto ELSE 0 END) AS pim,
               sum(CASE WHEN fase = 'devengado' THEN monto ELSE 0 END) AS devengado
        FROM read_parquet('{fact}')
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    total_pim = sum(row[1] for row in rows)
    total_dev = sum(row[2] for row in rows)
    for anio, pim, dev in rows:
        rate = 100.0 * dev / pim if pim else float("nan")
        print(f"{anio}: PIM {pim / 1e9:>10,.2f}bn  devengado {dev / 1e9:>10,.2f}bn  rate {rate:>7.2f}%")
    if total_pim:
        print(f"all : PIM {total_pim / 1e9:>10,.2f}bn  devengado {total_dev / 1e9:>10,.2f}bn  "
              f"rate {100.0 * total_dev / total_pim:>7.2f}%")

    geo = DEMO_DIR / "dim_geografia.parquet"
    if geo.exists():
        print("\n=== PIM SHARE BY EXECUTING-UNIT DEPARTMENT (top 5) ===")
        shares = con.execute(
            f"""
            WITH pim AS (
                SELECT sk_geografia_id, sum(monto) AS monto
                FROM read_parquet('{fact}') WHERE fase = 'pim' GROUP BY 1
            ),
            total AS (SELECT sum(monto) AS monto FROM pim)
            SELECT g.departamento_ejecutora_nombre,
                   sum(p.monto) / 1e9 AS bn,
                   100.0 * sum(p.monto) / (SELECT monto FROM total) AS share_pct
            FROM pim p
            JOIN read_parquet('{geo}') g USING (sk_geografia_id)
            GROUP BY 1
            ORDER BY 2 DESC LIMIT 5
            """
        ).fetchall()
        for name, bn, share in shares:
            print(f"{name:<12} {bn:>8,.2f}bn  {share:>6.2f}%")

    con.close()


if __name__ == "__main__":
    main()
