import duckdb
import numpy as np
import pandas as pd
import pytest

from src.wpa import pipeline as wp


def test_air_density_matches_standard_atmosphere():
    rho = wp.air_density(pd.Series([101325.0]), pd.Series([15.0]), hub_height_m=0.0)
    assert rho.iloc[0] == pytest.approx(1.225, abs=1e-3)


def test_density_normalization_is_identity_at_reference_density():
    ws = pd.Series([4.0, 8.0, 12.0])
    assert np.allclose(wp.normalize_wind_speed(ws, pd.Series([wp.RHO_REF] * 3)), ws)


def test_reference_curve_is_monotone_and_capped_at_rated():
    rng = np.random.default_rng(0)
    ws = pd.Series(rng.uniform(3, 18, 20000))
    p = pd.Series(np.clip(2050 * ((ws - 3) / 9) ** 3, 0, 2050) + rng.normal(0, 30, 20000))
    curve = wp.fit_reference_curve(ws, p, rated_kw=2050)
    assert np.all(np.diff(curve["p_kw"]) >= 0)
    assert curve["p_kw"].max() <= 2050


def _frame(power, expected, temp=10.0, curtail=0.0, dq=False):
    n = len(power)
    return pd.DataFrame({
        "turbine": ["T1"] * n,
        "power_kw": power, "expected_kw": expected, "ws_norm": [8.0] * n,
        "rated_kw": [2050.0] * n, "temp_c": [temp] * n, "plant_curtail_kwh": [curtail] * n,
        "dq_missing": [dq] * n, "dq_frozen_ws": [False] * n,
        "dq_out_of_range": [False] * n, "dq_power_without_wind": [False] * n,
    })


def test_downtime_and_loss():
    out = wp.classify(_frame([0.0, -5.0], [800.0, 800.0]))
    assert (out["state"] == "downtime").all()
    assert np.allclose(out["loss_kw"], 800.0)          # negative power clipped to 0 before loss


def test_isolated_dip_is_not_underperformance_but_persistent_dip_is():
    iso = wp.classify(_frame([800, 500, 800, 800], [800] * 4))
    assert (iso["state"] == "normal").all()
    run = wp.classify(_frame([500, 500, 500, 800], [800] * 4))
    assert list(run["state"]) == ["underperformance"] * 3 + ["normal"]


def test_curtailment_takes_priority_over_underperformance():
    out = wp.classify(_frame([400] * 3, [800] * 3, curtail=50.0))
    assert (out["state"] == "curtailment").all()


def test_cold_persistent_shortfall_is_icing():
    out = wp.classify(_frame([300] * 3, [800] * 3, temp=0.5))
    assert (out["state"] == "icing_suspected").all()


def test_dq_records_are_unassessable_and_carry_no_loss():
    out = wp.classify(_frame([0.0] * 3, [800] * 3, dq=True))
    assert (out["state"] == "unassessable").all()
    assert (out["loss_kw"] == 0).all() and out["expected_kw"].isna().all() and not out["windy"].any()


def test_loss_accounting_identity():
    rng = np.random.default_rng(1)
    exp = rng.uniform(100, 2000, 500)
    pw = exp * rng.choice([1.0, 0.95, 0.6, 0.0], 500)
    out = wp.classify(_frame(list(pw), list(exp)))
    loss_rows = out["state"].isin(wp.LOSS_STATES)
    assert (out["loss_kw"] >= 0).all()
    assert (out.loc[~loss_rows, "loss_kw"] == 0).all()
    np.testing.assert_allclose(out.loc[loss_rows, "loss_kw"] + out.loc[loss_rows, "power_kw"].clip(lower=0),
                               out.loc[loss_rows, "expected_kw"])


def test_detect_issues_flags_sustained_gap_in_both_directions():
    months = pd.date_range("2015-01-01", periods=6, freq="MS")
    rows = []
    for m_i, m in enumerate(months):
        rows += [{"turbine": "A", "month": m, "performance_index": 1.00, "median_yaw_misalign_deg": 0.0},
                 {"turbine": "B", "month": m, "performance_index": 1.00, "median_yaw_misalign_deg": 6.0},
                 {"turbine": "C", "month": m, "performance_index": 0.95 if m_i >= 2 else 1.0, "median_yaw_misalign_deg": 0.0}]
    k = wp.detect_issues(pd.DataFrame(rows))
    c = k[k["turbine"] == "C"]
    assert c["pi_gap_persistent"].sum() == 4 and set(c.loc[c["pi_gap_persistent"], "pi_gap_direction"]) == {"below_fleet"}
    assert k.loc[k["turbine"] == "B", "yaw_flag"].all()


def test_sql_frozen_sensor_rule():
    con = duckdb.connect()
    ts = pd.date_range("2015-01-01", periods=10, freq="10min")
    con.register("s", pd.DataFrame({"turbine": "T1", "ts_utc": ts, "pitch_deg": 0.0, "power_kw": 500.0,
                                    "ws_ms": [7.0] * 7 + [7.5, 8.0, 8.5], "rel_dir_deg": 0.0, "temp_c": 10.0,
                                    "nacelle_dir_deg": 0.0, "wind_dir_deg": 0.0}))
    con.execute("CREATE TABLE scada AS SELECT * FROM s")
    con.execute("CREATE TABLE assets AS SELECT 'T1' AS turbine, 2050.0 AS rated_kw")
    con.execute((wp.SQL / "02_dq_flags.sql").read_text())
    flags = con.execute("SELECT dq_frozen_ws FROM scada_dq ORDER BY ts_utc").fetchnumpy()["dq_frozen_ws"]
    assert flags.tolist() == [True] * 7 + [False] * 3
