SELECT 
    d_inst.sector_nombre AS government_sector,
    -- Presupuesto total devengado en miles de millones
    ROUND(SUM(f.monto) / 1000000000.0, 2) AS total_devengado_billions,
    
    -- Cuánto de ese dinero se devengó específicamente en LIMA
    ROUND(SUM(CASE WHEN d_geo.departamento_ejecutora_nombre = 'LIMA' THEN f.monto ELSE 0 END) / 1000000000.0, 2) AS lima_devengado_billions,
    
    -- % de centralización en Lima (Índice de macrocefalia presupuestal)
    CONCAT(
        ROUND(
            (SUM(CASE WHEN d_geo.departamento_ejecutora_nombre = 'LIMA' THEN f.monto ELSE 0 END) / 
             SUM(f.monto)) * 100, 
            2
        ),
        ' %'
    ) AS lima_centralization_rate
FROM fact_presupuesto f
JOIN dim_institucion d_inst ON f.sk_institucion_id = d_inst.sk_institucion_id
JOIN dim_geografia d_geo ON f.sk_geografia_id = d_geo.sk_geografia_id
WHERE f.anio = 2024 
  AND f.fase = 'devengado'
  AND d_inst.sector_nombre IS NOT NULL 
  AND TRIM(d_inst.sector_nombre) != ''
GROUP BY 1
ORDER BY total_devengado_billions DESC
LIMIT 5;