SELECT 
    d_inst.sector_nombre AS government_sector,
    -- Ajuste Senior: Usamos '{:,}' que es el formateador nativo de enteros para miles
    FORMAT('{:,}', APPROX_COUNT_DISTINCT(d_prog.producto_proyecto)) AS estimated_project_count,
    -- Redondeamos el dinero a 2 decimales fijos
    ROUND(SUM(f.monto) / 1000000000.0, 2) AS expenditure_billions
FROM fact_presupuesto f
JOIN dim_institucion d_inst ON f.sk_institucion_id = d_inst.sk_institucion_id
JOIN dim_programatica d_prog ON f.sk_programatica_id = d_prog.sk_programatica_id
WHERE f.anio = 2024 
  AND f.fase = 'devengado'
  AND d_inst.sector_nombre IS NOT NULL 
  AND TRIM(d_inst.sector_nombre) != ''
GROUP BY 1 
ORDER BY 3 DESC 
LIMIT 5;