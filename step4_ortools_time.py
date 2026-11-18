"""4단계: OR-Tools 탐색 시간별 비교 (2·5·10·30초)
- 대상 시나리오는 미리 고정: 2단계 반복 실험의 앞 5개(seed 1000~1004), 3단계 반복 실험의 앞 5개(seed 2000~2004)
  결과와 무관하게 이 10개를 모두 보고한다 (좋은 사례만 고르지 않기).
- 30초 결과도 최적해를 보장하는 기준은 아니다.

실행: python step4_ortools_time.py   (약 8~9분)
결과: 화면 표 + data/step4_ortools_time.csv (실행 시각·설정 포함)
"""
try:
    from ortools.constraint_solver import pywrapcp  # noqa: F401  (Windows DLL 충돌 방지)
except Exception:
    pass

import datetime
import os
import random
import time

import osmnx as ox
import pandas as pd

from dijkstra import build_adjacency, distance_matrix
from tsp import route_cost, multi_start, nearest_neighbor, improve, ortools_tsp
from cvrp import total_cost, savings, improve_routes, ortools_cvrp, check

OUT = "data"
TIMES = [2, 5, 10, 30]
STAMP = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def main():
    G = ox.load_graphml(os.path.join(OUT, "graph.graphml"))
    pts = pd.read_csv(os.path.join(OUT, "points.csv"))
    depot = int(pts.node[0])
    adj = build_adjacency(G)
    cands = [n for n in G.nodes if n != depot]
    rows = []

    print("=== 차량 1대 (배송지 50곳, 2단계 시나리오 0~4) ===")
    for s in range(5):
        random.seed(1000 + s)                       # step2_tsp.py와 같은 방식
        nodes = [depot] + random.sample(cands, 50)
        M = distance_matrix(adj, nodes)
        lats = [G.nodes[n]["y"] for n in nodes]
        lons = [G.nodes[n]["x"] for n in nodes]
        row = {"실행 시각": STAMP, "문제": "차량 1대", "시나리오": s, "배송지": 50}
        t = time.time(); r = improve(nearest_neighbor(M), M)
        row["직접(빠른)_km"] = route_cost(r, M) / 1000; row["직접(빠른)_초"] = time.time() - t
        r = multi_start(M, lats, lons, seconds=2)
        row["직접(다중 시작 2초)_km"] = route_cost(r, M) / 1000
        for sec in TIMES:
            r = ortools_tsp(M, sec)
            row[f"OR-Tools {sec}초_km"] = route_cost(r, M) / 1000
        rows.append(row)
        print(f"  시나리오 {s} 완료")

    print("=== 차량 여러 대 (배송지 100곳, 용량 60, 3단계 시나리오 0~4) ===")
    for s in range(5):
        rnd = random.Random(2000 + s)               # step3_cvrp.py와 같은 방식
        nodes = [depot] + rnd.sample(cands, 100)
        demand = [0] + [rnd.randint(1, 3) for _ in range(100)]
        M = distance_matrix(adj, nodes)
        row = {"실행 시각": STAMP, "문제": "차량 여러 대", "시나리오": s, "배송지": 100}
        t = time.time(); r = improve_routes(savings(M, demand, 60), M)
        check(r, demand, 60, len(nodes))
        row["직접(빠른)_km"] = total_cost(r, M) / 1000; row["직접(빠른)_초"] = time.time() - t
        for sec in TIMES:
            r = ortools_cvrp(M, demand, 60, sec)
            check(r, demand, 60, len(nodes))
            row[f"OR-Tools {sec}초_km"] = total_cost(r, M) / 1000
        rows.append(row)
        print(f"  시나리오 {s} 완료")

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "step4_ortools_time.csv"), index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    print("\n[시나리오별 결과 (km)] — 선별 없이 고정된 10개 전부")
    show = [c for c in df.columns if c.endswith("_km")]
    print(df[["문제", "시나리오"] + show].round(2).to_string(index=False, na_rep="-"))

    print("\n[OR-Tools 30초 대비 차이 (%), +면 OR-Tools 30초가 더 짧음]")
    for prob, g in df.groupby("문제", sort=False):
        ref = g["OR-Tools 30초_km"]
        for c in show:
            if c == "OR-Tools 30초_km" or g[c].isna().all():
                continue
            gap = (g[c] / ref - 1) * 100
            print(f"  {prob:<8} {c[:-3]:<22} 평균 {gap.mean():+6.2f}% | 최악 {gap.max():+6.2f}% | 최선 {gap.min():+6.2f}%")
    print("\n※ 30초 결과도 최적해를 보장하는 기준이 아님. 시나리오 5개씩의 소규모 비교로, 전체 반복 실험과 구분해 제시할 것.")


if __name__ == "__main__":
    main()
