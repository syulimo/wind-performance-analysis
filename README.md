# Wind fleet performance analysis: lost energy attribution and long-term issue detection

**Live dashboard:** https://syulimo.github.io/wind-performance-analysis/

A reproducible performance review of a real operating wind farm: data quality controls in SQL, density-normalized
reference power curves, a lost-energy breakdown by driver for every 10-minute record, and a monthly issue detector that
flags turbines drifting away from the fleet. Output is a single-file dashboard for an Asset Operations review meeting.

**Data:** ENGIE La Haute Borne open data (4 x Senvion MM82, 8.2 MW, France), 10-minute SCADA for 2014 to 2015
(420,480 turbine records), ERA5 reanalysis surface pressure, and the plant-level series distributed with
[NREL OpenOA](https://github.com/NREL/OpenOA). Licence Ouverte 2.0.

## Results

| Driver | Lost energy (MWh, 2014 to 2015) |
|---|---|
| Downtime | 280.9 |
| Underperformance (30 min or longer) | 168.0 |
| Suspected icing | 10.4 |
| Curtailment | 4.4 |
| **Total** | **463.7** (1.8 percent of potential; 24,630 MWh produced) |

* **R80790 is the priority asset.** Highest downtime loss (105.7 MWh) and its underperformance loss rose from 20.4 MWh
  (2014) to 39.1 MWh (2015). Reference curves are fitted on 2014 only, so 2015 is out of sample. Its performance index
  was 2.1 and 2.9 points below the fleet median in September and December 2015. Lowest time-based availability in the
  fleet (98.1 percent in 2014, 98.0 percent in 2015), with dips to 88.1 percent (June 2014) and 89.7 percent (February 2015).
* **R80711 ran 2.0 to 3.1 points above the fleet median for five consecutive months (April to August 2015).** The
  detector is two-sided because a sustained gain is often a sensor change. The anemometer check shows no step in that
  window (wind speed ratio to fleet 1.04 in Q2 and Q3 2015, inside its 2014 range of 1.04 to 1.05), so the cause is
  open. Next check: directional and wake-sector comparison.
* **Negative results, reported:** no static yaw misalignment above 4 degrees on any turbine in any month; curtailment
  and suspected icing are small.
* **Data quality:** 2,603 of 420,480 records (0.62 percent) excluded, each traceable to one rule. R80721 carries most
  of it (1,209 missing, 34 out of range).
* **Traceability:** the pipeline's downtime estimate (281 MWh) is within 9 percent of the operator's unavailability
  counter (308 MWh).

## Method

1. **Staging (`sql/01_staging.sql`).** Typed, UTC-aligned SCADA; plant meter; ERA5 pressure (DuckDB).
2. **Data quality controls (`sql/02_dq_flags.sql`).** One boolean column per rule: missing values, frozen wind sensor
   (identical value for 1 hour or more), out of range (wind speed, power above 105 percent of rated, temperature), and
   power reported without wind.
3. **Air density and normalization (`src/wpa/pipeline.py`).** Hub-height density from ERA5 surface pressure with a
   barometric correction and nacelle temperature; wind speed normalized per IEC 61400-12-1.
4. **Reference power curves.** Per turbine, fitted on 2014 clean records only (no DQ flag, producing, above 3 C,
   no curtailment): 0.5 m/s binned median with one outlier-rejection pass, forced monotone and capped at rated.
5. **State classification, in priority order:** unassessable (any DQ flag), downtime (power at or below 1 percent
   of rated while expected power is 50 kW or more), curtailment (plant curtailment signal), suspected icing (3 C or
   colder and below 75 percent of expected), underperformance (below 85 percent of expected), normal. Icing and
   underperformance must persist for 3 consecutive records (30 minutes); isolated 10-minute dips are curve scatter.
   Loss is expected minus actual power for loss states and zero otherwise.
6. **KPIs (`sql/03_kpis.sql`).** Monthly actual and expected energy, capacity factor, time-based and energy-based
   availability, performance index, median yaw misalignment; loss by driver; meter reconciliation.
7. **Long-term issue detection.** Performance index more than 2 points from the fleet median for 3 or more
   consecutive months (either direction), static yaw misalignment above 4 degrees, and an anemometer drift check
   (`sql/04_sensor_checks.sql`: each turbine's wind speed against the fleet median at the same timestamp).

## Limitations

* The plant meter, availability and curtailment series are the OpenOA example plant-level data; the meter equals
  0.98 of SCADA energy in almost every month, so the reconciliation tests the code path, not an independent meter.
* No manufacturer power curve or alarm logs are public for this site, so the reference is empirical and root causes
  stop at the signal level (what and where), not the component level.
* The 85 percent and 75 percent thresholds are conventions; changing them moves MWh between underperformance and normal.

## Run

```bash
pip install -r requirements.txt
bash scripts/get_data.sh
python -m src.wpa.pipeline          # writes outputs/*.csv and outputs/results.json
python -m src.wpa.build_dashboard   # writes outputs/dashboard.html (self-contained, works offline)
pytest -q                           # 11 tests: physics, curve fitting, classification, loss identity, SQL rules
```

Chart.js 4.4.1 (MIT) is vendored in `vendor/` and inlined into the dashboard.
