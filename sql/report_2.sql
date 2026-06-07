WITH yearly_pim AS (
    SELECT 
        anio AS fiscal_year, 
        SUM(monto) / 1000000000.0 AS total_pim_billions
    FROM fact_presupuesto
    WHERE fase = 'pim'
    GROUP BY 1
)
SELECT 
    fiscal_year,
    ROUND(total_pim_billions, 2) AS total_pim_billions,
    
    -- Si es nulo (primer año), mostramos 0.00
    COALESCE(
        ROUND(total_pim_billions - LAG(total_pim_billions) OVER(ORDER BY fiscal_year), 2),
        0.00
    ) AS net_variance_billions,
    
    -- Formateamos el porcentaje interanual de manera limpia
    CONCAT(
        COALESCE(
            ROUND(((total_pim_billions - LAG(total_pim_billions) OVER(ORDER BY fiscal_year)) / 
            LAG(total_pim_billions) OVER(ORDER BY fiscal_year)) * 100, 2),
            0.00
        ),
        ' %'
    ) AS yoy_growth_percentage
FROM yearly_pim
ORDER BY fiscal_year ASC;