"""運用ダッシュボード生成: 実績推移と AS-IS / TO-BE を1枚のHTMLに描画する

state/ (1株トラック) と state/live/ (単元株トラック) の資産ログ・保有・取引履歴を読み、
GOALS.md の目標ラダーと突き合わせた自己完結型HTMLを reports/dashboard.html に出力する。

  python analysis/dashboard.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reports", "dashboard.html")

# GOALS.md の目標ラダー (単元株トラック=実弾想定150万に対する金額目標)
LADDER = [
    ("2026年末", dt.date(2026, 12, 30), 1_650_000, 0.27),
    ("2027年末", dt.date(2027, 12, 30), 2_200_000, 0.28),
    ("2028年末", dt.date(2028, 12, 30), 3_000_000, 0.22),
]
LIVE_START = (dt.date(2026, 8, 26), 1_500_000)
RETREAT_LINE = 1_200_000            # 撤退ライン (-20%)
T1_START = (dt.date(2026, 8, 24), 500_000)
T1_RETREAT = 400_000
SHARPE_GATE_15 = 0.8                # 信用1.5倍の許可基準
SHARPE_GATE_20 = 1.2                # 信用2倍の許可基準

JP = "'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', sans-serif"


def read_track(state_dir: str) -> dict:
    d: dict = {"equity": None, "portfolio": None, "summary": None}
    eq = os.path.join(state_dir, "equity_log.csv")
    if os.path.exists(eq):
        d["equity"] = pd.read_csv(eq, parse_dates=["date"]).sort_values("date")
    pf = os.path.join(state_dir, "portfolio.json")
    if os.path.exists(pf):
        d["portfolio"] = json.load(open(pf, encoding="utf-8"))
    sm = os.path.join(state_dir, "summary.json")
    if os.path.exists(sm):
        d["summary"] = json.load(open(sm, encoding="utf-8"))
    return d


def metrics(equity: pd.Series, risk_free: float = 0.001) -> dict:
    import sys

    sys.path.insert(0, ROOT)
    from autotrader.risk.metrics import summarize

    r = equity.pct_change().dropna()
    if len(r) < 2:
        return {}
    return summarize(r, risk_free)


def yen(v: float) -> str:
    return f"{v:,.0f}"


def pct(v: float, digits: int = 2) -> str:
    return f"{v * 100:+.{digits}f}%"


# ---------------------------------------------------------------- SVG chart
def line_chart(
    series: list[tuple[str, str, list[tuple[dt.date, float]]]],
    refs: list[tuple[str, str, float]],
    x0: dt.date, x1: dt.date, w: int = 860, h: int = 300,
    y_pad: float = 0.05,
) -> str:
    """series: (label, cssvar, points) の実線。refs: (label, cssvar, y値) の水平線"""
    all_y = [y for _, _, pts in series for _, y in pts] + [y for _, _, y in refs]
    lo, hi = min(all_y), max(all_y)
    span = (hi - lo) or 1
    lo -= span * y_pad
    hi += span * y_pad
    ml, mr, mt, mb = 64, 150, 16, 30
    pw, ph = w - ml - mr, h - mt - mb

    def X(d: dt.date) -> float:
        return ml + pw * ((d - x0).days / max(1, (x1 - x0).days))

    def Y(v: float) -> float:
        return mt + ph * (1 - (v - lo) / (hi - lo))

    out = [f'<svg viewBox="0 0 {w} {h}" role="img" style="width:100%;height:auto;display:block">']
    # グリッド (横4本) + y軸ラベル
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        y = Y(v)
        out.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{w - mr}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        out.append(f'<text x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end" class="ax">{v / 1e4:,.0f}万</text>')
    # x軸ラベル (始点・月初・終点)
    ticks = [x0]
    m = dt.date(x0.year, x0.month, 1)
    while m <= x1:
        if m > x0:
            ticks.append(m)
        m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    ticks.append(x1)
    for t in ticks:
        out.append(f'<text x="{X(t):.1f}" y="{h - 8}" text-anchor="middle" class="ax">{t.month}/{t.day}</text>')
    # 参照線
    for label, var, v in refs:
        y = Y(v)
        out.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{w - mr}" y2="{y:.1f}" stroke="var({var})" stroke-width="1.5" stroke-dasharray="6 4"/>')
        out.append(f'<text x="{w - mr + 6}" y="{y + 4:.1f}" class="rl" fill="var({var})">{label}</text>')
    # データ系列
    for label, var, pts in series:
        if not pts:
            continue
        path = " ".join(f"{'M' if i == 0 else 'L'}{X(d):.1f},{Y(v):.1f}" for i, (d, v) in enumerate(pts))
        out.append(f'<path d="{path}" fill="none" stroke="var({var})" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>')
        for d, v in pts:
            out.append(
                f'<circle cx="{X(d):.1f}" cy="{Y(v):.1f}" r="4" fill="var({var})" stroke="var(--surface)" stroke-width="2">'
                f"<title>{d.isoformat()}  {yen(v)}円</title></circle>"
            )
        d, v = pts[-1]
        out.append(f'<text x="{X(d) + 8:.1f}" y="{Y(v) - 8:.1f}" class="dl" fill="var({var})">{label} {v / 1e4:,.1f}万</text>')
    out.append("</svg>")
    return "".join(out)


def tile(label: str, value: str, sub: str = "", tone: str = "") -> str:
    cls = f"tile {tone}".strip()
    return (f'<div class="{cls}"><div class="t-label">{label}</div>'
            f'<div class="t-value">{value}</div><div class="t-sub">{sub}</div></div>')


def holdings_table(summary: dict | None, portfolio: dict | None) -> str:
    rows = []
    if summary and summary.get("holdings"):
        for hh in summary["holdings"]:
            tone = "pos" if hh["pnl_pct"] >= 0 else "neg"
            rows.append(
                f"<tr><td>{hh['ticker']}</td><td class='num'>{hh['quantity']:,}株</td>"
                f"<td class='num'>{hh['avg_cost']:,.1f}</td><td class='num'>{hh['price']:,.1f}</td>"
                f"<td class='num {tone}'>{hh['pnl_pct']:+.2f}%</td><td class='num'>{hh['weight_pct']}%</td></tr>"
            )
        head = "<tr><th>銘柄</th><th>数量</th><th>取得</th><th>現在</th><th>損益</th><th>配分</th></tr>"
    elif portfolio and portfolio.get("positions"):
        for t, p in portfolio["positions"].items():
            rows.append(f"<tr><td>{t}</td><td class='num'>{p['quantity']:,}株</td>"
                        f"<td class='num'>{p['avg_cost']:,.1f}</td><td class='num'>—</td>"
                        f"<td class='num'>—</td><td class='num'>—</td></tr>")
        head = "<tr><th>銘柄</th><th>数量</th><th>取得</th><th>現在</th><th>損益</th><th>配分</th></tr>"
    else:
        return "<p class='muted'>保有なし</p>"
    return f"<div class='tblwrap'><table>{head}{''.join(rows)}</table></div>"


def trades_table(portfolio: dict | None, n: int = 8) -> str:
    if not portfolio or not portfolio.get("trades"):
        return "<p class='muted'>取引なし</p>"
    rows = []
    for t in portfolio["trades"][-n:][::-1]:
        side = "買" if t["side"] == "BUY" else "売"
        cls = "buy" if t["side"] == "BUY" else "sell"
        rows.append(f"<tr><td>{t['date']}</td><td><span class='pill {cls}'>{side}</span></td>"
                    f"<td>{t['ticker']}</td><td class='num'>{t['quantity']:,}株</td>"
                    f"<td class='num'>{t['price']:,.1f}</td>"
                    f"<td class='reason'>{html.escape(t['reason'][:48])}</td></tr>")
    return ("<div class='tblwrap'><table><tr><th>日付</th><th></th><th>銘柄</th><th>数量</th>"
            f"<th>価格</th><th>理由</th></tr>{''.join(rows)}</table></div>")


def main() -> None:
    live = read_track(os.path.join(ROOT, "state", "live"))
    t1 = read_track(os.path.join(ROOT, "state"))
    today = dt.date.today()

    # --- 単元株トラック (実弾想定): AS-IS ---
    lv_eq = live["equity"]
    lv_now = float(lv_eq["equity"].iloc[-1]) if lv_eq is not None else LIVE_START[1]
    lv_date = lv_eq["date"].iloc[-1].date() if lv_eq is not None else LIVE_START[0]
    lv_ret = lv_now / LIVE_START[1] - 1
    lv_m = metrics(lv_eq.set_index("date")["equity"]) if lv_eq is not None else {}
    lv_days = len(lv_eq) if lv_eq is not None else 0

    # TO-BE ペース (2026年末目標への線形ペース)
    g_label, g_date, g_target, g_prob = LADDER[0]
    total_d = (g_date - LIVE_START[0]).days
    frac = min(1.0, max(0.0, (lv_date - LIVE_START[0]).days / total_d))
    pace_today = LIVE_START[1] + (g_target - LIVE_START[1]) * frac
    gap = lv_now - pace_today
    bdays_left = int(pd.bdate_range(today, g_date).size)
    need_daily = (g_target / lv_now) ** (1 / max(1, bdays_left)) - 1 if lv_now > 0 else 0

    # --- 1株トラック: AS-IS (実力測定) ---
    t1_eq = t1["equity"]
    t1_now = float(t1_eq["equity"].iloc[-1]) if t1_eq is not None else T1_START[1]
    t1_ret = t1_now / T1_START[1] - 1
    t1_m = metrics(t1_eq.set_index("date")["equity"]) if t1_eq is not None else {}
    t1_days = len(t1_eq) if t1_eq is not None else 0

    sharpe = t1_m.get("sharpe")
    if t1_days < 15:
        gate = f"計測 {t1_days}/15営業日 — 判定はサンプル15日以降"
        gate_tone = ""
    elif sharpe is not None and sharpe >= SHARPE_GATE_20:
        gate, gate_tone = f"実測Sharpe {sharpe:.2f} ≥ 1.2 → 信用2倍の検討水準", "good"
    elif sharpe is not None and sharpe >= SHARPE_GATE_15:
        gate, gate_tone = f"実測Sharpe {sharpe:.2f} ≥ 0.8 → 信用1.5倍の検討水準", "good"
    else:
        gate, gate_tone = f"実測Sharpe {sharpe:.2f} < 0.8 → 現物プランA継続", "warn"

    # --- チャート ---
    lv_pts = ([(r.date.date(), float(r.equity)) for r in lv_eq.itertuples()] if lv_eq is not None else [])
    pace_pts = [(LIVE_START[0], float(LIVE_START[1])), (g_date, float(g_target))]
    chart_live = line_chart(
        [("TO-BEペース", "--muted2", pace_pts), ("実績", "--acc", lv_pts)],
        [("撤退ライン 120万", "--crit", RETREAT_LINE)],
        LIVE_START[0], g_date,
    )
    t1_pts = ([(r.date.date(), float(r.equity)) for r in t1_eq.itertuples()] if t1_eq is not None else [])
    chart_t1 = line_chart(
        [("実績", "--teal", t1_pts)],
        [("開始 50万", "--muted2", T1_START[1]), ("撤退 40万", "--crit", T1_RETREAT)],
        T1_START[0], today + dt.timedelta(days=3), h=220,
    )

    # --- ラダー表 ---
    ladder_rows = []
    for label, date_, target, prob in LADDER:
        prog = min(100.0, max(0.0, (lv_now - LIVE_START[1]) / (target - LIVE_START[1]) * 100))
        ladder_rows.append(
            f"<tr><td>{label}<span class='muted'> ({date_.month}/{date_.day})</span></td>"
            f"<td class='num'>{yen(target)}円</td><td class='num'>{prob:.0%}</td>"
            f"<td><div class='bar'><div class='fill' style='width:{prog:.1f}%'></div></div>"
            f"<span class='muted'>{prog:.0f}%</span></td></tr>"
        )

    gap_tone = "pos" if gap >= 0 else "neg"
    updated = f"{today.isoformat()} 16:20 JST 更新"
    phase = f"ペーパー計測 {t1_days}日目"

    html_doc = f"""<title>株自動運用ボード</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=Zen+Kaku+Gothic+New:wght@700&display=swap">
<style>
:root {{
  --bg:#F4F6F9; --surface:#FFFFFF; --ink:#1B2537; --muted:#5B6578; --muted2:#8A94A8;
  --grid:#E3E7EF; --border:#DDE2EB; --acc:#3E63DD; --teal:#0F8C7E; --crit:#C43D3D;
  --good:#1F7A4D; --warn:#A06A1B; --pos:#1F7A4D; --neg:#C43D3D; --chip:#EDF0F7;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#12151C; --surface:#1B2029; --ink:#E7EAF2; --muted:#9AA4B8; --muted2:#6B7690;
    --grid:#2A303D; --border:#323949; --acc:#7B96F4; --teal:#3AC0B0; --crit:#E06C6C;
    --good:#4FBF8B; --warn:#D8A04A; --pos:#4FBF8B; --neg:#E06C6C; --chip:#252B38;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#12151C; --surface:#1B2029; --ink:#E7EAF2; --muted:#9AA4B8; --muted2:#6B7690;
  --grid:#2A303D; --border:#323949; --acc:#7B96F4; --teal:#3AC0B0; --crit:#E06C6C;
  --good:#4FBF8B; --warn:#D8A04A; --pos:#4FBF8B; --neg:#E06C6C; --chip:#252B38;
}}
* {{ box-sizing:border-box }}
body {{ background:var(--bg); color:var(--ink); font-family:{JP}; margin:0; line-height:1.6; }}
.wrap {{ max-width:1000px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-family:'Zen Kaku Gothic New',{JP}; font-size:1.5rem; margin:0; letter-spacing:.02em; }}
h2 {{ font-family:'Zen Kaku Gothic New',{JP}; font-size:1.05rem; margin:36px 0 12px; }}
.head {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }}
.chip {{ background:var(--chip); border:1px solid var(--border); border-radius:99px; padding:2px 12px; font-size:.78rem; color:var(--muted); }}
.updated {{ color:var(--muted2); font-size:.8rem; margin-left:auto; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin-top:18px; }}
.tile {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
.t-label {{ font-size:.75rem; color:var(--muted); letter-spacing:.04em; }}
.t-value {{ font-size:1.45rem; font-weight:700; font-variant-numeric:tabular-nums; margin-top:2px; }}
.t-sub {{ font-size:.78rem; color:var(--muted); font-variant-numeric:tabular-nums; }}
.tile.good .t-value {{ color:var(--good) }} .tile.warn .t-value {{ color:var(--warn) }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:18px; }}
.ax {{ font-size:11px; fill:var(--muted2); font-family:{JP}; }}
.dl {{ font-size:12px; font-weight:700; font-family:{JP}; }}
.rl {{ font-size:11px; font-family:{JP}; }}
.tblwrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:.85rem; }}
th {{ text-align:left; color:var(--muted); font-weight:500; font-size:.75rem; border-bottom:1px solid var(--border); padding:6px 10px; }}
td {{ padding:7px 10px; border-bottom:1px solid var(--grid); }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.pos {{ color:var(--pos) }} .neg {{ color:var(--neg) }} .muted {{ color:var(--muted2); font-size:.85em }}
.pill {{ border-radius:5px; padding:1px 8px; font-size:.75rem; color:#fff; }}
.pill.buy {{ background:var(--acc) }} .pill.sell {{ background:var(--crit) }}
.reason {{ color:var(--muted); font-size:.78rem; }}
.bar {{ display:inline-block; width:120px; height:8px; background:var(--chip); border-radius:99px; vertical-align:middle; margin-right:8px; }}
.fill {{ height:100%; background:var(--acc); border-radius:99px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
@media (max-width:760px) {{ .grid2 {{ grid-template-columns:1fr }} }}
.note {{ color:var(--muted); font-size:.8rem; margin-top:28px; border-top:1px solid var(--border); padding-top:12px; }}
</style>
<div class="wrap">
  <div class="head">
    <h1>株自動運用ボード</h1>
    <span class="chip">{phase}</span>
    <span class="chip">スイング・現物</span>
    <span class="updated">{updated}</span>
  </div>

  <div class="tiles">
    {tile("単元株トラック 総資産 (実弾想定150万)", yen(lv_now) + "円", f"累積 {pct(lv_ret)} / {lv_days}営業日")}
    {tile("対TO-BEペース (2026末165万への進捗線)", f"{gap / 1e4:+,.1f}万円",
          f"本日のペース基準 {yen(pace_today)}円", gap_tone if gap < 0 else "good")}
    {tile("1株トラック 総資産 (実力測定用)", yen(t1_now) + "円", f"累積 {pct(t1_ret)} / {t1_days}営業日")}
    {tile("レバレッジ許可判定", "—" if t1_days < 15 or sharpe is None else f"Sharpe {sharpe:.2f}", gate, gate_tone)}
  </div>

  <h2>AS-IS → TO-BE (単元株トラック・金額目標)</h2>
  <div class="card">
    <div class="tblwrap"><table>
      <tr><th>マイルストーン</th><th>TO-BE</th><th>達成確率(試算)</th><th>進捗 (AS-IS: {yen(lv_now)}円)</th></tr>
      {''.join(ladder_rows)}
    </table></div>
    <p class="muted" style="margin:10px 0 0">
      年内目標まで残り{bdays_left}営業日 / 必要ペース 日次{pct(need_daily)} ・
      撤退ライン {yen(RETREAT_LINE)}円 (現在との差 {(lv_now - RETREAT_LINE) / 1e4:,.1f}万円) ・
      確率はモンテカルロ試算 (analysis/target_plan.py)
    </p>
  </div>

  <h2>実績推移 — 単元株トラック vs TO-BEペース</h2>
  <div class="card">{chart_live}</div>

  <h2>実績推移 — 1株トラック (戦略の素の実力)</h2>
  <div class="card">{chart_t1}
    <p class="muted" style="margin:10px 0 0">
      実測(年率換算): リターン {pct(t1_m['annual_return'], 1) if t1_m else '計測中'} /
      ボラ {f"{t1_m['annual_volatility'] * 100:.1f}%" if t1_m else '計測中'} /
      Sharpe {f"{t1_m['sharpe']:.2f}" if t1_m else '計測中'} — サンプル{t1_days}営業日
      (15日未満は参考値)
    </p>
  </div>

  <div class="grid2">
    <div><h2>保有 — 単元株トラック</h2><div class="card">{holdings_table(live['summary'], live['portfolio'])}</div></div>
    <div><h2>保有 — 1株トラック</h2><div class="card">{holdings_table(t1['summary'], t1['portfolio'])}</div></div>
  </div>

  <div class="grid2">
    <div><h2>直近の取引 — 単元株</h2><div class="card">{trades_table(live['portfolio'])}</div></div>
    <div><h2>直近の取引 — 1株</h2><div class="card">{trades_table(t1['portfolio'])}</div></div>
  </div>

  <p class="note">
    毎営業日16:20 JST の自動売買サイクル後に更新。ペーパートレード (仮想売買) の結果であり、
    実際の発注は行っていません。目標ラダーと判定基準の詳細は リポジトリの GOALS.md を参照。
    投資判断は自己責任であり、本ボードは利益を保証するものではありません。
  </p>
</div>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"ダッシュボードを出力: {OUT}")


if __name__ == "__main__":
    main()
