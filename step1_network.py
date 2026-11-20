"""1단계: 미추홀구 도로망 내려받기 -> 배송지 생성 -> 다익스트라로 도로 거리행렬 계산

실행: python step1_network.py
결과: data/ 폴더에 graph.graphml, points.csv, dist_matrix.npy, step1_map.html
"""
import os
import random
import time

import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import folium

from basemap import make_map, add_road_background

from dijkstra import build_adjacency, dijkstra, distance_matrix, haversine

# ---------------- 설정 ----------------
# 지역·터미널은 regions.py에서 관리. 실행: python step1_network.py [지역키]  (기본: michuhol)
import sys
from regions import PRESETS
REGION = sys.argv[1] if len(sys.argv) > 1 else "michuhol"
CFG = PRESETS[REGION]
PLACE = CFG["place"]
DEPOT = CFG["depot"]          # 미추홀구: CJ대한통운 택배 남동A터미널, 학익동 587-190 (Plus Code CJQX+J8)
                              # 이전 실험(data_old_inha)은 인하대 인근 임의 좌표 (37.4505, 126.6536)
if DEPOT is None:
    raise SystemExit(f"regions.py에서 {REGION}의 터미널 좌표(depot)를 먼저 입력하세요.")
FALLBACK_CENTER = DEPOT
FALLBACK_RADIUS = 3000                          # m
N_POINTS = 50                                   # 배송지 개수
SEED = 42                                       # 같은 숫자면 항상 같은 배송지가 나옴
OUT = CFG["data"]
# --------------------------------------


def largest_strong_component(G):
    """일방통행 때문에 들어가면 못 나오는 구역이 있을 수 있어,
    서로 왕복 가능한 가장 큰 영역만 남긴다."""
    try:
        return ox.truncate.largest_component(G, strongly=True)       # osmnx 2.x
    except AttributeError:
        return ox.utils_graph.get_largest_component(G, strongly=True)  # osmnx 1.x


def load_graph():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "graph.graphml")
    if os.path.exists(path):
        print("저장된 도로망을 불러옵니다:", path)
        return ox.load_graphml(path)
    print("도로망을 내려받는 중... (1~2분 걸릴 수 있음)")
    try:
        G = ox.graph_from_place(PLACE, network_type="drive")
    except Exception as e:
        print("지명 검색 실패, 중심점 기준으로 내려받습니다:", e)
        G = ox.graph_from_point(FALLBACK_CENTER, dist=FALLBACK_RADIUS, network_type="drive")
    G = largest_strong_component(G)
    ox.save_graphml(G, path)
    return G


def main():
    G = load_graph()
    print(f"도로망: 교차로 {G.number_of_nodes():,}개, 도로 구간 {G.number_of_edges():,}개")

    # 출발점과 배송지를 도로망 위의 교차로에 맞춘다
    depot_node = ox.distance.nearest_nodes(G, X=DEPOT[1], Y=DEPOT[0])
    snap = haversine(DEPOT[0], DEPOT[1], G.nodes[depot_node]["y"], G.nodes[depot_node]["x"])
    print(f"터미널 좌표 -> 가장 가까운 교차로까지 직선 {snap:.0f}m")
    if snap > 300:
        print("[주의] 터미널이 도로망 교차로에서 300m 이상 떨어져 있습니다. 위치를 확인하세요.")
    random.seed(SEED)
    candidates = [n for n in G.nodes if n != depot_node]
    stops = random.sample(candidates, N_POINTS)
    nodes = [depot_node] + stops          # 0번 = 출발점

    pts = pd.DataFrame({
        "id": range(len(nodes)),
        "node": nodes,
        "lat": [G.nodes[n]["y"] for n in nodes],
        "lon": [G.nodes[n]["x"] for n in nodes],
        "type": ["depot"] + ["stop"] * N_POINTS,
    })
    pts.to_csv(os.path.join(OUT, "points.csv"), index=False)

    # 직접 구현한 다익스트라로 거리행렬 계산
    adj = build_adjacency(G)
    t = time.time()
    M = np.array(distance_matrix(adj, nodes))
    print(f"거리행렬 {M.shape} 계산: {time.time() - t:.2f}초 (직접 구현 다익스트라)")
    assert np.isfinite(M).all(), "도달 불가능한 배송지가 있습니다"
    np.save(os.path.join(OUT, "dist_matrix.npy"), M)

    # 검증: networkx 라이브러리 결과와 비교
    for s in nodes[:5]:
        mine = dijkstra(adj, s)
        ref = nx.single_source_dijkstra_path_length(G, s, weight="length")
        for t_ in nodes:
            assert abs(mine[t_] - ref[t_]) < 1e-6
    print("검증 통과: 직접 구현한 다익스트라 = networkx 결과")

    # 발표용 수치: 직선거리 vs 도로거리, 일방통행에 의한 비대칭
    n = len(nodes)
    ratios, asym = [], []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            s = haversine(pts.lat[i], pts.lon[i], pts.lat[j], pts.lon[j])
            if s > 50:
                ratios.append(M[i, j] / s)
            if i < j:
                asym.append(abs(M[i, j] - M[j, i]))
    ratios, asym = np.array(ratios), np.array(asym)
    print(f"\n[발표용 수치]")
    print(f"도로거리 / 직선거리: 평균 {ratios.mean():.2f}배, 최대 {ratios.max():.2f}배")
    print(f"가는 길과 오는 길 거리가 다른 쌍: {(asym > 1).mean() * 100:.1f}% "
          f"(최대 차이 {asym.max():.0f}m)")

    # 지도
    m = make_map(pts.lat.mean(), pts.lon.mean())
    add_road_background(m, G)
    for _, r in pts.iterrows():
        if r.type == "depot":
            folium.Marker([r.lat, r.lon], tooltip="출발점",
                          icon=folium.Icon(color="red", icon="home")).add_to(m)
        else:
            folium.CircleMarker([r.lat, r.lon], radius=5, color="blue", fill=True,
                                tooltip=f"배송지 {r.id}").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(os.path.join(OUT, "step1_map.html"))
    print(f"\n지도 저장: {OUT}/step1_map.html (더블클릭하면 브라우저에서 열림)")


if __name__ == "__main__":
    main()
