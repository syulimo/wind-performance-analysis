-- Data quality controls. Each rule is its own boolean column, so every excluded record is traceable to a rule.
CREATE OR REPLACE TABLE scada_dq AS
WITH changes AS (
    SELECT *,
        CASE WHEN ws_ms IS NOT DISTINCT FROM LAG(ws_ms) OVER w THEN 0 ELSE 1 END AS ws_changed
    FROM scada
    WINDOW w AS (PARTITION BY turbine ORDER BY ts_utc)
), runs AS (
    SELECT *, SUM(ws_changed) OVER (PARTITION BY turbine ORDER BY ts_utc) AS ws_run_id FROM changes
), run_len AS (
    SELECT *, COUNT(*) OVER (PARTITION BY turbine, ws_run_id) AS ws_run_len FROM runs
)
SELECT r.* EXCLUDE (ws_changed, ws_run_id),
    a.rated_kw,
    (r.power_kw IS NULL OR r.ws_ms IS NULL)                                     AS dq_missing,
    COALESCE(r.ws_ms > 0 AND r.ws_run_len >= 6, FALSE)                          AS dq_frozen_ws,   -- identical value for 1 h or more
    COALESCE(r.ws_ms < 0 OR r.ws_ms > 40 OR r.power_kw > 1.05 * a.rated_kw
             OR r.temp_c < -30 OR r.temp_c > 50, FALSE)                         AS dq_out_of_range,
    COALESCE(r.power_kw > 200 AND r.ws_ms < 2, FALSE)                           AS dq_power_without_wind
FROM run_len r JOIN assets a USING (turbine);

CREATE OR REPLACE VIEW dq_summary AS
SELECT turbine,
       COUNT(*)                                   AS records,
       SUM(dq_missing::INT)                       AS missing,
       SUM(dq_frozen_ws::INT)                     AS frozen_ws,
       SUM(dq_out_of_range::INT)                  AS out_of_range,
       SUM(dq_power_without_wind::INT)            AS power_without_wind,
       SUM((dq_missing OR dq_frozen_ws OR dq_out_of_range OR dq_power_without_wind)::INT) AS excluded
FROM scada_dq GROUP BY turbine ORDER BY turbine;
