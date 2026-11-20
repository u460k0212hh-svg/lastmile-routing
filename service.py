"""웹 서비스(app.py)가 쓰는 계산 기능 모음 - 화면과 계산을 분리해 두면 테스트와 수정이 쉽다."""
import random

import numpy as np
import pandas as pd
import networkx as nx

from dijkstra import distance_matrix
from cvrp import run_all, route_cost, savings, improve_routes, check
from dijkstra import haversine

BASELINE = "기준(구역 분할)"
MAX_SNAP_M = 300   # 업로드 좌표가 가장 가까운 교차로에서 이보다 멀면 거부
VEH_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
              "#f032e6", "#9a6324", "#469990", "#000075", "#808000", "#800000"]


def prepare_network(G, depot_latlon=None):
    """도로망에서 왕복 가능한 가장 큰 영역만 남기고, 터미널 교차로를 정한다.
    depot_latlon이 없으면 지역 중심에서 가장 가까운 교차로를 '임시 터미널'로 쓴다.
    반환: (G, 터미널 교차로, 터미널에서 교차로까지 거리 m, 임시 여부)"""
    import osmnx as ox
    try:
        G = ox.truncate.largest_component(G, strongly=True)
    except AttributeError:
        G = ox.utils_graph.get_largest_component(G, strongly=True)
    temp = depot_latlon is None
    if temp:
        ys = [d["y"] for _, d in G.nodes(data=True)]
        xs = [d["x"] for _, d in G.nodes(data=True)]
        depot_latlon = (sum(ys) / len(ys), sum(xs) / len(xs))
    node = int(ox.distance.nearest_nodes(G, X=depot_latlon[1], Y=depot_latlon[0]))
    snap = haversine(depot_latlon[0], depot_latlon[1], G.nodes[node]["y"], G.nodes[node]["x"])
    return G, node, snap, temp


def download_network(query):
    """OpenStreetMap에서 지역 차도 도로망을 내려받는다 (수십 초~1분 이상 걸릴 수 있음)"""
    import osmnx as ox
    return ox.graph_from_place(query, network_type="drive")


def random_scenario(G, adj, depot, n_points, dmin, dmax, seed):
    rnd = random.Random(seed)
    cands = [n for n in G.nodes if n != depot]
    nodes = [depot] + rnd.sample(cands, n_points)
    demand = [0] + [rnd.randint(dmin, dmax) for _ in range(n_points)]
    return _finish(G, adj, nodes, demand, names=[f"배송지 {i}" for i in range(1, n_points + 1)])


def upload_scenario(G, adj, depot, df):
    """CSV(lat, lon, [boxes], [name])로 받은 실제 배송지를 가장 가까운 교차로에 맞춘다."""
    import osmnx as ox
    df = df.rename(columns=str.lower)
    if not {"lat", "lon"} <= set(df.columns):
        raise ValueError("CSV에 lat, lon 열이 있어야 합니다")
    lat = pd.to_numeric(df["lat"], errors="coerce")
    lon = pd.to_numeric(df["lon"], errors="coerce")
    if lat.isna().any() or lon.isna().any():
        raise ValueError("lat, lon에 숫자가 아닌 값이 있습니다")
    snapped = ox.distance.nearest_nodes(G, X=lon.tolist(), Y=lat.tolist())
    far = [i + 1 for i, (y, x, n) in enumerate(zip(lat, lon, snapped))
           if haversine(y, x, G.nodes[n]["y"], G.nodes[n]["x"]) > MAX_SNAP_M]
    if far:
        raise ValueError(f"도로망에서 {MAX_SNAP_M}m 넘게 떨어진 좌표가 있습니다 (CSV {far[:10]}번째 행). "
                         "미추홀구 안의 좌표인지 확인하세요")
    nodes = [depot] + [int(x) for x in snapped]
    if "boxes" in df.columns:
        b = pd.to_numeric(df["boxes"], errors="coerce")
        if b.isna().any() or (b < 1).any() or (b % 1 != 0).any():
            raise ValueError("boxes는 1 이상의 정수여야 합니다")
        boxes = b.astype(int).tolist()
    else:
        boxes = [1] * len(df)
    names = df["name"].astype(str).tolist() if "name" in df.columns else [f"배송지 {i}" for i in range(1, len(df) + 1)]
    return _finish(G, adj, nodes, [0] + boxes, names)


def _finish(G, adj, nodes, demand, names):
    M = distance_matrix(adj, nodes)
    if not np.isfinite(np.array(M)).all():
        raise ValueError("도로로 도달할 수 없는 배송지가 있습니다")
    return {"nodes": nodes, "demand": demand, "M": M, "names": ["터미널"] + names,
            "lats": [G.nodes[n]["y"] for n in nodes], "lons": [G.nodes[n]["x"] for n in nodes]}


def solve(sc, capacity, use_ortools, ortools_seconds):
    """반환: (결과 dict, 경고 메시지 또는 None)"""
    if max(sc["demand"]) > capacity:
        raise ValueError("한 배송지의 박스 수가 차량 용량보다 큽니다")
    res = run_all(sc["M"], sc["lats"], sc["lons"], sc["demand"], capacity, use_ortools=False)
    warn = None
    if use_ortools:
        try:
            routes, sec = ortools_subprocess(sc["M"], sc["demand"], capacity, ortools_seconds)
            res["OR-Tools(비교 기준)"] = (routes, sum(route_cost(r, sc["M"]) for r in routes), sec)
        except Exception as e:
            warn = f"OR-Tools 비교를 실행하지 못했습니다: {e}"
    # 화면에 보여주기 전에 모든 계획의 유효성 검사 (누락·중복 방문, 용량 초과, 출발·복귀)
    for name, (routes, _, _) in res.items():
        try:
            check(routes, sc["demand"], capacity, len(sc["nodes"]))
        except AssertionError as e:
            raise ValueError(f"'{name}' 결과가 유효성 검사를 통과하지 못했습니다: {e}")
    return res, warn


def ortools_subprocess(M, demand, capacity, seconds):
    """OR-Tools를 별도 파이썬 프로세스로 실행 (Windows DLL 충돌 회피)"""
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    t = time.time()
    p = subprocess.run([sys.executable, os.path.join(here, "ortools_worker.py")],
                       input=json.dumps({"M": M, "demand": demand, "capacity": capacity, "seconds": seconds}),
                       capture_output=True, text=True, cwd=here, timeout=seconds + 120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "알 수 없는 오류")
    return json.loads(p.stdout.strip().splitlines()[-1]), time.time() - t


def compare_table(res, sc):
    M = sc["M"]
    base = res[BASELINE][1]
    rows = []
    for name, (routes, d, sec) in res.items():
        lens = [route_cost(r, M) / 1000 for r in routes]
        rows.append({"방식": name, "차량 수": len(routes), "총 거리(km)": round(d / 1000, 2),
                     "구역 분할 대비 감소(%)": round((1 - d / base) * 100, 1),
                     "최장–최단 경로 차이(km)": round(max(lens) - min(lens), 2),
                     "경로 계산 시간(초)": sec})
    return pd.DataFrame(rows)


def vehicle_table(routes, sc, capacity):
    M, dem = sc["M"], sc["demand"]
    rows = []
    for v, r in enumerate(routes):
        boxes = sum(dem[k] for k in r)
        rows.append({"호차": f"{v + 1}호차", "배송지 수": len(r) - 2, "박스": boxes,
                     "적재율(%)": round(boxes / capacity * 100), "거리(km)": round(route_cost(r, M) / 1000, 2),
                     "방문 순서": " → ".join(sc["names"][k] for k in r)})
    return pd.DataFrame(rows)


def leg_paths(G, sc, routes):
    """차량별 실제 도로 좌표 목록 (지도 그리기용)"""
    nodes = sc["nodes"]
    out = []
    for r in routes:
        coords = []
        for a, b in zip(r[:-1], r[1:]):
            p = nx.shortest_path(G, nodes[a], nodes[b], weight="length")
            coords += [(G.nodes[x]["y"], G.nodes[x]["x"]) for x in p]
        out.append(coords)
    return out


def build_map(G, sc, routes, show_roads=False):
    import folium
    from basemap import add_road_background
    m = folium.Map(location=[float(np.mean(sc["lats"])), float(np.mean(sc["lons"]))],
                   zoom_start=14, tiles="OpenStreetMap")
    add_road_background(m, G, show=show_roads)
    stop_vehicle = {}
    for v, (r, coords) in enumerate(zip(routes, leg_paths(G, sc, routes))):
        color = VEH_COLORS[v % len(VEH_COLORS)]
        layer = folium.FeatureGroup(name=f"{v + 1}호차 ({route_cost(r, sc['M']) / 1000:.1f}km)")
        folium.PolyLine(coords, color=color, weight=5, opacity=0.85).add_to(layer)
        layer.add_to(m)
        for order, k in enumerate(r[1:-1], start=1):
            stop_vehicle[k] = (v, order, color)
    for k, (v, order, color) in stop_vehicle.items():
        folium.CircleMarker([sc["lats"][k], sc["lons"][k]], radius=6, color="black", weight=1,
                            fill=True, fill_color=color, fill_opacity=1,
                            tooltip=f"{sc['names'][k]} | {v + 1}호차 {order}번째 | {sc['demand'][k]}박스").add_to(m)
    folium.Marker([sc["lats"][0], sc["lons"][0]], tooltip="터미널",
                  icon=folium.Icon(color="red", icon="home")).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def capacity_analysis(sc, capacities):
    """차량 용량을 바꿔 가며 세이빙 + 순서 개선 결과를 비교 (차를 키우면 얼마나 이득인가)"""
    M, dem = sc["M"], sc["demand"]
    rows = []
    for cap in capacities:
        if cap < max(dem):
            continue
        routes = improve_routes(savings(M, dem, cap), M)
        lens = [route_cost(r, M) / 1000 for r in routes]
        rows.append({"차량 용량(박스)": cap, "사용 차량 수": len(routes),
                     "총 거리(km)": round(sum(lens), 2), "가장 긴 경로(km)": round(max(lens), 2),
                     "차량 1대당 평균 거리(km)": round(sum(lens) / len(routes), 2)})
    return pd.DataFrame(rows)
