SELECT 
    d_geo.departamento_ejecutora_nombre AS department,
    SUM(f.monto) / 1000000000 AS billion_soles
FROM fact_presupuesto f
JOIN dim_geografia d_geo ON f.sk_geografia_id = d_geo.sk_geografia_id
WHERE f.ano_eje = 2024 
  AND f.fase = 'devengado'
  AND d_geo.departamento_ejecutora_nombre IS NOT NULL 
  AND TRIM(d_geo.departamento_ejecutora_nombre) != ''
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5;
