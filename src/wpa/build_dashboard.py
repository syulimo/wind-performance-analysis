"""Build outputs/dashboard.html (single self-contained file) from outputs/results.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = json.loads((ROOT / "outputs" / "results.json").read_text())

losses = R["loss_by_driver"]
total_loss = sum(r["lost_mwh"] for r in losses)
actual = sum(r["actual_mwh"] for r in R["kpi_yearly"])
by_driver = {}
for r in losses:
    by_driver[r["driver"]] = by_driver.get(r["driver"], 0) + r["lost_mwh"]
recon = R["meter_reconciliation"]
est_dt = sum(r["est_downtime_kwh"] for r in recon) / 1000
op_dt = sum(r["operator_unavail_kwh"] for r in recon) / 1000
yr = {(r["turbine"], r["year"]): r for r in R["kpi_yearly"]}

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>La Haute Borne wind fleet: performance review 2014 to 2015</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@500;600&display=swap" rel="stylesheet">
<script>__CHARTJS__</script>
<style>
:root{--paper:#F4F6F5;--card:#FFFFFF;--ink:#1D2733;--steel:#5B6B7A;--rule:#D5DBDF;--blue:#2E6F95;
--down:#B5452F;--under:#E0A100;--ice:#7FB3C8;--curt:#8A7FB0;--ok:#4E8A5E;
box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#151B21;--card:#1D252D;--ink:#E6EBEF;--steel:#9AA9B6;--rule:#33404B;--blue:#6FA8CC}}
:root[data-theme="dark"]{--paper:#151B21;--card:#1D252D;--ink:#E6EBEF;--steel:#9AA9B6;--rule:#33404B;--blue:#6FA8CC}
*{box-sizing:border-box}html{scroll-padding-top:env(safe-area-inset-top,0px)}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 Barlow,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1080px;margin:0 auto;padding:40px 20px 64px}
h1,h2{font-family:"Barlow Condensed",Barlow,"Arial Narrow",sans-serif;font-weight:600;letter-spacing:.01em;margin:0}
h1{font-size:clamp(30px,5vw,48px);line-height:1.05;max-width:22ch}
h2{font-size:26px;margin-bottom:6px}
p{max-width:72ch;margin:.4em 0}.muted{color:var(--steel)}
.hero{display:grid;grid-template-columns:1.1fr 1fr;gap:32px;align-items:end;border-bottom:3px solid var(--ink);padding-bottom:28px}
.bar{display:flex;height:46px;width:100%;margin-top:14px;border-radius:2px;overflow:hidden}
.bar span{display:block;height:100%}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:10px;font-size:14px}
.legend i{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:-1px}
section{margin-top:44px}
.panel{background:var(--card);border:1px solid var(--rule);padding:20px;margin-top:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--rule);white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{font-weight:600;color:var(--steel)}
.heat td{min-width:44px;text-align:center;font-size:12.5px}
.finding{border-left:4px solid var(--under);padding:4px 0 4px 14px;margin:14px 0}
.finding.down{border-color:var(--down)}.finding.info{border-color:var(--blue)}
select{font:inherit;padding:4px 8px;border:1px solid var(--rule);background:var(--card);color:var(--ink)}
select:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
canvas{max-width:100%}
@media (max-width:760px){.hero,.grid2{grid-template-columns:1fr}}
</style></head><body><main>
<header class="hero">
  <div>
    <p class="muted">ENGIE La Haute Borne, 4 x Senvion MM82 (8.2 MW), 10-minute SCADA, 2014 to 2015</p>
    <h1>__TOTAL__ MWh of production was lost, and two turbines account for __TOP2__ percent of it</h1>
  </div>
  <div>
    <p>Lost energy by driver, against __ACTUAL__ MWh produced (__LOSSPCT__ percent of potential).</p>
    <div class="bar" role="img" aria-label="Lost energy split by driver">__BAR__</div>
    <div class="legend">__LEGEND__</div>
  </div>
</header>

<section>
  <h2>What to act on first</h2>
  <p class="muted">Ranked by lost MWh. Reference power curves fitted on 2014 only, so 2015 is an out-of-sample year.</p>
  <div class="finding down"><strong>R80790 is the priority asset.</strong> Highest downtime loss in the fleet (__R90DT__ MWh over two years) and its underperformance loss rose from __R90U14__ MWh in 2014 to __R90U15__ MWh in 2015, out of sample. Its performance index sat 2.1 and 2.9 points below the fleet median in September and December 2015. Next step: review its alarm log and pitch and converter events for 2015 with site operations.</div>
  <div class="finding"><strong>R80711 reads 2 to 3 points above the fleet from April to August 2015.</strong> A sustained gain is flagged on purpose, because it is often a sensor change rather than real output. The anemometer check shows no step during the flagged window (its wind speed ratio to the fleet is 1.04 in Q2 and Q3 2015, within its 2014 range of 1.04 to 1.05), so the cause is open; next check is a directional and wake-sector comparison.</div>
  <div class="finding info"><strong>No static yaw misalignment above 4 degrees</strong> on any turbine in any month, and curtailment and suspected icing are small (__CURT__ and __ICE__ MWh). These are reported as negative results, not omitted.</div>
  <div class="panel scroll"><table id="prio"></table></div>
</section>

<section>
  <h2>Performance index gap to fleet median, by month</h2>
  <p class="muted">Points of performance index (actual over expected, excluding downtime and curtailment). Outlined cells meet the persistence rule: more than 2 points from the fleet for 3 or more consecutive months.</p>
  <div class="panel scroll"><table class="heat" id="heat"></table></div>
</section>

<section class="grid2">
  <div>
    <h2>Power curve check</h2>
    <p class="muted">2015 records (1 in 40) against the 2014 reference curve, density-normalized wind speed.</p>
    <label for="tsel">Turbine </label><select id="tsel"></select>
    <div class="panel"><canvas id="pc" height="300"></canvas></div>
  </div>
  <div>
    <h2>Monthly availability</h2>
    <p class="muted">Time-based availability during windy periods, per turbine.</p>
    <div class="panel"><canvas id="av" height="330"></canvas></div>
  </div>
</section>

<section>
  <h2>Data quality and traceability</h2>
  <p>Every excluded record maps to one rule in <code>sql/02_dq_flags.sql</code>. Our downtime estimate (__ESTDT__ MWh) is within __DTPCT__ percent of the operator's own unavailability counter (__OPDT__ MWh).</p>
  <p class="muted">Caveat: the plant meter, availability and curtailment tables are the example plant-level series distributed with NREL OpenOA, and the meter equals 0.98 of SCADA energy almost every month, so they test the reconciliation code rather than provide an independent audit.</p>
  <div class="panel scroll"><table id="dq"></table></div>
</section>
</main>
<script>
const R=__DATA__;
const C={downtime:'#B5452F',underperformance:'#E0A100',icing_suspected:'#7FB3C8',curtailment:'#8A7FB0',normal:'#2E6F95'};
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt=(x,d=1)=>x==null?'':Number(x).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
// priority table
const turbines=[...new Set(R.kpi_yearly.map(r=>r.turbine))].sort();
const drivers=['downtime','underperformance','icing_suspected','curtailment'];
const lossT={};turbines.forEach(t=>lossT[t]={});R.loss_by_driver.forEach(r=>lossT[r.turbine][r.driver]=r.lost_mwh);
const rows=turbines.map(t=>({t,tot:drivers.reduce((s,d)=>s+(lossT[t][d]||0),0)})).sort((a,b)=>b.tot-a.tot);
document.getElementById('prio').innerHTML='<tr><th>Rank</th><th>Turbine</th><th>Downtime MWh</th><th>Underperformance MWh</th><th>Icing MWh</th><th>Curtailment MWh</th><th>Total lost MWh</th><th>PI 2014</th><th>PI 2015</th></tr>'+
 rows.map((r,i)=>{const y14=R.kpi_yearly.find(k=>k.turbine==r.t&&k.year==2014),y15=R.kpi_yearly.find(k=>k.turbine==r.t&&k.year==2015);
 return `<tr><td>${i+1}</td><td>${r.t}</td>${drivers.map(d=>`<td>${fmt(lossT[r.t][d])}</td>`).join('')}<td><strong>${fmt(r.tot)}</strong></td><td>${fmt(y14.performance_index,3)}</td><td>${fmt(y15.performance_index,3)}</td></tr>`}).join('');
// heatmap
const months=[...new Set(R.kpi_monthly.map(r=>r.month))].sort();
const cell=(g,p)=>{const a=Math.min(Math.abs(g)/4,1);const col=g<0?`rgba(181,69,47,${a})`:`rgba(46,111,149,${a})`;
 return `<td style="background:${col};${p?'outline:2px solid currentColor;outline-offset:-2px;font-weight:600':''}">${Math.abs(g)<0.05?'0.0':(g>0?'+':'')+fmt(g,1)}</td>`};
document.getElementById('heat').innerHTML='<tr><th>Turbine</th>'+months.map(m=>`<th>${m.slice(2)}</th>`).join('')+'</tr>'+
 turbines.map(t=>'<tr><td>'+t+'</td>'+months.map(m=>{const k=R.kpi_monthly.find(r=>r.turbine==t&&r.month==m);return cell(k.pi_gap_pts,k.pi_gap_persistent)}).join('')+'</tr>').join('');
// dq table
document.getElementById('dq').innerHTML='<tr><th>Turbine</th><th>Records</th><th>Missing</th><th>Frozen wind sensor</th><th>Out of range</th><th>Power without wind</th><th>Excluded</th><th>Excluded %</th></tr>'+
 R.dq_summary.map(r=>`<tr><td>${r.turbine}</td><td>${fmt(r.records,0)}</td><td>${fmt(r.missing,0)}</td><td>${fmt(r.frozen_ws,0)}</td><td>${fmt(r.out_of_range,0)}</td><td>${fmt(r.power_without_wind,0)}</td><td>${fmt(r.excluded,0)}</td><td>${fmt(100*r.excluded/r.records,2)}</td></tr>`).join('');
// charts
Chart.defaults.font.family='Barlow, "Segoe UI", sans-serif';Chart.defaults.color=css('--steel');
const sel=document.getElementById('tsel');turbines.forEach(t=>sel.add(new Option(t,t)));sel.value='R80790';
let pc;function drawPC(t){const pts=R.scatter.filter(r=>r.turbine==t);
 const ds=['normal','underperformance','downtime','icing_suspected','curtailment'].map(s=>({type:'scatter',label:s.replace('_',' '),data:pts.filter(p=>p.state==s).map(p=>({x:p.ws_norm,y:p.power_kw})),backgroundColor:C[s]+(s=='normal'?'55':'cc'),pointRadius:s=='normal'?1.6:2.4}));
 ds.push({type:'line',label:'2014 reference',data:R.curves[t].map(c=>({x:c.ws_ms,y:c.p_kw})),borderColor:css('--ink'),borderWidth:2,pointRadius:0});
 pc&&pc.destroy();pc=new Chart(document.getElementById('pc'),{data:{datasets:ds},options:{animation:false,parsing:false,scales:{x:{type:'linear',min:0,max:20,title:{display:true,text:'Normalized wind speed (m/s)'}},y:{min:-50,max:2200,title:{display:true,text:'Power (kW)'}}},plugins:{legend:{labels:{boxWidth:10}}}}})}
drawPC(sel.value);sel.onchange=()=>drawPC(sel.value);
const lc=['#2E6F95','#4E8A5E','#8A7FB0','#B5452F'];
new Chart(document.getElementById('av'),{type:'line',data:{labels:months.map(m=>m.slice(2)),datasets:turbines.map((t,i)=>({label:t,data:months.map(m=>100*R.kpi_monthly.find(r=>r.turbine==t&&r.month==m).time_availability),borderColor:lc[i],backgroundColor:lc[i],pointRadius:2,borderWidth:t=='R80790'?2.5:1.3}))},
 options:{animation:false,scales:{y:{min:85,max:100.5,title:{display:true,text:'Availability (%)'}}},plugins:{legend:{labels:{boxWidth:10}}}}});
</script></body></html>"""

colors = {"downtime": "#B5452F", "underperformance": "#E0A100", "icing_suspected": "#7FB3C8", "curtailment": "#8A7FB0"}
names = {"downtime": "Downtime", "underperformance": "Underperformance", "icing_suspected": "Suspected icing", "curtailment": "Curtailment"}
bar = "".join(f'<span style="width:{100*v/total_loss:.2f}%;background:{colors[d]}"></span>' for d, v in by_driver.items())
legend = "".join(f'<span><i style="background:{colors[d]}"></i>{names[d]} {v:,.0f} MWh</span>' for d, v in by_driver.items())
per_t = {}
for r in losses:
    per_t[r["turbine"]] = per_t.get(r["turbine"], 0) + r["lost_mwh"]
top2 = sum(sorted(per_t.values(), reverse=True)[:2]) / total_loss * 100

rep = {
    "__TOTAL__": f"{total_loss:,.0f}", "__TOP2__": f"{top2:.0f}", "__ACTUAL__": f"{actual:,.0f}",
    "__LOSSPCT__": f"{100*total_loss/(actual+total_loss):.1f}", "__BAR__": bar, "__LEGEND__": legend,
    "__R90DT__": f"{sum(r['lost_mwh'] for r in losses if r['turbine']=='R80790' and r['driver']=='downtime'):.0f}",
    "__R90U14__": f"{yr[('R80790',2014)]['underperf_mwh']:.0f}", "__R90U15__": f"{yr[('R80790',2015)]['underperf_mwh']:.0f}",
    "__CURT__": f"{by_driver.get('curtailment',0):.1f}", "__ICE__": f"{by_driver.get('icing_suspected',0):.1f}",
    "__ESTDT__": f"{est_dt:,.0f}", "__OPDT__": f"{op_dt:,.0f}", "__DTPCT__": f"{100*abs(op_dt-est_dt)/op_dt:.0f}",
    "__DATA__": json.dumps(R),
    "__CHARTJS__": (ROOT / "vendor" / "chart.umd.js").read_text(),  # Chart.js 4.4.1, MIT, inlined so the file works offline
}
for k, v in rep.items():
    HTML = HTML.replace(k, v)
(ROOT / "outputs" / "dashboard.html").write_text(HTML)
print("total_loss", round(total_loss, 1), "actual", round(actual, 1), "top2", round(top2, 1), "est_dt", round(est_dt), "op_dt", round(op_dt))
