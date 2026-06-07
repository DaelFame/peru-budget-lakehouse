SELECT 
    d_geo.departamento_ejecutora_nombre AS department,
    ROUND(SUM(f.monto) / 1000000000.0, 2) AS billion_soles,
    -- Redondeamos e inyectamos el sufijo porcentual
    CONCAT(
        ROUND((SUM(f.monto) / SUM(SUM(f.monto)) OVER()) * 100, 2), 
        ' %'
    ) AS percentage_of_national_total
FROM fact_presupuesto f
JOIN dim_geografia d_geo ON f.sk_geografia_id = d_geo.sk_geografia_id
WHERE f.anio = 2024 
  AND f.fase = 'devengado'
  AND d_geo.departamento_ejecutora_nombre IS NOT NULL 
  AND TRIM(d_geo.departamento_ejecutora_nombre) != ''
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5;