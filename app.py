import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("METRIKA_TOKEN", "")
COUNTER = os.getenv("COUNTER_ID", "55085689")
BASE    = "https://api-metrika.yandex.net"
HDR     = {"Authorization": f"OAuth {TOKEN}"}
NO_ROBOTS = "ym:s:isRobot=='No'"

st.set_page_config(page_title="Traffic Dashboard · Herbies",
                   page_icon="🌿", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
html,body,[class*="css"]{font-family:'IBM Plex Sans',sans-serif;background:#0d0d0d;color:#e8e8e8}
.block-container{padding:1.5rem 2rem;max-width:1440px}
section[data-testid="stSidebar"]{background:#111;border-right:1px solid #222}
.kpi{background:#161616;border:1px solid #1e1e1e;border-radius:6px;padding:1.1rem 1.4rem;position:relative;overflow:hidden}
.kpi::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#00e676,#00b0ff)}
.kpi-label{font-family:'IBM Plex Mono',monospace;font-size:.6rem;letter-spacing:.14em;color:#555;text-transform:uppercase;margin-bottom:.4rem}
.kpi-val{font-family:'IBM Plex Mono',monospace;font-size:1.9rem;font-weight:600;color:#f5f5f5;line-height:1;margin-bottom:.3rem}
.up{color:#00e676;font-size:.75rem;font-family:'IBM Plex Mono',monospace}
.dn{color:#ff5252;font-size:.75rem;font-family:'IBM Plex Mono',monospace}
.fl{color:#555;font-size:.75rem;font-family:'IBM Plex Mono',monospace}
.sec{font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.16em;color:#444;text-transform:uppercase;border-bottom:1px solid #1e1e1e;padding-bottom:.45rem;margin:2rem 0 1rem}
.ts{font-family:'IBM Plex Mono',monospace;font-size:.58rem;color:#2a2a2a;text-align:right;margin-top:1rem}
.legend-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
</style>
""", unsafe_allow_html=True)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=15 * 60 * 1000, key="ar")
except ImportError:
    pass

# ── helpers ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def stat(metrics, dims=None, date1="today", date2="today", flt=None, limit=100):
    f = NO_ROBOTS + (f" AND {flt}" if flt else "")
    p = dict(ids=COUNTER, metrics=metrics, date1=date1,
             date2=date2, filters=f, limit=limit, accuracy="full")
    if dims:
        p["dimensions"] = dims
    try:
        r = requests.get(f"{BASE}/stat/v1/data", headers=HDR, params=p, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=3600, show_spinner=False)
def get_goals():
    try:
        r = requests.get(f"{BASE}/management/v1/counter/{COUNTER}/goals",
                         headers=HDR, timeout=15)
        r.raise_for_status()
        return r.json().get("goals", [])
    except:
        return []

def fmt(n):
    if n is None: return "—"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(int(n))

def get_metric(data, row_idx=0, metric_idx=0):
    try:
        return data["data"][row_idx]["metrics"][metric_idx]
    except:
        return None

def delta_html(today, yest, label_a="", label_b=""):
    if not yest: return '<span class="fl">—</span>'
    d = today - yest
    pct = d / yest * 100
    sign = "+" if d >= 0 else ""
    cls = "up" if d > 0 else ("dn" if d < 0 else "fl")
    arrow = "▲" if d > 0 else ("▼" if d < 0 else "●")
    cmp_hint = f" <span style='color:#333;font-size:.6rem'>({label_a} vs {label_b})</span>" if label_a else ""
    return f'<span class="{cls}">{arrow} {sign}{pct:.1f}%{cmp_hint}</span>'

def find_goal(goals, *keywords):
    """Find goal id: numeric keyword = direct ID, string = search name/conditions."""
    for kw in keywords:
        if str(kw).isdigit():
            for g in goals:
                if str(g.get("id")) == str(kw):
                    return g.get("id")
        else:
            for g in goals:
                name  = g.get("name", "").lower()
                conds = str(g.get("conditions", "")).lower()
                if kw.lower() in name or kw.lower() in conds:
                    return g.get("id")
    return None

def d2s(d): return d.strftime("%Y-%m-%d")

STAGE_COLORS = ["#00e676","#00c8ff","#ff9100","#ff5252","#e040fb","#ffeb3b","#00bcd4"]

# Composite paired goals — честная посессионная конверсия шаг→шаг
# Знаменатель каждой пары = goal_visits первого шага из основного FUNNEL_DEF
PAIR_GOALS = [
    # (название перехода, ID составной цели-пары, знаменатель_keyword)
    ("Просмотр → Добавил", 562849814, "cannabis-seeds"),
    ("Добавил → Корзина",  562849950, "add_to_cart"),
    ("Корзина → Чекаут",   562850066, "basket"),
    ("Чекаут → Покупка",   562851178, "начало оформления"),
]

# ── sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🌿 Traffic Dashboard")
    st.markdown("---")

    country_raw = stat("ym:s:visits", dims="ym:s:regionCountryName", limit=30)
    countries = ["Все страны"]
    if "data" in country_raw:
        for row in country_raw["data"]:
            n = row["dimensions"][0].get("name", "")
            if n: countries.append(n)
    country = st.selectbox("🌍 Страна", countries)

    # Traffic source — store id for filtering, name for display
    src_raw = stat("ym:s:visits", dims="ym:s:trafficSource", limit=20)
    src_id_map = {"Все источники": None}   # display → filter_id
    src_labels = ["Все источники"]
    if "data" in src_raw:
        for row in src_raw["data"]:
            dim = row["dimensions"][0]
            name = dim.get("name", "")
            fid  = dim.get("id") or name   # id = 'organic', 'direct', etc.
            if name:
                src_labels.append(name)
                src_id_map[name] = fid
    traffic_src = st.selectbox("📡 Источник трафика", src_labels)
    traffic_src_id = src_id_map.get(traffic_src)  # actual API filter value

    # Landing page — use name (URL) directly for filter
    land_raw = stat("ym:s:visits", dims="ym:s:startURL", limit=30)
    land_options = {"Все страницы входа": None}   # display → filter_value
    land_labels = ["Все страницы входа"]
    if "data" in land_raw:
        for row in land_raw["data"]:
            dim = row["dimensions"][0]
            full_url = dim.get("name", "")
            if full_url:
                # Extract path for display
                path = full_url.replace("https://herbiesheadshop.com","")                                .replace("https://www.herbiesheadshop.com","")                                .split("?")[0].rstrip("/") or "/"
                short = path[:60]
                land_labels.append(short)
                land_options[short] = path   # store path for contains filter
    landing_label = st.selectbox("🚪 Страница входа", land_labels)
    landing_path  = land_options.get(landing_label)

    # Build combined filter
    def q(v): return v.replace("'", "\'") if v else v
    filters = []
    if country != "Все страны":
        filters.append(f"ym:s:regionCountryName=='{q(country)}'")
    if traffic_src_id:
        filters.append(f"ym:s:trafficSource=='{q(traffic_src_id)}'")
    if landing_path:
        filters.append(f"ym:s:startURL=@'{q(landing_path)}'")
    c_flt = " AND ".join(filters) if filters else None

    # Active filter badge
    active = []
    if country != "Все страны": active.append(country)
    if traffic_src_id: active.append(traffic_src)
    if landing_path: active.append(landing_label)
    if active:
        st.markdown(f"""<div style='font-family:IBM Plex Mono,monospace;font-size:.58rem;
        color:#00e676;background:#0a1a0a;border:1px solid #1a3a1a;border-radius:4px;
        padding:.3rem .6rem;margin-top:.3rem'>
        🔽 {" · ".join(active)}</div>""", unsafe_allow_html=True)

    st.markdown("---")
    metric_mode = st.radio("📐 Считать по", ["Сеансам", "Пользователям"],
                           horizontal=True)
    st.markdown("---")
    st.markdown("#### 📅 Период")
    mode = st.radio("Режим", ["Сегодня vs вчера", "Выбрать даты"],
                    label_visibility="collapsed")

    if mode == "Сегодня vs вчера":
        d1_main = d2s(date.today());     d2_main = d2s(date.today())
        d1_cmp  = d2s(date.today()-timedelta(1)); d2_cmp = d2s(date.today()-timedelta(1))
        label_main = "Сегодня"; label_cmp = "Вчера"
    else:
        st.markdown("""<div style='font-family:IBM Plex Mono,monospace;font-size:.58rem;
        color:#555;margin-bottom:.3rem'>🟢 ПЕРИОД A — начало</div>""",
        unsafe_allow_html=True)
        da_s = st.date_input("", date.today()-timedelta(7),
                             key="das", label_visibility="collapsed",
                             format="DD.MM.YYYY")
        st.markdown("""<div style='font-family:IBM Plex Mono,monospace;font-size:.58rem;
        color:#555;margin:.3rem 0'>🟢 ПЕРИОД A — конец (включительно)</div>""",
        unsafe_allow_html=True)
        da_e = st.date_input("", date.today(),
                             key="dae", label_visibility="collapsed",
                             format="DD.MM.YYYY")
        if da_e < da_s:
            st.error("Конец A раньше начала A"); da_e = da_s

        st.markdown("""<div style='font-family:IBM Plex Mono,monospace;font-size:.58rem;
        color:#444;margin:.5rem 0 .3rem'>⚪ ПЕРИОД B — начало</div>""",
        unsafe_allow_html=True)
        db_s = st.date_input("", date.today()-timedelta(14),
                             key="dbs", label_visibility="collapsed",
                             format="DD.MM.YYYY")
        st.markdown("""<div style='font-family:IBM Plex Mono,monospace;font-size:.58rem;
        color:#444;margin:.3rem 0'>⚪ ПЕРИОД B — конец (включительно)</div>""",
        unsafe_allow_html=True)
        db_e = st.date_input("", date.today()-timedelta(8),
                             key="dbe", label_visibility="collapsed",
                             format="DD.MM.YYYY")
        if db_e < db_s:
            st.error("Конец B раньше начала B"); db_e = db_s

        d1_main=d2s(da_s); d2_main=d2s(da_e)
        d1_cmp =d2s(db_s); d2_cmp =d2s(db_e)
        label_main=f"{da_s.strftime('%d.%m')}–{da_e.strftime('%d.%m')}"
        label_cmp =f"{db_s.strftime('%d.%m')}–{db_e.strftime('%d.%m')}"
        days_a = (da_e - da_s).days + 1
        days_b = (db_e - db_s).days + 1
        st.markdown(f"""<div style='font-family:IBM Plex Mono,monospace;font-size:.58rem;
        color:#333;margin-top:.4rem'>
        A: {days_a} дн. &nbsp;·&nbsp; B: {days_b} дн.
        {"&nbsp;·&nbsp; <span style='color:#ff9100'>⚠️ сегодня = частичные данные</span>" if da_e >= date.today() or db_e >= date.today() else ""}
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔄 Обновить"):
        st.cache_data.clear(); st.rerun()
    st.markdown(f'<div class="ts">↻ {datetime.now().strftime("%H:%M:%S")}</div>',
                unsafe_allow_html=True)

if not TOKEN:
    st.error("❌ METRIKA_TOKEN не задан в .env"); st.stop()

# Debug: show raw filter and dimension values
with st.expander("🔧 Отладка фильтров", expanded=False):
    st.code(f"c_flt = {repr(c_flt)}\ntraffic_src_id = {repr(traffic_src_id)}\nlanding_path = {repr(landing_path)}")
    st.markdown("**Сырые значения trafficSource из API:**")
    _src_debug = stat("ym:s:visits", dims="ym:s:trafficSource", limit=20)
    if "data" in _src_debug:
        for row in _src_debug["data"]:
            dim = row["dimensions"][0]
            st.write(f"name={repr(dim.get('name'))} | id={repr(dim.get('id'))}")
    else:
        st.write(_src_debug)
    st.markdown("**Тест запроса с текущим фильтром:**")
    _test = stat("ym:s:visits", date1=d1_main, date2=d2_main, flt=c_flt)
    st.write(_test)

# Metric mode variables
base_m      = "ym:s:visits" if metric_mode == "Сеансам" else "ym:s:users"
goal_sfx    = "visits"      if metric_mode == "Сеансам" else "users"
base_label  = "сеансов"     if metric_mode == "Сеансам" else "пользователей"

# ── title ──────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="display:flex;align-items:baseline;gap:1rem;margin-bottom:.5rem">
  <span style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;font-weight:600;color:#f0f0f0">TRAFFIC MONITOR</span>
  <span style="font-family:'IBM Plex Mono',monospace;font-size:.7rem;color:#444;letter-spacing:.1em">
    {label_main} vs {label_cmp} · {" · ".join(active) if active else "Все"}
  </span>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# БЛОК 1 — KPI
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f'''<div class="sec">◈ ключевые метрики · 
  <span style="color:#00e676">{label_main}</span>
  <span style="color:#444"> vs </span>
  <span style="color:#555">{label_cmp}</span>
  <span style="color:#333"> · Δ = A минус B</span>
</div>''', unsafe_allow_html=True)
KPI_M = "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth"
with st.spinner(""):
    d_main = stat(KPI_M, date1=d1_main, date2=d2_main, flt=c_flt)
    d_cmp  = stat(KPI_M, date1=d1_cmp,  date2=d2_cmp,  flt=c_flt)

for col, (label, idx, sfx) in zip(st.columns(4),
    [("СЕАНСЫ" if metric_mode=="Сеансам" else "ПОЛЬЗ.", 0, ""),
     ("ПОЛЬЗ." if metric_mode=="Сеансам" else "СЕАНСЫ", 1, ""),
     ("ОТКАЗЫ", 2, "%"), ("ГЛУБИНА", 3, "")]):
    tv = get_metric(d_main,0,idx); yv = get_metric(d_cmp,0,idx)
    display = "—" if tv is None else (f"{tv:.1f}{sfx}" if sfx else fmt(tv))
    with col:
        st.markdown(f"""<div class="kpi">
          <div class="kpi-label">{label}</div>
          <div class="kpi-val">{display}</div>
          {delta_html(tv or 0, yv, label_main, label_cmp)}</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# БЛОК 2 — Воронка
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sec">◈ воронка продаж</div>', unsafe_allow_html=True)

# Funnel stages in sequential order — each step's conversion = count / prev_step_count
# Remove "Нажал Create order" per user request
FUNNEL_DEF = [
    ("Просмотр товара",   "cannabis-seeds", "просмотр",  "product"),
    ("Добавил в корзину", "add_to_cart",    "добавлен",  "добавление в корзину"),
    ("Корзина",           "basket",         "корзин",    "cart_view"),
    ("Чекаут",  "начало оформления", "begin-checkout", "автоцель: начало"),
    ("Выбрал оплату",     "add_payment_info","оплат",    "добавление оплаты"),
    ("Покупка",           "purchase",       "покупка",   "ecommerce: покупка"),
]

with st.spinner("Загрузка воронки..."):
    goals = get_goals()

    # Show goal debug expander
    with st.expander("🔍 Найденные цели (для отладки)", expanded=False):
        for stage, *kws in FUNNEL_DEF:
            gid = find_goal(goals, *kws)
            gname = next((g["name"] for g in goals if g["id"]==gid), "не найдено") if gid else "—"
            color = "🟢" if gid else "🔴"
            st.markdown(f"{color} **{stage}** → ID `{gid}` · *{gname}*")

    def build_funnel(d1, d2):
        total_d = stat(base_m, date1=d1, date2=d2, flt=c_flt)
        total = get_metric(total_d,0,0) or 1
        base_stage = "Все сеансы" if metric_mode == "Сеансам" else "Все пользователи"
        result = [{"stage": base_stage,"count":int(total),
                   "pct_from_sessions":100.0,
                   "pct_from_prev":None,
                   "over100":False,"gid":None}]
        for stage, *kws in FUNNEL_DEF:
            gid = find_goal(goals, *kws)
            if gid:
                d = stat(f"{base_m},ym:s:goal{gid}{goal_sfx}", date1=d1, date2=d2, flt=c_flt)
                count = int(get_metric(d,0,1) or 0)
            else:
                count = 0
            # % from ALL sessions (denominator = total always)
            pct_sessions = round(count/total*100, 2) if total else 0
            # % from PREVIOUS step (denominator = prev step count)
            prev_count = result[-1]["count"]
            pct_prev_raw = round(count/prev_count*100, 2) if prev_count else 0
            # cap at 100% — values over 100 mean users bypassed the step
            pct_prev = min(pct_prev_raw, 100.0)
            over100 = pct_prev_raw > 100.0
            result.append({
                "stage": stage,
                "count": count,
                "pct_from_sessions": pct_sessions,
                "pct_from_prev": pct_prev,
                "over100": over100,
                "gid": gid
            })
        return result

    rows_main = build_funnel(d1_main, d2_main)
    rows_cmp  = build_funnel(d1_cmp,  d2_cmp)

# ── Funnel: two tabs ──────────────────────────────────────────────────────────
FUNNEL_COLORS = ["#0d2035","#0d2a3d","#0c3545","#0a404d","#084b44","#065636","#046128"]

def build_funnel_fig_sessions(rows):
    """Classic funnel: bar width = absolute count, label shows % of sessions"""
    labels, values, bar_colors = [], [], []
    for i, r in enumerate(rows):
        pct = r["pct_from_sessions"]
        warn = " ⚠️" if r.get("over100") else ""
        label = f"<b>{r['stage']}</b>{warn}<br>{fmt(r['count'])}  ({pct}%)"
        labels.append(label)
        values.append(r["count"])
        bar_colors.append(FUNNEL_COLORS[i % len(FUNNEL_COLORS)])

    fig = go.Figure(go.Funnel(
        y=labels, x=values, textposition="inside", textinfo="none",
        marker=dict(color=bar_colors, line=dict(width=1, color="#0d0d0d")),
        connector=dict(line=dict(color="#1a1a1a", width=1)),
    ))
    fig.update_layout(
        paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d",
        font=dict(family="IBM Plex Mono", color="#ccc", size=11),
        margin=dict(l=10, r=10, t=10, b=10), height=420,
    )
    return fig

def build_funnel_fig_prev(rows):
    """Step-to-step: horizontal bar chart where bar = conversion % from prev step.
    First bar = Просмотр товара / Все сеансы. Shows WHERE the biggest drop-offs are."""
    stages, pcts, counts, bar_colors, texts = [], [], [], [], []
    for i, r in enumerate(rows[1:], 1):  # skip "Все сеансы" row
        pct = r["pct_from_prev"] or 0
        warn = " ⚠️" if r.get("over100") else ""
        prev = rows[i-1]
        # First stage label: show "из всех сеансов" instead of stage name
        prev_label = "всех сеансов" if prev["stage"] == "Все сеансы" else fmt(prev["count"])
        stage_label = r["stage"] + warn
        stages.append(stage_label)
        pcts.append(pct)
        counts.append(r["count"])
        texts.append(f"{pct}%  ({fmt(r['count'])} из {prev_label})")
        # Color by conversion: red=bad, yellow=medium, green=good
        if pct >= 70:
            bar_colors.append("#00e676")
        elif pct >= 40:
            bar_colors.append("#ffb300")
        else:
            bar_colors.append("#ff5252")

    fig = go.Figure(go.Bar(
        y=stages,
        x=pcts,
        orientation="h",
        marker_color=bar_colors,
        text=texts,
        textposition="outside",
        textfont=dict(family="IBM Plex Mono", size=11, color="#aaa"),
        cliponaxis=False,
    ))
    fig.add_vline(x=100, line_dash="dot", line_color="#333")
    fig.update_layout(
        paper_bgcolor="#0d0d0d", plot_bgcolor="#161616",
        font=dict(family="IBM Plex Mono", color="#888", size=11),
        margin=dict(l=10, r=180, t=10, b=10), height=360,
        xaxis=dict(range=[0, 115], ticksuffix="%",
                   gridcolor="#1e1e1e", zeroline=False),
        yaxis=dict(gridcolor="#1e1e1e", autorange="reversed"),
        showlegend=False,
    )
    return fig

def build_funnel_table(rows_m, rows_c, label_m, label_c, mode):
    table = []
    for rm, rc in zip(rows_m, rows_c):
        if mode == "sessions":
            val_m = rm["pct_from_sessions"]
            val_c = rc["pct_from_sessions"]
            d = val_m - val_c
            sign = "+" if d >= 0 else ""
            table.append({
                "Этап":                   rm["stage"],
                f"Визиты {label_m}":      fmt(rm["count"]),
                f"Визиты {label_c}":      fmt(rc["count"]),
                f"% {label_m}":           f"{val_m}%",
                f"% {label_c}":           f"{val_c}%",
                "Δ":                      f"{sign}{d:.1f}%",
            })
        else:
            val_m = rm["pct_from_prev"]
            val_c = rc["pct_from_prev"]
            warn = " ⚠️" if rm.get("over100") else ""
            if val_m is not None and val_c is not None:
                d = val_m - val_c
                sign = "+" if d >= 0 else ""
                delta_str = f"{sign}{d:.1f}%"
            else:
                delta_str = "—"
            table.append({
                "Этап":                   rm["stage"] + warn,
                f"Визиты {label_m}":      fmt(rm["count"]),
                f"Визиты {label_c}":      fmt(rc["count"]),
                f"шаг→шаг {label_m}":    f"{val_m}%" if val_m is not None else "база",
                f"шаг→шаг {label_c}":    f"{val_c}%" if val_c is not None else "база",
                "Δ шаг→шаг":             delta_str,
            })
    return pd.DataFrame(table)

period_label = f"Период: **{label_main}** vs **{label_cmp}**"
st.markdown(f'<div style="font-family:IBM Plex Mono,monospace;font-size:.65rem;'
            f'color:#555;margin-bottom:.5rem">📅 {label_main} vs {label_cmp}</div>',
            unsafe_allow_html=True)

st.markdown("""
<div style="background:#111;border:1px solid #222;border-radius:6px;
padding:.7rem 1rem;margin-bottom:.8rem;font-family:'IBM Plex Mono',monospace;
font-size:.65rem;color:#555">
  Выберите режим отображения воронки ↓
</div>""", unsafe_allow_html=True)

ftab1, ftab2, ftab3 = st.tabs([
    "📊  % ОТ ВСЕХ СЕАНСОВ — сколько из общего трафика дошли до каждого шага",
    "🔗  ШАГ→ШАГ — сколько % из прошедших предыдущий шаг перешли на следующий",
    "✅  ПОСЕССИОННО — только те, кто прошёл оба шага в одной сессии",
])

with ftab1:
    st.caption(f"🗓 {label_main} · Знаменатель каждого этапа = все сеансы за период")
    col_f, col_t = st.columns([5, 4])
    with col_f:
        st.plotly_chart(build_funnel_fig_sessions(rows_main),
                        use_container_width=True)
    with col_t:
        df_t = build_funnel_table(rows_main, rows_cmp, label_main, label_cmp, "sessions")
        st.dataframe(df_t, hide_index=True, use_container_width=True, height=420)

with ftab2:
    st.caption(
        f"🗓 {label_main} · "
        f"Корзина % = из тех, кто добавил в корзину. "
        f"Чекаут % = из тех, кто зашёл в корзину. И т.д."
    )
    col_f2, col_t2 = st.columns([5, 4])
    with col_f2:
        st.plotly_chart(build_funnel_fig_prev(rows_main),
                        use_container_width=True)
    with col_t2:
        df_t2 = build_funnel_table(rows_main, rows_cmp, label_main, label_cmp, "prev")
        st.dataframe(df_t2, hide_index=True, use_container_width=True, height=380)

with ftab3:
    st.caption(
        f"🗓 {label_main} · Знаменатель каждого шага = сессии где был достигнут предыдущий шаг. "
        f"Считается через составные цели Метрики — только одна сессия."
    )

    with st.spinner("Загрузка посессионных данных..."):
        pair_rows = []
        for pair_name, pair_gid, denom_kw in PAIR_GOALS:
            # Numerator: composite pair goal visits
            d_pair = stat(f"{base_m},ym:s:goal{pair_gid}{goal_sfx}",
                          date1=d1_main, date2=d2_main, flt=c_flt)
            pair_count = int(get_metric(d_pair, 0, 1) or 0)

            # Denominator: first stage visits
            denom_gid = find_goal(goals, denom_kw)
            if denom_kw == "cannabis-seeds":
                # First stage = all sessions with product view
                d_denom = stat(f"{base_m},ym:s:goal{denom_gid}{goal_sfx}",
                               date1=d1_main, date2=d2_main, flt=c_flt)
                denom_count = int(get_metric(d_denom, 0, 1) or 0)
            elif denom_gid:
                d_denom = stat(f"{base_m},ym:s:goal{denom_gid}{goal_sfx}",
                               date1=d1_main, date2=d2_main, flt=c_flt)
                denom_count = int(get_metric(d_denom, 0, 1) or 0)
            else:
                denom_count = 0

            pct = round(pair_count / denom_count * 100, 2) if denom_count else 0
            pair_rows.append({
                "name": pair_name,
                "pair_count": pair_count,
                "denom_count": denom_count,
                "pct": pct,
            })

    if pair_rows:
        # Bar chart
        fig_pair = go.Figure()
        bar_colors_pair = []
        for r in pair_rows:
            if r["pct"] >= 70: bar_colors_pair.append("#00e676")
            elif r["pct"] >= 40: bar_colors_pair.append("#ffb300")
            else: bar_colors_pair.append("#ff5252")

        fig_pair.add_trace(go.Bar(
            y=[r["name"] for r in pair_rows],
            x=[r["pct"] for r in pair_rows],
            orientation="h",
            marker_color=bar_colors_pair,
            text=[f"{r['pct']}%  ({fmt(r['pair_count'])} из {fmt(r['denom_count'])} в одной сессии)"
                  for r in pair_rows],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono", size=11, color="#aaa"),
            cliponaxis=False,
        ))
        fig_pair.add_vline(x=100, line_dash="dot", line_color="#333")
        fig_pair.update_layout(
            paper_bgcolor="#0d0d0d", plot_bgcolor="#161616",
            font=dict(family="IBM Plex Mono", color="#888", size=11),
            margin=dict(l=10, r=280, t=10, b=10), height=280,
            xaxis=dict(range=[0, 115], ticksuffix="%",
                       gridcolor="#1e1e1e", zeroline=False),
            yaxis=dict(gridcolor="#1e1e1e", autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(fig_pair, use_container_width=True)

        # Table
        df_pair = pd.DataFrame([{
            "Переход":                   r["name"],
            f"Прошли оба шага ({label_main})": fmt(r["pair_count"]),
            "Знаменатель (1-й шаг)":     fmt(r["denom_count"]),
            "Конверсия":                 f"{r['pct']}%",
        } for r in pair_rows])
        st.dataframe(df_pair, hide_index=True, use_container_width=True)

        st.markdown("""<div style='font-family:IBM Plex Mono,monospace;font-size:.6rem;
        color:#444;margin-top:.5rem'>
        ⚠️ Не хватает пар: Чекаут→Оплата и Оплата→Покупка — создай их в Метрике чтобы заполнить пробел
        </div>""", unsafe_allow_html=True)
    else:
        st.info("Нет данных по составным целям.")

# ══════════════════════════════════════════════════════════════════════════════
# БЛОК 3 — Конверсия по дням для каждого этапа воронки
# ══════════════════════════════════════════════════════════════════════════════
if d1_main != d2_main or mode == "Выбрать даты":
    st.markdown('<div class="sec">◈ конверсия по дням — каждый этап воронки (% от сеансов)</div>',
                unsafe_allow_html=True)
    with st.spinner("Загрузка дневных данных..."):
        vis_daily_d = stat(base_m, dims="ym:s:date",
                         date1=d1_main, date2=d2_main, flt=c_flt, limit=90)
        vis_by_day_d = {}
        if "data" in vis_daily_d:
            for row in vis_daily_d["data"]:
                vis_by_day_d[row["dimensions"][0]["name"]] = row["metrics"][0]

        stage_daily = {}
        for stage, *kws in FUNNEL_DEF:
            gid = find_goal(goals, *kws)
            if not gid:
                continue
            d = stat(f"{base_m},ym:s:goal{gid}{goal_sfx}", dims="ym:s:date",
                     date1=d1_main, date2=d2_main, flt=c_flt, limit=90)
            if "data" in d:
                stage_daily[stage] = {
                    row["dimensions"][0]["name"]: row["metrics"][1]
                    for row in d["data"]
                }

    all_days = sorted(vis_by_day_d.keys())
    ordered_stages = [s for s, *_ in FUNNEL_DEF if s in stage_daily]

    def make_daily_fig(mode_tab):
        fig = go.Figure()
        prev_vals = None
        # Format dates as "DD.MM" for category axis — avoids Plotly treating as datetime
        x_labels = [d[8:10] + "." + d[5:7] for d in all_days]
        for i, stage in enumerate(ordered_stages):
            color = STAGE_COLORS[i % len(STAGE_COLORS)]
            day_vals = stage_daily.get(stage, {})
            y_vals = []
            for day in all_days:
                total_vis = vis_by_day_d.get(day, 0)
                goal_cnt  = day_vals.get(day, 0)
                if mode_tab == "sessions":
                    y = round(goal_cnt / total_vis * 100, 2) if total_vis else 0
                else:
                    if prev_vals:
                        prev_cnt = prev_vals.get(day, 0)
                        y = round(goal_cnt / prev_cnt * 100, 2) if prev_cnt else 0
                        y = min(y, 100.0)
                    else:
                        y = round(goal_cnt / total_vis * 100, 2) if total_vis else 0
                y_vals.append(y)
            fig.add_trace(go.Scatter(
                x=x_labels, y=y_vals, mode="lines+markers",
                name=stage,
                line=dict(color=color, width=2),
                marker=dict(size=5, color=color),
                hovertemplate=f"<b>{stage}</b><br>%{{x}}<br>%{{y:.2f}}%<extra></extra>",
            ))
            prev_vals = day_vals
        fig.update_layout(
            paper_bgcolor="#0d0d0d", plot_bgcolor="#161616",
            font=dict(family="IBM Plex Mono", color="#888", size=10),
            margin=dict(l=10, r=10, t=10, b=10), height=320,
            xaxis=dict(type="category", gridcolor="#1e1e1e", zeroline=False,
                       tickangle=-45 if len(all_days) > 10 else 0),
            yaxis=dict(gridcolor="#1e1e1e", zeroline=False, ticksuffix="%"),
            legend=dict(bgcolor="#161616", bordercolor="#222", borderwidth=1,
                        font=dict(size=9), orientation="h",
                        yanchor="bottom", y=1.02, xanchor="left", x=0),
            hovermode="x unified",
        )
        return fig

    if all_days and stage_daily:
        tab1, tab2 = st.tabs(["📊 % от всех сеансов", "🔗 % от предыдущего шага"])
        with tab1:
            st.caption(f"Каждый этап: какой % от всех {base_label} за день достиг этого шага")
            st.plotly_chart(make_daily_fig("sessions"), use_container_width=True)
        with tab2:
            st.caption("Каждый этап: какой % прошедших предыдущий шаг дошёл до этого")
            st.plotly_chart(make_daily_fig("prev_step"), use_container_width=True)
    else:
        st.info("Нет данных по целям за выбранный период.")

# ══════════════════════════════════════════════════════════════════════════════
# БЛОК 3b — Конверсия между двумя выбранными этапами
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sec">◈ конверсия между двумя этапами — по дням</div>',
            unsafe_allow_html=True)

stage_names = [("Все сеансы" if metric_mode=="Сеансам" else "Все пользователи")] + [s for s, *_ in FUNNEL_DEF]

col_s1, col_s2 = st.columns(2)
with col_s1:
    stage_from = st.selectbox("📍 Откуда (знаменатель)", stage_names,
                              index=3, key="sf")   # default: Чекаут
with col_s2:
    stage_to   = st.selectbox("🏁 Куда (числитель)",   stage_names,
                              index=5, key="st")   # default: Покупка

if stage_from == stage_to:
    st.warning("Выбери два разных этапа.")
else:
    with st.spinner(""):
        # Get daily data for both stages
        def get_daily_counts(stage_name):
            base_stage_name = "Все сеансы" if metric_mode=="Сеансам" else "Все пользователи"
            if stage_name == base_stage_name:
                d = stat(base_m, dims="ym:s:date",
                         date1=d1_main, date2=d2_main, flt=c_flt, limit=90)
                if "data" in d:
                    return {r["dimensions"][0]["name"]: r["metrics"][0]
                            for r in d["data"]}
                return {}
            else:
                kws = next((list(kw) for s, *kw in FUNNEL_DEF if s == stage_name), [])
                gid = find_goal(goals, *kws) if kws else None
                if not gid:
                    return {}
                d = stat(f"{base_m},ym:s:goal{gid}{goal_sfx}", dims="ym:s:date",
                         date1=d1_main, date2=d2_main, flt=c_flt, limit=90)
                if "data" in d:
                    return {r["dimensions"][0]["name"]: r["metrics"][1]
                            for r in d["data"]}
                return {}

        from_vals = get_daily_counts(stage_from)
        to_vals   = get_daily_counts(stage_to)

    all_conv_days = sorted(set(from_vals) | set(to_vals))
    conv_pcts = []
    for day in all_conv_days:
        f = from_vals.get(day, 0)
        t = to_vals.get(day, 0)
        conv_pcts.append(round(t / f * 100, 2) if f else 0)

    if all_conv_days:
        avg_conv = round(sum(conv_pcts) / len(conv_pcts), 2) if conv_pcts else 0

        # Summary metric
        total_from = sum(from_vals.values())
        total_to   = sum(to_vals.values())
        total_pct  = round(total_to / total_from * 100, 2) if total_from else 0

        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown(f"""<div class="kpi">
              <div class="kpi-label">{stage_from} (всего)</div>
              <div class="kpi-val">{fmt(total_from)}</div>
            </div>""", unsafe_allow_html=True)
        with mc2:
            st.markdown(f"""<div class="kpi">
              <div class="kpi-label">{stage_to} (всего)</div>
              <div class="kpi-val">{fmt(total_to)}</div>
            </div>""", unsafe_allow_html=True)
        with mc3:
            st.markdown(f"""<div class="kpi">
              <div class="kpi-label">{stage_from} → {stage_to}</div>
              <div class="kpi-val">{total_pct}%</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

        # Daily line chart
        # Format as "DD.MM" to avoid datetime axis issues
        x_conv = [d[8:10] + "." + d[5:7] for d in all_conv_days]

        fig_conv = go.Figure()
        fig_conv.add_trace(go.Scatter(
            x=x_conv, y=conv_pcts,
            mode="lines+markers",
            line=dict(color="#00e676", width=2),
            marker=dict(size=6, color="#00e676"),
            fill="tozeroy", fillcolor="rgba(0,230,118,0.06)",
            hovertemplate="%{x}<br><b>%{y:.2f}%</b><extra></extra>",
        ))
        fig_conv.add_hline(y=avg_conv, line_dash="dot", line_color="#444",
                           annotation_text=f"среднее {avg_conv}%",
                           annotation_font=dict(color="#555", size=9))
        fig_conv.update_layout(
            paper_bgcolor="#0d0d0d", plot_bgcolor="#161616",
            font=dict(family="IBM Plex Mono", color="#888", size=10),
            margin=dict(l=10, r=10, t=10, b=10), height=240,
            xaxis=dict(type="category", gridcolor="#1e1e1e", zeroline=False,
                       tickangle=-45 if len(all_conv_days) > 10 else 0),
            yaxis=dict(gridcolor="#1e1e1e", zeroline=False, ticksuffix="%"),
            title=dict(
                text=f"{stage_from} → {stage_to}  ·  {label_main}",
                font=dict(family="IBM Plex Mono", size=11, color="#555"),
                x=0,
            ),
            showlegend=False,
        )
        st.plotly_chart(fig_conv, use_container_width=True)
    else:
        st.info("Нет данных для выбранных этапов за указанный период.")

# ══════════════════════════════════════════════════════════════════════════════
# БЛОК 4 — Источники трафика
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sec">◈ источники трафика</div>', unsafe_allow_html=True)
with st.spinner(""):
    src_m = stat("ym:s:visits", dims="ym:s:trafficSource",
                 date1=d1_main, date2=d2_main, flt=c_flt, limit=20)
    src_c = stat("ym:s:visits", dims="ym:s:trafficSource",
                 date1=d1_cmp,  date2=d2_cmp,  flt=c_flt, limit=20)

if "data" in src_m and src_m["data"]:
    def to_df(d):
        return pd.DataFrame([
            {"src": r["dimensions"][0].get("name","?"), "v": int(r["metrics"][0])}
            for r in d.get("data",[])
        ])
    df_m = to_df(src_m); df_c = to_df(src_c)
    df_mg = df_m.merge(df_c, on="src", how="outer",
                       suffixes=("_A","_B")).fillna(0).sort_values("v_A",ascending=False)
    top = df_mg.head(8)

    col1, col2 = st.columns([3,2])
    with col1:
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            y=top["src"], x=top["v_A"], orientation="h", name=label_main,
            marker_color="#00e676",
            text=[fmt(v) for v in top["v_A"]], textposition="outside",
            textfont=dict(size=9,color="#888")))
        fig2.add_trace(go.Bar(
            y=top["src"], x=top["v_B"], orientation="h", name=label_cmp,
            marker_color="#1a4a2e",
            text=[fmt(v) for v in top["v_B"]], textposition="outside",
            textfont=dict(size=9,color="#555")))
        fig2.update_layout(
            barmode="group", paper_bgcolor="#0d0d0d", plot_bgcolor="#161616",
            font=dict(family="IBM Plex Mono",color="#888",size=10),
            margin=dict(l=10,r=60,t=10,b=10), height=300,
            xaxis=dict(gridcolor="#1e1e1e",zeroline=False),
            yaxis=dict(gridcolor="#1e1e1e"),
            legend=dict(bgcolor="#161616",font=dict(size=9)))
        st.plotly_chart(fig2, use_container_width=True)
    with col2:
        df_show = top[["src","v_A","v_B"]].copy()
        df_show.columns = ["Источник", label_main, label_cmp]
        df_show["Δ"] = (df_show[label_main] - df_show[label_cmp]).astype(int)
        st.dataframe(df_show, hide_index=True, use_container_width=True, height=300)

# ══════════════════════════════════════════════════════════════════════════════
# БЛОК 5 — Визиты по часам
# ══════════════════════════════════════════════════════════════════════════════
if d1_main == d2_main:
    st.markdown('<div class="sec">◈ визиты по часам — сегодня</div>',
                unsafe_allow_html=True)
    with st.spinner(""):
        hour_data = stat(base_m, dims="ym:s:hour",
                         date1=d1_main, date2=d2_main, flt=c_flt, limit=24)
    if "data" in hour_data and hour_data["data"]:
        # Parse and sort hours, fill missing with 0
        raw_hours = {}
        for row in hour_data["data"]:
            raw = row["dimensions"][0].get("name","0")
            h = int(str(raw).split(":")[0])
            raw_hours[h] = int(row["metrics"][0])
        # Fill all hours 0..current_hour
        max_h = max(raw_hours.keys()) if raw_hours else datetime.now().hour
        hours = list(range(0, max_h + 1))
        visits = [raw_hours.get(h, 0) for h in hours]
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=hours, y=visits, mode="lines+markers",
            line=dict(color="#00b0ff",width=2),
            marker=dict(size=5,color="#00b0ff"),
            fill="tozeroy", fillcolor="rgba(0,176,255,0.06)"))
        fig3.add_vline(x=datetime.now().hour, line_dash="dot",
                       line_color="#333",
                       annotation_text="сейчас",
                       annotation_font=dict(color="#444",size=9))
        fig3.update_layout(
            paper_bgcolor="#0d0d0d", plot_bgcolor="#161616",
            font=dict(family="IBM Plex Mono",color="#888",size=10),
            margin=dict(l=10,r=10,t=10,b=10), height=200,
            xaxis=dict(tickmode="linear",dtick=2,gridcolor="#1e1e1e",
                       zeroline=False,title="Час (МСК)"),
            yaxis=dict(gridcolor="#1e1e1e",zeroline=False),
            showlegend=False)
        st.plotly_chart(fig3, use_container_width=True)

st.markdown(
    f'<div class="ts">↻ автообновление каждые 15 мин · '
    f'{datetime.now().strftime("%d.%m.%Y %H:%M:%S")}</div>',
    unsafe_allow_html=True)
