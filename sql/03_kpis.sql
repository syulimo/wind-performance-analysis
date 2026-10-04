-- KPIs on the classified table written by src/wpa/pipeline.py (one row per turbine per 10 minutes).
CREATE OR REPLACE VIEW kpi_monthly AS
SELECT turbine,
       date_trunc('month', ts_utc)                                                  AS month,
       SUM(COALESCE(power_kw, 0)) / 6.0                                             AS actual_kwh,
       SUM(COALESCE(expected_kw, 0)) / 6.0                                          AS expected_kwh,
       SUM(COALESCE(power_kw, 0)) / (MAX(rated_kw) * COUNT(*))                      AS capacity_factor,
       1 - SUM((state = 'downtime')::INT)::DOUBLE / NULLIF(SUM(windy::INT), 0)      AS time_availability,
       1 - SUM(CASE WHEN state = 'downtime' THEN loss_kw ELSE 0 END)
           / NULLIF(SUM(CASE WHEN windy THEN expected_kw ELSE 0 END), 0)            AS energy_availability,
       SUM(CASE WHEN windy AND state IN ('normal','underperformance','icing_suspected') THEN power_kw END)
         / NULLIF(SUM(CASE WHEN windy AND state IN ('normal','underperformance','icing_suspected') THEN expected_kw END), 0)
                                                                                    AS performance_index,
       median(CASE WHEN state = 'normal' AND ws_ms BETWEEN 5 AND 11 THEN rel_dir_deg END) AS median_yaw_misalign_deg
FROM classified GROUP BY 1, 2 ORDER BY 1, 2;

CREATE OR REPLACE VIEW loss_by_driver AS
SELECT turbine, state AS driver, SUM(loss_kw) / 6.0 / 1000 AS lost_mwh, COUNT(*) AS records
FROM classified
WHERE state IN ('downtime','curtailment','icing_suspected','underperformance')
GROUP BY 1, 2 ORDER BY lost_mwh DESC;

-- Traceability: SCADA energy vs revenue meter, and our downtime estimate vs the operator's own unavailability counter.
CREATE OR REPLACE VIEW meter_reconciliation AS
WITH s AS (SELECT date_trunc('month', ts_utc) AS month,
                  SUM(COALESCE(power_kw, 0)) / 6.0 AS scada_kwh,
                  SUM(CASE WHEN state = 'downtime' THEN loss_kw ELSE 0 END) / 6.0 AS est_downtime_kwh
           FROM classified GROUP BY 1),
     m AS (SELECT date_trunc('month', ts_utc) AS month, SUM(net_energy_kwh) AS meter_kwh,
                  SUM(availability_kwh) AS operator_unavail_kwh, SUM(curtailment_kwh) AS operator_curtail_kwh
           FROM plant GROUP BY 1)
SELECT month, scada_kwh, meter_kwh, meter_kwh / scada_kwh AS meter_to_scada,
       est_downtime_kwh, operator_unavail_kwh, operator_curtail_kwh
FROM s JOIN m USING (month) ORDER BY month;

-- Monthly lost energy by turbine and driver (feeds the asset P&L and variance workbook).
CREATE OR REPLACE VIEW loss_monthly AS
SELECT turbine, date_trunc('month', ts_utc) AS month,
       SUM(COALESCE(power_kw, 0)) / 6000                                             AS actual_mwh,
       SUM(COALESCE(expected_kw, 0)) / 6000                                          AS potential_mwh,
       SUM(CASE WHEN state = 'downtime'         THEN loss_kw ELSE 0 END) / 6000      AS downtime_mwh,
       SUM(CASE WHEN state = 'underperformance' THEN loss_kw ELSE 0 END) / 6000      AS underperf_mwh,
       SUM(CASE WHEN state = 'icing_suspected'  THEN loss_kw ELSE 0 END) / 6000      AS icing_mwh,
       SUM(CASE WHEN state = 'curtailment'      THEN loss_kw ELSE 0 END) / 6000      AS curtailment_mwh
FROM classified GROUP BY 1, 2 ORDER BY 1, 2;
