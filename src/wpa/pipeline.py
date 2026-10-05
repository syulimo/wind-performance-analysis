"""Wind fleet performance analysis: data quality, reference power curves, loss attribution, issue detection.

Run from the repo root:  python -m src.wpa.pipeline
Outputs land in outputs/ (CSV tables plus results.json for the dashboard).
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "sql"
OUT = ROOT / "outputs"

RHO_REF = 1.225          # kg/m3, IEC 61400-12-1 reference density
R_DRY = 287.05           # J/(kg K)
G = 9.80665
BIN_WIDTH = 0.5          # m/s
CUT_IN, CUT_OUT = 3.5, 25.0
TRAIN_YEAR = 2014        # reference curves fitted on 2014 only; 2015 is out-of-sample
LOSS_STATES = ("downtime", "curtailment", "icing_suspected", "underperformance")

# Classification thresholds (documented in README; tested in tests/)
DOWNTIME_POWER_FRAC = 0.01     # power at or below 1 percent of rated while wind supports production
DOWNTIME_MIN_EXPECTED = 50.0   # kW
UNDERPERF_RATIO = 0.85
ICING_RATIO = 0.75
ICING_TEMP_C = 2.0
MIN_EXPECTED_FOR_RATIO = 100.0 # kW
MIN_RUN = 3                    # underperformance and icing must persist 30 min (3 records) to count


def run_sql(con: duckdb.DuckDBPyConnection, name: str) -> None:
    con.execute((SQL / name).read_text())


def air_density(pres_pa: pd.Series, temp_c: pd.Series, hub_height_m: float) -> pd.Series:
    """Hub-height air density from surface pressure (barometric correction) and outdoor temperature (SCADA Ot_avg)."""
    t_k = temp_c + 273.15
    p_hub = pres_pa * np.exp(-G * hub_height_m / (R_DRY * t_k))
    return p_hub / (R_DRY * t_k)


def normalize_wind_speed(ws: pd.Series, rho: pd.Series) -> pd.Series:
    """IEC 61400-12-1 density normalization for pitch-regulated turbines."""
    return ws * (rho / RHO_REF) ** (1.0 / 3.0)


def fit_reference_curve(ws_norm: pd.Series, power: pd.Series, rated_kw: float) -> pd.DataFrame:
    """Binned median power curve with one outlier-rejection pass; monotone non-decreasing; capped at rated."""
    df = pd.DataFrame({"ws": ws_norm, "p": power}).dropna()
    df["bin"] = (df["ws"] / BIN_WIDTH).round() * BIN_WIDTH
    med = df.groupby("bin")["p"].median()
    df = df[df["p"] >= 0.8 * df["bin"].map(med)]          # drop derated / stopped points from the fit
    curve = df.groupby("bin").agg(p_kw=("p", "median"), n=("p", "size")).reset_index()
    curve = curve[curve["n"] >= 20]
    curve["p_kw"] = np.minimum(np.maximum.accumulate(curve["p_kw"].to_numpy()), rated_kw)
    return curve.rename(columns={"bin": "ws_ms"})


def expected_power(ws_norm: pd.Series, curve: pd.DataFrame) -> np.ndarray:
    exp = np.interp(ws_norm.to_numpy(), curve["ws_ms"], curve["p_kw"], left=0.0, right=curve["p_kw"].iloc[-1])
    exp[(ws_norm < CUT_IN).to_numpy() | (ws_norm > CUT_OUT).to_numpy()] = 0.0
    return exp


def persistent(flag: pd.Series, turbine: pd.Series, min_run: int = MIN_RUN) -> pd.Series:
    """Keep a flag only where it belongs to a run of at least min_run consecutive records for the same turbine.
    Assumes rows are sorted by turbine then time. Isolated 10-minute dips are power-curve scatter, not issues."""
    run_id = (flag != flag.groupby(turbine).shift(fill_value=False)).groupby(turbine).cumsum()
    run_len = flag.groupby([turbine, run_id]).transform("size")
    return flag & (run_len >= min_run)


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Assign one operating state and a loss (kW) to every 10-minute record. Priority order is explicit."""
    df = df.copy()
    dq = df[["dq_missing", "dq_frozen_ws", "dq_out_of_range", "dq_power_without_wind"]].any(axis=1)
    p = df["power_kw"].clip(lower=0)
    e = df["expected_kw"]
    windy = (~dq) & df["ws_norm"].between(CUT_IN, CUT_OUT) & (e > 0)

    downtime = windy & (df["power_kw"] <= DOWNTIME_POWER_FRAC * df["rated_kw"]) & (e >= DOWNTIME_MIN_EXPECTED)
    curtail = windy & ~downtime & (df["plant_curtail_kwh"] > 0) & (p < 0.9 * e)
    icing = windy & ~downtime & ~curtail & (df["temp_c"] <= ICING_TEMP_C) & (e >= MIN_EXPECTED_FOR_RATIO) & (p < ICING_RATIO * e)
    icing = persistent(icing, df["turbine"])
    under = windy & ~downtime & ~curtail & ~icing & (e >= MIN_EXPECTED_FOR_RATIO) & (p < UNDERPERF_RATIO * e)
    under = persistent(under, df["turbine"])

    state = np.select([dq, downtime, curtail, icing, under], ["unassessable", *LOSS_STATES], default="normal")
    df["state"] = state
    df["windy"] = windy
    df["loss_kw"] = np.where(np.isin(state, LOSS_STATES), (e - p).clip(lower=0), 0.0)
    df.loc[dq, "expected_kw"] = np.nan
    return df


def detect_issues(kpi: pd.DataFrame, gap_pts: float = 2.0, months: int = 3, yaw_deg: float = 4.0) -> pd.DataFrame:
    """Long-term issue detection, two-sided: performance index more than gap_pts away from the fleet median
    for at least `months` consecutive months (a sustained gain is as suspicious as a loss: it often means a
    sensor change), plus static yaw misalignment above yaw_deg."""
    kpi = kpi.sort_values(["turbine", "month"]).reset_index(drop=True)
    kpi["fleet_median_pi"] = kpi.groupby("month")["performance_index"].transform("median")
    kpi["pi_gap_pts"] = 100 * (kpi["performance_index"] - kpi["fleet_median_pi"])
    sign = np.sign(kpi["pi_gap_pts"]).where(kpi["pi_gap_pts"].abs() > gap_pts, 0)
    run_id = (sign != sign.groupby(kpi["turbine"]).shift()).groupby(kpi["turbine"]).cumsum()
    run_len = sign.groupby([kpi["turbine"], run_id]).transform("size")
    kpi["pi_gap_persistent"] = (sign != 0) & (run_len >= months)
    kpi["pi_gap_direction"] = np.where(kpi["pi_gap_persistent"], np.where(sign > 0, "above_fleet", "below_fleet"), "")
    kpi["yaw_flag"] = kpi["median_yaw_misalign_deg"].abs() > yaw_deg
    return kpi


def main() -> dict:
    OUT.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET file_search_path='{ROOT}'")
    run_sql(con, "01_staging.sql")
    run_sql(con, "02_dq_flags.sql")

    df = con.execute("""
        SELECT d.*, a.hub_height_m, e.pres_pa, COALESCE(p.curtailment_kwh, 0) AS plant_curtail_kwh
        FROM scada_dq d
        JOIN assets a USING (turbine)
        LEFT JOIN era5 e ON e.ts_hour = date_trunc('hour', d.ts_utc)
        LEFT JOIN plant p ON p.ts_utc = d.ts_utc
        ORDER BY turbine, ts_utc""").df()

    df["rho"] = air_density(df["pres_pa"], df["temp_c"], float(df["hub_height_m"].iloc[0]))
    df["ws_norm"] = normalize_wind_speed(df["ws_ms"], df["rho"].fillna(RHO_REF))

    dq_any = df[["dq_missing", "dq_frozen_ws", "dq_out_of_range", "dq_power_without_wind"]].any(axis=1)
    train = (df["ts_utc"].dt.year == TRAIN_YEAR) & ~dq_any & (df["power_kw"] > 0) \
        & (df["temp_c"] > ICING_TEMP_C + 1) & (df["plant_curtail_kwh"] == 0)

    curves, parts = {}, []
    for t, g in df.groupby("turbine"):
        rated = float(g["rated_kw"].iloc[0])
        tm = train.loc[g.index]
        curves[t] = fit_reference_curve(g.loc[tm, "ws_norm"], g.loc[tm, "power_kw"], rated)
        g = g.assign(expected_kw=expected_power(g["ws_norm"], curves[t]))
        parts.append(g)
    df = classify(pd.concat(parts))

    con.register("classified_df", df)
    con.execute("CREATE OR REPLACE TABLE classified AS SELECT * FROM classified_df")
    run_sql(con, "03_kpis.sql")
    run_sql(con, "04_sensor_checks.sql")

    dq = con.execute("SELECT * FROM dq_summary").df()
    kpi = detect_issues(con.execute("SELECT * FROM kpi_monthly").df())
    losses = con.execute("SELECT * FROM loss_by_driver").df()
    recon = con.execute("SELECT * FROM meter_reconciliation").df()
    yearly = con.execute("""
        SELECT turbine, year(ts_utc) AS year,
               SUM(COALESCE(power_kw,0))/6000 AS actual_mwh,
               SUM(CASE WHEN state='downtime' THEN loss_kw ELSE 0 END)/6000 AS downtime_mwh,
               SUM(CASE WHEN state='curtailment' THEN loss_kw ELSE 0 END)/6000 AS curtailment_mwh,
               SUM(CASE WHEN state='icing_suspected' THEN loss_kw ELSE 0 END)/6000 AS icing_mwh,
               SUM(CASE WHEN state='underperformance' THEN loss_kw ELSE 0 END)/6000 AS underperf_mwh,
               SUM(CASE WHEN windy AND state IN ('normal','underperformance','icing_suspected') THEN power_kw END)
                 / SUM(CASE WHEN windy AND state IN ('normal','underperformance','icing_suspected') THEN expected_kw END) AS performance_index,
               1 - SUM((state='downtime')::INT)::DOUBLE / SUM(windy::INT) AS time_availability,
               SUM(COALESCE(power_kw,0)) / (MAX(rated_kw)*COUNT(*)) AS capacity_factor
        FROM classified GROUP BY 1,2 ORDER BY 1,2""").df()
    anemo = con.execute("SELECT * FROM anemometer_ratio_quarterly").df()
    loss_monthly = con.execute("SELECT * FROM loss_monthly").df()
    states = con.execute("SELECT state, COUNT(*) AS records FROM classified GROUP BY 1 ORDER BY 2 DESC").df()

    for name, frame in {"dq_summary": dq, "kpi_monthly": kpi, "loss_by_driver": losses,
                        "meter_reconciliation": recon, "kpi_yearly": yearly, "state_counts": states,
                        "anemometer_ratio_quarterly": anemo, "loss_monthly": loss_monthly}.items():
        frame.to_csv(OUT / f"{name}.csv", index=False)
    curve_rows = [c.assign(turbine=t) for t, c in curves.items()]
    pd.concat(curve_rows).to_csv(OUT / "reference_power_curves.csv", index=False)

    # Scatter sample for the dashboard (every 40th record, 2015 only, assessable)
    s = df[(df["ts_utc"].dt.year == 2015) & (df["state"] != "unassessable")].iloc[::40]
    scatter = s[["turbine", "ws_norm", "power_kw", "state"]].round(2)

    results = {
        "dq_summary": dq.to_dict("records"),
        "kpi_monthly": kpi.assign(month=kpi["month"].dt.strftime("%Y-%m")).round(4).to_dict("records"),
        "loss_by_driver": losses.round(2).to_dict("records"),
        "meter_reconciliation": recon.assign(month=recon["month"].dt.strftime("%Y-%m")).round(4).to_dict("records"),
        "kpi_yearly": yearly.round(4).to_dict("records"),
        "state_counts": states.to_dict("records"),
        "anemometer": anemo.assign(quarter=anemo["quarter"].dt.strftime("%Y-Q") + anemo["quarter"].dt.quarter.astype(str)).round(4).to_dict("records"),
        "curves": {t: c.round(2).to_dict("records") for t, c in curves.items()},
        "scatter": scatter.to_dict("records"),
    }
    (OUT / "results.json").write_text(json.dumps(results, default=str))
    return results


if __name__ == "__main__":
    r = main()
    print(pd.DataFrame(r["dq_summary"]).to_string(index=False))
    print(pd.DataFrame(r["kpi_yearly"]).to_string(index=False))
    print(pd.DataFrame(r["loss_by_driver"]).to_string(index=False))
