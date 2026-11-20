"""라스트마일 배송 경로 최적화 웹 서비스
실행: streamlit run app.py
"""
# 주의: 이 파일에서는 OR-Tools를 직접 불러오지 않는다.
# (Windows에서 표/그래프용 pyarrow와 DLL이 충돌 -> OR-Tools는 ortools_worker.py로 별도 실행)
import os

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import service as S

import regions as R

DATA = R.PRESETS["michuhol"]["data"]   # 반복 실험 결과는 미추홀구 사례 폴더

st.set_page_config(page_title="라스트마일 배송 경로 최적화", page_icon="🚚", layout="wide")


# ---------- 데이터 (한 번만 불러와 재사용) ----------
@st.cache_resource(show_spinner="저장된 도로망을 불러오는 중...")
def load_preset(key):
    """미리 준비한 지역: data 폴더의 도로망과 터미널을 불러온다"""
    import osmnx as ox
    from dijkstra import build_adjacency
    cfg = R.PRESETS[key]
    G = ox.load_graphml(os.path.join(cfg["data"], "graph.graphml"))
    pts = pd.read_csv(os.path.join(cfg["data"], "points.csv"))
    return G, build_adjacency(G), int(pts.node[0])


@st.cache_resource(show_spinner="OpenStreetMap에서 도로망을 내려받는 중... (수십 초~1분 이상)")
def load_live(query, depot_latlon):
    """그 밖의 지역: 도로망을 내려받고 터미널 교차로를 정한다"""
    from dijkstra import build_adjacency
    G, node, snap, temp = S.prepare_network(S.download_network(query), depot_latlon)
    return G, build_adjacency(G), node, snap, temp


def network():
    if REGION["kind"] == "preset":
        return load_preset(REGION["key"])
    G, adj, node, _, _ = load_live(REGION["query"], REGION["depot"])
    return G, adj, node


@st.cache_data(show_spinner="배송지 사이 도로 거리를 계산하는 중 (다익스트라)...")
def cached_random_scenario(region_id, n_points, dmin, dmax, seed):
    G, adj, depot = network()
    return S.random_scenario(G, adj, depot, n_points, dmin, dmax, seed)


@st.cache_data(show_spinner="업로드한 주소를 도로망에 맞추는 중...")
def cached_upload_scenario(region_id, csv_bytes):
    import io
    G, adj, depot = network()
    return S.upload_scenario(G, adj, depot, pd.read_csv(io.BytesIO(csv_bytes)))


def bar(df, cat, val, highlight=("세이빙 + 순서 개선", "다중 시작(같은 시간)")):
    """막대그래프: 방식 순서를 표와 같게 유지하고, 직접 구현한 최종 방식을 빨간색으로 강조"""
    d = df[[cat, val]].copy()
    d["hl"] = d[cat].isin(highlight)
    base = alt.Chart(d).encode(
        y=alt.Y(f"{cat}:N", sort=None, title=None, axis=alt.Axis(labelLimit=320)),
        x=alt.X(f"{val}:Q", title=val))
    bars = base.mark_bar().encode(color=alt.condition(alt.datum.hl, alt.value("#ff4b4b"), alt.value("#9db4d6")))
    text = base.mark_text(align="left", dx=4).encode(text=alt.Text(f"{val}:Q", format=".2f"))
    st.altair_chart((bars + text).properties(height=45 * len(d) + 30))


def fmt_sec(s):
    """경로 계산 시간 표시: 반올림하면 0이 되는 값은 <0.001초로"""
    return "<0.001 초" if s < 0.001 else f"{s:.3f} 초"


def line(df, cols, x="차량 용량(박스)"):
    """확대/이동이 안 되는 고정 꺾은선 그래프 (발표 중 실수로 화면이 움직이지 않도록)"""
    d = df[[x] + cols].melt(x, var_name="항목", value_name="값")
    return alt.Chart(d).mark_line(point=True).encode(
        x=alt.X(f"{x}:Q", scale=alt.Scale(domain=[df[x].min(), df[x].max()]), title=x),
        y=alt.Y("값:Q", scale=alt.Scale(zero=True), title=None),
        color=alt.Color("항목:N", legend=alt.Legend(orient="bottom", title=None)),
        tooltip=[x, "항목", "값"]).properties(height=320)


# ---------- 사이드바: 지역 ----------
st.sidebar.title("📍 지역과 터미널")
ready = {k: v for k, v in R.PRESETS.items()
         if v["depot"] is not None and os.path.exists(os.path.join(v["data"], "graph.graphml"))}
OTHER = "다른 지역 불러오기"
choice = st.sidebar.selectbox("지역", [v["label"] for v in ready.values()] + [OTHER])
if choice != OTHER:
    key = next(k for k, v in ready.items() if v["label"] == choice)
    cfg = R.PRESETS[key]
    REGION = {"kind": "preset", "key": key, "id": key, "label": cfg["label"],
              "depot_name": cfg["depot_name"], "case_study": cfg["case_study"], "temp": False}
    st.sidebar.caption(f"터미널: {cfg['depot_name']}")
else:
    city = st.sidebar.selectbox("시", list(R.CITIES))
    gu = st.sidebar.selectbox("구", R.CITIES[city])
    use_xy = st.sidebar.checkbox("터미널 좌표 직접 입력", value=False)
    depot_xy = None
    if use_xy:
        lat = st.sidebar.number_input("터미널 위도", value=37.5, format="%.6f")
        lon = st.sidebar.number_input("터미널 경도", value=127.0, format="%.6f")
        depot_xy = (float(lat), float(lon))
    else:
        st.sidebar.caption("입력하지 않으면 지역 중심 근처 교차로를 임시 터미널로 씁니다.")
    if "loaded" not in st.session_state or st.session_state.loaded[:3] != (city, gu, depot_xy):
        st.session_state.pop("loaded_ok", None)
    if st.sidebar.button("이 지역 불러오기", type="primary"):
        st.session_state.loaded = (city, gu, depot_xy)
        st.session_state.loaded_ok = True
    if not st.session_state.get("loaded_ok"):
        st.info("왼쪽에서 시·구를 고르고 **이 지역 불러오기**를 누르세요. 처음 불러오는 지역은 도로망을 "
                "내려받느라 수십 초~1분 이상 걸릴 수 있습니다.")
        st.stop()
    REGION = {"kind": "live", "query": R.place_query(city, gu), "depot": depot_xy,
              "id": f"{city}-{gu}-{depot_xy}", "label": f"{city} {gu}", "case_study": False}
    try:
        _, _, _, snap, temp = load_live(REGION["query"], depot_xy)
    except Exception as e:
        st.error(f"도로망을 불러오지 못했습니다: {e}")
        st.stop()
    REGION["temp"] = temp
    REGION["depot_name"] = "임시 터미널 (지역 중심 근처)" if temp else "직접 입력한 좌표"
    if snap > 500:
        st.sidebar.warning(f"터미널이 도로망에서 {snap:.0f}m 떨어져 있습니다. 지역 안의 좌표인지 확인하세요.")

G, adj, depot = network()

# ---------- 사이드바: 배송 조건 ----------
st.sidebar.title("🚚 배송 조건")
src = st.sidebar.radio("배송지", ["무작위 생성", "CSV 업로드"])
if src == "무작위 생성":
    n_points = st.sidebar.slider("배송지 수", 10, 150, 100, step=10)
    dmin, dmax = st.sidebar.slider("배송지별 박스 수", 1, 10, (1, 3))
    seed = st.sidebar.number_input("시나리오 번호 (같은 번호 = 같은 배송지)", 0, 9999, 7)
    sc = cached_random_scenario(REGION["id"], n_points, dmin, dmax, int(seed))
else:
    up = st.sidebar.file_uploader("CSV (열: lat, lon, boxes, name)", type="csv")
    st.sidebar.caption(f"boxes, name은 생략 가능. {REGION['label']} 안의 좌표여야 합니다.")
    if up is None:
        st.info("왼쪽에서 배송지 CSV를 올려주세요.")
        st.stop()
    try:
        sc = cached_upload_scenario(REGION["id"], up.getvalue())
    except Exception as e:
        st.error(f"CSV를 읽지 못했습니다: {e}")
        st.stop()

capacity = st.sidebar.slider("차량 1대 적재 한도 (박스)", 10, 200, 60, step=5)
use_ortools = st.sidebar.checkbox("OR-Tools와 비교 (느림)", value=False)
ort_sec = st.sidebar.slider("OR-Tools 제한 시간(초)", 1, 10, 3) if use_ortools else 3
show_roads = st.sidebar.checkbox("도로망 레이어 켜기", value=False)

total_boxes = sum(sc["demand"])
st.sidebar.markdown(f"**총 {len(sc['nodes']) - 1}곳 · {total_boxes}박스**  \n"
                    f"총수요 기준 하한: {-(-total_boxes // capacity)}대 (박스 합 ÷ 용량, 올림)")

try:
    with st.spinner("경로 계산 중..." + (" (OR-Tools 포함)" if use_ortools else "")):
        res, warn = S.solve(sc, capacity, use_ortools, ort_sec)
except ValueError as e:
    st.error(str(e))
    st.stop()
if warn:
    st.sidebar.warning(warn)

# ---------- 본문 ----------
st.title("라스트마일 배송 경로 최적화")
st.caption(f"{REGION['label']} 실제 도로망(OpenStreetMap) · 터미널: {REGION['depot_name']} · "
           "다익스트라 도로 거리 · 세이빙 알고리즘 + 2-opt/Or-opt")
if REGION.get("temp"):
    st.warning("임시 터미널(지역 중심 근처)을 사용 중입니다. 실제 터미널 위치가 아닙니다.")

tab1, tab2, tab3, tab4 = st.tabs(["🗺️ 배송 경로", "📊 알고리즘 비교", "🚛 차량 용량 분석", "🧪 반복 실험 결과"])

with tab1:
    methods = list(res.keys())
    method = st.selectbox("경로 계산 방식", methods, index=methods.index("세이빙 + 순서 개선"))
    routes, dist, sec = res[method]
    base = res[S.BASELINE][1]
    lens = [S.route_cost(r, sc["M"]) / 1000 for r in routes]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 이동 거리", f"{dist / 1000:.1f} km",
              f"{(dist / base - 1) * 100:+.1f}% · 구역 분할 방식 대비", delta_color="inverse")
    c2.metric("사용 차량", f"{len(routes)} 대")
    c3.metric("최장–최단 차량 경로 차이", f"{max(lens) - min(lens):.1f} km")
    c4.metric("경로 계산 시간", fmt_sec(sec))
    st.caption("위 수치는 현재 시나리오 1개의 결과입니다. 여러 시나리오의 평균은 '반복 실험 결과' 탭을 보세요. "
               "경로 계산 시간은 도로 거리 계산과 지도 표시 시간을 제외한 값입니다.")
    components.html(S.build_map(G, sc, routes, show_roads)._repr_html_(), height=560)
    st.subheader("차량별 배송 계획")
    st.markdown(" &nbsp; ".join(
        f'<span style="color:{S.VEH_COLORS[v % len(S.VEH_COLORS)]};font-size:1.3em">●</span> {v + 1}호차'
        for v in range(len(routes))), unsafe_allow_html=True)
    st.dataframe(S.vehicle_table(routes, sc, capacity), hide_index=True)

with tab2:
    st.subheader("같은 배송지, 다른 방식")
    df = S.compare_table(res, sc)
    show = df.copy()
    show["경로 계산 시간"] = show.pop("경로 계산 시간(초)").map(fmt_sec)
    st.dataframe(show, hide_index=True)
    bar(df, "방식", "총 거리(km)")
    if "OR-Tools(비교 기준)" in res:
        st.caption(f"OR-Tools는 탐색 제한 시간 {ort_sec}초 조건의 결과이며, 최적해를 보장하는 기준이 아닙니다.")
    st.markdown(
        "- **기준(구역 분할)**: 터미널 기준 방향별로 구역을 나눠 기사에게 배정, 구역 안에서는 가까운 곳부터\n"
        "- **순서 개선**: 2-opt(구간 뒤집기) + Or-opt(구간 옮기기). 일방통행으로 거리가 비대칭이라 Or-opt를 추가\n"
        "- **세이빙**: Clarke & Wright(1964). 두 경로를 이었을 때 절약되는 거리 d(i,0)+d(0,j)−d(i,j)가 큰 순서로 합침")

with tab3:
    st.subheader("차를 키우면 얼마나 이득인가?")
    st.caption("같은 배송지에서 차량 1대의 적재 한도만 바꿔 세이빙 + 순서 개선으로 계산")
    caps = list(range(max(20, max(sc["demand"])), 201, 10))
    cap_df = S.capacity_analysis(sc, caps)
    a, b = st.columns(2)
    a.markdown("**사용 차량 수 (대)** — 세이빙 방식이 만든 결과이며 증명된 최소 대수는 아님")
    a.altair_chart(line(cap_df, ["사용 차량 수"]))
    b.markdown("**총 거리 vs 가장 긴 차량 경로 (km)**")
    b.altair_chart(line(cap_df, ["총 거리(km)", "가장 긴 경로(km)"]))
    st.dataframe(cap_df, hide_index=True)
    st.info("이 시나리오에서 관찰된 변화입니다. 사용 차량 수와 총 거리가 줄어도 한 차량이 맡는 가장 긴 경로는 "
            "늘어날 수 있습니다. 근무시간이나 실제 업무 부담의 변화는 이 모델(주행거리)로 판단할 수 없습니다.")

with tab4:
    st.subheader("배송지 배치를 바꿔 반복한 실험 — 인천 미추홀구 사례")
    if not REGION.get("case_study"):
        st.info("반복 실험·OR-Tools 시간별 비교·검증은 인천 미추홀구(CJ대한통운 학익동 터미널) 사례에서 수행했습니다. "
                "아래 결과는 현재 선택한 지역의 결과가 아닙니다.")
    for fname, title in [("step2_experiment.csv", "차량 1대 (배송지 50곳 × 30개 시나리오, OR-Tools 탐색 제한 2초)"),
                         ("step3_experiment.csv", "차량 여러 대 (배송지 100곳 × 20개 시나리오, 용량 60박스, OR-Tools 탐색 제한 3초)")]:
        path = os.path.join(DATA, fname)
        if not os.path.exists(path):
            st.caption(f"{fname} 없음 (step2/step3 실험을 먼저 실행)")
            continue
        ex = pd.read_csv(path)
        names = [c[:-3] for c in ex.columns if c.endswith("_km")]
        summ = pd.DataFrame({"방식": names,
                             "평균 거리(km)": [ex[n + "_km"].mean().round(2) for n in names],
                             "평균 경로 계산 시간": [fmt_sec(ex[n + "_sec"].mean()) for n in names]})
        st.markdown(f"**{title}**")
        st.dataframe(summ, hide_index=True)
        bar(summ, "방식", "평균 거리(km)")

    path = os.path.join(DATA, "step4_ortools_time.csv")
    if os.path.exists(path):
        st.markdown("**추가 실험: OR-Tools 탐색 시간별 비교 (위 실험의 앞 5개 시나리오씩, 미리 고정)**")
        t4 = pd.read_csv(path)
        rows = []
        for prob, g in t4.groupby("문제", sort=False):
            ref = g["OR-Tools 30초_km"]
            for c in [c for c in g.columns if c.endswith("_km") and c != "OR-Tools 30초_km"]:
                if g[c].isna().all():
                    continue
                gap = (g[c] / ref - 1) * 100
                rows.append({"문제": prob, "방식": c[:-3], "OR-Tools 30초 대비 평균(%)": round(gap.mean(), 2),
                             "최악(%)": round(gap.max(), 2), "최선(%)": round(gap.min(), 2)})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption("+는 OR-Tools 30초 결과보다 길다는 뜻. 30초 결과도 최적해를 보장하는 기준이 아니며, "
                   "시나리오 5개씩의 소규모 비교입니다. '다중 시작 2초'는 2초 탐색 설정을 뜻합니다.")

st.caption("지도 데이터 © OpenStreetMap contributors")
