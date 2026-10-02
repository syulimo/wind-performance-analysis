-- Sensor drift check: each turbine's nacelle wind speed relative to the fleet median at the same timestamp.
-- A step change in this ratio points to an anemometer or transfer-function change rather than a production change.
CREATE OR REPLACE VIEW anemometer_ratio_quarterly AS
WITH fleet AS (
    SELECT ts_utc, median(ws_ms) AS fleet_ws
    FROM scada_dq
    WHERE NOT (dq_missing OR dq_frozen_ws OR dq_out_of_range) AND ws_ms > 3
    GROUP BY 1 HAVING COUNT(*) = 4
)
SELECT date_trunc('quarter', s.ts_utc) AS quarter, s.turbine, AVG(s.ws_ms / f.fleet_ws) AS ws_ratio_to_fleet
FROM scada_dq s JOIN fleet f USING (ts_utc)
GROUP BY 1, 2 ORDER BY 1, 2;
