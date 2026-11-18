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

DATA = "data"
st.set_page_config(page_title="라스트마일 배송 경로 최적화", page_icon="🚚", layout="wide")


# ---------- 데이터 (한 번만 불러와 재사용) ----------
@st.cache_resource(show_spinner="도로망을 불러오는 중...")
def load_network():
    import osmnx as ox
    from dijkstra import build_adjacency
    G = ox.load_graphml(os.path.join(DATA, "graph.graphml"))
    pts = pd.read_csv(os.path.join(DATA, "points.csv"))
    return G, build_adjacency(G), int(pts.node[0])


@st.cache_data(show_spinner="배송지 사이 도로 거리를 계산하는 중 (다익스트라)...")
def cached_random_scenario(n_points, dmin, dmax, seed):
    G, adj, depot = load_network()
    return S.random_scenario(G, adj, depot, n_points, dmin, dmax, seed)


@st.cache_data(show_spinner="업로드한 주소를 도로망에 맞추는 중...")
def cached_upload_scenario(csv_bytes):
    import io
    G, adj, depot = load_network()
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


def line(df, cols, x="차량 용량(박스)"):
    """확대/이동이 안 되는 고정 꺾은선 그래프 (발표 중 실수로 화면이 움직이지 않도록)"""
    d = df[[x] + cols].melt(x, var_name="항목", value_name="값")
    return alt.Chart(d).mark_line(point=True).encode(
        x=alt.X(f"{x}:Q", scale=alt.Scale(domain=[df[x].min(), df[x].max()]), title=x),
        y=alt.Y("값:Q", scale=alt.Scale(zero=True), title=None),
        color=alt.Color("항목:N", legend=alt.Legend(orient="bottom", title=None)),
        tooltip=[x, "항목", "값"]).properties(height=320)


G, adj, depot = load_network()

# ---------- 사이드바: 입력 ----------
st.sidebar.title("🚚 배송 조건")
src = st.sidebar.radio("배송지", ["무작위 생성", "CSV 업로드"])
if src == "무작위 생성":
    n_points = st.sidebar.slider("배송지 수", 10, 150, 100, step=10)
    dmin, dmax = st.sidebar.slider("배송지별 박스 수", 1, 10, (1, 3))
    seed = st.sidebar.number_input("시나리오 번호 (같은 번호 = 같은 배송지)", 0, 9999, 7)
    sc = cached_random_scenario(n_points, dmin, dmax, int(seed))
else:
    up = st.sidebar.file_uploader("CSV (열: lat, lon, boxes, name)", type="csv")
    st.sidebar.caption("boxes, name은 생략 가능. 미추홀구 안의 좌표여야 합니다.")
    if up is None:
        st.info("왼쪽에서 배송지 CSV를 올려주세요.")
        st.stop()
    try:
        sc = cached_upload_scenario(up.getvalue())
    except Exception as e:
        st.error(f"CSV를 읽지 못했습니다: {e}")
        st.stop()

capacity = st.sidebar.slider("차량 1대 적재 한도 (박스)", 10, 200, 60, step=5)
use_ortools = st.sidebar.checkbox("OR-Tools와 비교 (느림)", value=False)
ort_sec = st.sidebar.slider("OR-Tools 제한 시간(초)", 1, 10, 3) if use_ortools else 3
show_roads = st.sidebar.checkbox("도로망 레이어 켜기", value=False)

total_boxes = sum(sc["demand"])
st.sidebar.markdown(f"**총 {len(sc['nodes']) - 1}곳 · {total_boxes}박스** → 최소 {-(-total_boxes // capacity)}대 필요")

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
st.caption("미추홀구 실제 도로망(OpenStreetMap) · 다익스트라 도로 거리 · 세이빙 알고리즘 + 2-opt/Or-opt")

tab1, tab2, tab3, tab4 = st.tabs(["🗺️ 배송 경로", "📊 알고리즘 비교", "🚛 차량 용량 분석", "🧪 반복 실험 결과"])

with tab1:
    methods = list(res.keys())
    method = st.selectbox("경로 계산 방식", methods, index=methods.index("세이빙 + 순서 개선"))
    routes, dist, sec = res[method]
    base = res[S.BASELINE][1]
    lens = [S.route_cost(r, sc["M"]) / 1000 for r in routes]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 이동 거리", f"{dist / 1000:.1f} km", f"{(dist / base - 1) * 100:+.1f}% (기준 대비)",
              delta_color="inverse")
    c2.metric("투입 차량", f"{len(routes)} 대")
    c3.metric("기사 간 거리 편차", f"{max(lens) - min(lens):.1f} km")
    c4.metric("계산 시간", f"{sec:.3f} 초")
    components.html(S.build_map(G, sc, routes, show_roads)._repr_html_(), height=560)
    st.subheader("차량별 배송 계획")
    st.dataframe(S.vehicle_table(routes, sc, capacity), hide_index=True)

with tab2:
    st.subheader("같은 배송지, 다른 방식")
    df = S.compare_table(res, sc)
    st.dataframe(df, hide_index=True)
    bar(df, "방식", "총 거리(km)")
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
    a.markdown("**필요 차량 수 (대)**")
    a.altair_chart(line(cap_df, ["필요 차량 수"]))
    b.markdown("**총 거리 vs 기사 1명의 최장 경로 (km)**")
    b.altair_chart(line(cap_df, ["총 거리(km)", "가장 긴 경로(km)"]))
    st.dataframe(cap_df, hide_index=True)
    st.info("차량이 커지면 필요 대수와 총 거리는 줄지만, 기사 1명이 맡는 경로(가장 긴 경로)는 길어진다. "
            "근무 시간 한도를 함께 고려해야 한다.")

with tab4:
    st.subheader("배송지 배치를 바꿔 반복한 실험")
    for fname, title in [("step2_experiment.csv", "차량 1대 (배송지 50곳 × 30개 시나리오)"),
                         ("step3_experiment.csv", "차량 여러 대 (배송지 100곳 × 20개 시나리오)")]:
        path = os.path.join(DATA, fname)
        if not os.path.exists(path):
            st.caption(f"{fname} 없음 (step2/step3 실험을 먼저 실행)")
            continue
        ex = pd.read_csv(path)
        names = [c[:-3] for c in ex.columns if c.endswith("_km")]
        summ = pd.DataFrame({"방식": names,
                             "평균 거리(km)": [ex[n + "_km"].mean().round(2) for n in names],
                             "평균 계산 시간(초)": [ex[n + "_sec"].mean().round(3) for n in names]})
        st.markdown(f"**{title}**")
        st.dataframe(summ, hide_index=True)
        bar(summ, "방식", "평균 거리(km)")

st.caption("지도 데이터 © OpenStreetMap contributors")
