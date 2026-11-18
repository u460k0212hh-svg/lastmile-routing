"""3단계: 차량 여러 대 + 적재 용량 (CVRP)
기준(구역 분할) vs 구역 분할+순서 개선 vs 세이빙 vs 세이빙+순서 개선 vs OR-Tools

실행: python step3_cvrp.py   (step1_network.py를 먼저 실행해서 data/graph.graphml이 있어야 함)
결과: 비교표 + data/step3_map.html(차량별 색깔 경로) + data/step3_experiment.csv
"""
try:
    from ortools.constraint_solver import pywrapcp  # noqa: F401  (Windows DLL 충돌 방지: 먼저 불러옴)
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
from cvrp import run_all, check, route_cost

# ---------------- 설정 ----------------
N_POINTS = 100          # 배송지 수
CAPACITY = 60           # 차량 1대 적재 한도 (박스 수)
DEMAND_RANGE = (1, 3)   # 배송지별 박스 수 (무작위)
RUN_EXPERIMENT = True   # False면 대표 시나리오 + 지도만
N_SCENARIOS = 20
OUT = "data"
# --------------------------------------
VEH_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
              "#f032e6", "#9a6324", "#469990", "#000075"]


def make_scenario(G, adj, depot, seed):
    rnd = random.Random(seed)
    cands = [n for n in G.nodes if n != depot]
    nodes = [depot] + rnd.sample(cands, N_POINTS)
    demand = [0] + [rnd.randint(*DEMAND_RANGE) for _ in range(N_POINTS)]
    M = distance_matrix(adj, nodes)
    lats = [G.nodes[n]["y"] for n in nodes]
    lons = [G.nodes[n]["x"] for n in nodes]
    return nodes, demand, M, lats, lons


def summarize(res, M):
    rows = []
    base = res["기준(구역 분할)"][1]
    for name, (routes, d, sec) in res.items():
        lens = [route_cost(r, M) / 1000 for r in routes]
        rows.append({"방식": name, "차량 수": len(routes), "총 거리(km)": round(d / 1000, 2),
                     "기준 대비 감소(%)": round((1 - d / base) * 100, 1),
                     "가장 긴 경로(km)": round(max(lens), 2), "가장 짧은 경로(km)": round(min(lens), 2),
                     "계산 시간(s)": round(sec, 3)})
    return pd.DataFrame(rows)


def draw_map(G, nodes, lats, lons, res, path):
    m = make_map(np.mean(lats), np.mean(lons))
    add_road_background(m, G)
    for name, (routes, d, _) in res.items():
        layer = folium.FeatureGroup(name=f"{name} ({len(routes)}대, {d / 1000:.1f}km)",
                                    show=(name == "세이빙 + 순서 개선"))
        for v, r in enumerate(routes):
            coords = []
            for a, b in zip(r[:-1], r[1:]):
                p = nx.shortest_path(G, nodes[a], nodes[b], weight="length")
                coords += [(G.nodes[x]["y"], G.nodes[x]["x"]) for x in p]
            folium.PolyLine(coords, color=VEH_COLORS[v % len(VEH_COLORS)], weight=4, opacity=0.85,
                            tooltip=f"{v + 1}호차: {route_cost(r, M_global) / 1000:.1f}km").add_to(layer)
        layer.add_to(m)
    folium.Marker([lats[0], lons[0]], tooltip="터미널", icon=folium.Icon(color="red", icon="home")).add_to(m)
    for i in range(1, len(nodes)):
        folium.CircleMarker([lats[i], lons[i]], radius=3, color="black", fill=True,
                            tooltip=f"배송지 {i}").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(path)


M_global = None


def main():
    global M_global
    G = ox.load_graphml(os.path.join(OUT, "graph.graphml"))
    pts = pd.read_csv(os.path.join(OUT, "points.csv"))
    depot = int(pts.node[0])
    adj = build_adjacency(G)

    print(f"=== 대표 시나리오 (배송지 {N_POINTS}곳, 차량 용량 {CAPACITY}박스) ===")
    nodes, demand, M, lats, lons = make_scenario(G, adj, depot, seed=7)
    M_global = M
    print(f"총 박스 {sum(demand)}개 -> 최소 필요 차량 {-(-sum(demand) // CAPACITY)}대")
    res = run_all(M, lats, lons, demand, CAPACITY, ortools_seconds=5)
    for name, (routes, _, _) in res.items():
        check(routes, demand, CAPACITY, len(nodes))
    print("검증 통과: 모든 방식이 배송지를 빠짐없이 한 번씩 방문하고 용량을 지킴")
    pd.set_option("display.width", 200)
    print(summarize(res, M).to_string(index=False))
    draw_map(G, nodes, lats, lons, res, os.path.join(OUT, "step3_map.html"))
    print("지도 저장: data/step3_map.html (차량별로 색이 다름, 선에 마우스를 올리면 호차별 거리)\n")

    if not RUN_EXPERIMENT:
        return
    print(f"=== 반복 실험 ({N_SCENARIOS}개 시나리오) ===")
    rows = []
    for s in range(N_SCENARIOS):
        nodes, demand, M, lats, lons = make_scenario(G, adj, depot, seed=2000 + s)
        r = run_all(M, lats, lons, demand, CAPACITY, ortools_seconds=3)
        row = {"scenario": s}
        for name, (routes, d, sec) in r.items():
            check(routes, demand, CAPACITY, len(nodes))
            row[name + "_km"] = d / 1000
            row[name + "_veh"] = len(routes)
            row[name + "_sec"] = sec
            lens = [route_cost(x, M) / 1000 for x in routes]
            row[name + "_gap"] = max(lens) - min(lens)
        rows.append(row)
        print(f"  시나리오 {s + 1}/{N_SCENARIOS} 완료")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "step3_experiment.csv"), index=False, encoding="utf-8-sig")
    base = df["기준(구역 분할)_km"]
    print(f"\n[발표용 수치: {N_SCENARIOS}개 시나리오 평균]")
    for name in res:
        km = df[name + "_km"]
        print(f"{name:<22} 평균 {km.mean():6.2f}km | 차량 {df[name + '_veh'].mean():.1f}대 | "
              f"기준 대비 {((1 - km / base) * 100).mean():5.1f}% 감소 | "
              f"기사 간 거리 편차 {df[name + '_gap'].mean():5.1f}km | 계산 {df[name + '_sec'].mean():.3f}s")
    if "OR-Tools(비교 기준)_km" in df.columns:
        gap = (df["세이빙 + 순서 개선_km"] / df["OR-Tools(비교 기준)_km"] - 1) * 100
        print(f"\n세이빙 + 순서 개선 vs OR-Tools: 평균 {gap.mean():+.1f}%, 최악 {gap.max():+.1f}%, "
              f"직접 구현이 더 좋았던 시나리오 {(gap < 0).sum()}개")


if __name__ == "__main__":
    main()
