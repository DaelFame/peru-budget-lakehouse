SELECT 
    ano_eje AS fiscal_year, 
    SUM(monto) / 1000000000 AS total_pim_billions
FROM fact_presupuesto
WHERE fase = 'pim'
GROUP BY 1
ORDER BY 1 ASC;
