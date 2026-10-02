-- Staging: typed, UTC-aligned 10-minute SCADA, plant meter, and ERA5 surface pressure.
-- Source: ENGIE La Haute Borne open data (redistributed in NREL OpenOA examples), Licence Ouverte 2.0.
CREATE OR REPLACE TABLE scada AS
SELECT
    Wind_turbine_name                                   AS turbine,
    timezone('UTC', CAST(Date_time AS TIMESTAMPTZ))     AS ts_utc,
    Ba_avg AS pitch_deg,
    P_avg  AS power_kw,
    Ws_avg AS ws_ms,
    Va_avg AS rel_dir_deg,      -- wind direction relative to nacelle: yaw misalignment proxy
    Ot_avg AS temp_c,
    Ya_avg AS nacelle_dir_deg,
    Wa_avg AS wind_dir_deg
FROM read_csv_auto('data/la-haute-borne-data-2014-2015.csv');

CREATE OR REPLACE TABLE assets AS
SELECT Wind_turbine_name AS turbine, Rated_power AS rated_kw, Hub_height_m AS hub_height_m,
       Rotor_diameter_m AS rotor_diameter_m, Manufacturer || ' ' || Model AS model
FROM read_csv_auto('data/la-haute-borne_asset_table.csv');

CREATE OR REPLACE TABLE plant AS
SELECT timezone('UTC', CAST(time_utc AS TIMESTAMPTZ)) AS ts_utc,
       net_energy_kwh, availability_kwh, curtailment_kwh
FROM read_csv_auto('data/plant_data.csv');

CREATE OR REPLACE TABLE era5 AS
SELECT CAST(datetime AS TIMESTAMP) AS ts_hour, surf_pres AS pres_pa
FROM read_csv_auto('data/era5_wind_la_haute_borne.csv')
WHERE CAST(datetime AS TIMESTAMP) BETWEEN TIMESTAMP '2013-12-31' AND TIMESTAMP '2016-01-02';
