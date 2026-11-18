"""2단계: 차량 1대 배송 순서 최적화 - 기준 방식 vs 최근접 이웃 vs 2-opt vs 2-opt+Or-opt vs OR-Tools

실행: python step2_tsp.py   (step1_network.py를 먼저 실행해서 data/ 폴더가 있어야 함)
결과: 화면에 비교표 + data/step2_map.html(방식별 경로 지도) + data/step2_experiment.csv
"""
# OR-Tools는 다른 패키지보다 먼저 불러와야 Windows에서 DLL 충돌이 덜 난다
try:
    from ortools.constraint_solver import pywrapcp  # noqa: F401
except Exception:
    pass

import os
import random

import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import folium

from basemap import make_map, add_road_background

from dijkstra import build_adjacency, distance_matrix
from tsp import run_all

OUT = "data"
RUN_EXPERIMENT = True   # False로 바꾸면 지도만 다시 그리고 반복 실험은 건너뜀
N_SCENARIOS = 30        # 반복 실험 횟수 (배송지 배치를 매번 바꿔서)
N_POINTS = 50
COLORS = {"기준(구역 순서)": "gray", "최근접 이웃": "orange",
          "최근접 이웃 + 2-opt": "purple", "최근접 이웃 + 2-opt + Or-opt": "blue", "다중 시작(같은 시간)": "darkblue", "OR-Tools(비교 기준)": "green"}


def print_table(res):
    base = res["기준(구역 순서)"][1]
    print(f"{'방식':<32}{'총 거리':>10}{'기준 대비':>10}{'계산 시간':>10}")
    for name, (_, d, sec) in res.items():
        print(f"{name:<32}{d / 1000:>8.2f}km{(1 - d / base) * 100:>8.1f}%↓{sec:>9.3f}s")


def draw_map(G, pts, res, path):
    m = make_map(pts.lat.mean(), pts.lon.mean())
    add_road_background(m, G)
    nodes = list(pts.node)
    for name, (route, d, _) in res.items():
        layer = folium.FeatureGroup(name=f"{name} ({d / 1000:.1f}km)", show=(name in ("기준(구역 순서)", "최근접 이웃 + 2-opt + Or-opt")))
        coords = []
        for a, b in zip(route[:-1], route[1:]):
            p = nx.shortest_path(G, nodes[a], nodes[b], weight="length")
            coords += [(G.nodes[x]["y"], G.nodes[x]["x"]) for x in p]
        folium.PolyLine(coords, color=COLORS[name], weight=4, opacity=0.8).add_to(layer)
        layer.add_to(m)
    for _, r in pts.iterrows():
        if r.type == "depot":
            folium.Marker([r.lat, r.lon], tooltip="출발점", icon=folium.Icon(color="red", icon="home")).add_to(m)
        else:
            folium.CircleMarker([r.lat, r.lon], radius=4, color="black", fill=True, tooltip=f"배송지 {r.id}").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(path)


def main():
    G = ox.load_graphml(os.path.join(OUT, "graph.graphml"))
    pts = pd.read_csv(os.path.join(OUT, "points.csv"))
    M = np.load(os.path.join(OUT, "dist_matrix.npy")).tolist()

    # 1) 대표 시나리오 1개: 자세한 비교 + 지도
    print("=== 대표 시나리오 (배송지 50곳, 차량 1대) ===")
    res = run_all(M, list(pts.lat), list(pts.lon))
    print_table(res)
    draw_map(G, pts, res, os.path.join(OUT, "step2_map.html"))
    print("지도 저장: data/step2_map.html (오른쪽 위 체크박스로 방식별 경로를 켜고 끌 수 있음)\n")

    if not RUN_EXPERIMENT:
        return

    # 2) 반복 실험: 배송지 배치를 30번 바꿔 평균 성능 측정
    print(f"=== 반복 실험 ({N_SCENARIOS}개 시나리오, 시간이 몇 분 걸립니다) ===")
    adj = build_adjacency(G)
    depot = int(pts.node[0])
    cands = [n for n in G.nodes if n != depot]
    rows = []
    for s in range(N_SCENARIOS):
        random.seed(1000 + s)
        nodes = [depot] + random.sample(cands, N_POINTS)
        Ms = distance_matrix(adj, nodes)
        lats = [G.nodes[n]["y"] for n in nodes]
        lons = [G.nodes[n]["x"] for n in nodes]
        r = run_all(Ms, lats, lons, ortools_seconds=2)
        row = {"scenario": s}
        for name, (_, d, sec) in r.items():
            row[name + "_km"] = d / 1000
            row[name + "_sec"] = sec
        rows.append(row)
        print(f"  시나리오 {s + 1}/{N_SCENARIOS} 완료")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "step2_experiment.csv"), index=False, encoding="utf-8-sig")

    base = df["기준(구역 순서)_km"]
    print("\n[발표용 수치: 30개 시나리오 평균]")
    for name in res:
        km = df[name + "_km"]
        print(f"{name:<32} 평균 {km.mean():6.2f}km | 기준 대비 {((1 - km / base) * 100).mean():5.1f}% 감소 "
              f"| 평균 계산 {df[name + '_sec'].mean():.3f}s")
    if "OR-Tools(비교 기준)_km" in df.columns:
        ort = df["OR-Tools(비교 기준)_km"]
        for name in ("최근접 이웃 + 2-opt + Or-opt", "다중 시작(같은 시간)"):
            gap = (df[name + "_km"] / ort - 1) * 100
            print(f"{name} vs OR-Tools: 평균 {gap.mean():+.1f}%, 최악 {gap.max():+.1f}%, "
                  f"직접 구현이 더 좋았던 시나리오 {(gap < 0).sum()}개")

if __name__ == "__main__":
    main()
