"""검증 스크립트 - 네 가지를 각각 다른 질문으로 확인한다.
  1. 다익스트라 정확성     : 직접 구현한 최단거리 = NetworkX 최단거리?
  2. 배송 계획 유효성      : 누락·중복 방문, 용량 초과, 출발·복귀 위반이 없는가?
  3. 개선 연산 정확성      : 2-opt·Or-opt 적용 후 거리가 늘지 않는가? (빠른 계산식이 실제 거리와 일치하는가?)
  4. 작은 문제의 해 품질   : 배송지 8곳에서 전수 탐색 최적해와 얼마나 차이 나는가?
모두 미추홀구 실제 도로망 거리로 확인한다.

실행: python verify.py   (2~4분)
"""
try:
    from ortools.constraint_solver import pywrapcp  # noqa: F401  (Windows DLL 충돌 방지)
    HAS_ORTOOLS = True
except Exception:
    HAS_ORTOOLS = False

import itertools
import os
import random
import time

import networkx as nx
import osmnx as ox
import pandas as pd

from dijkstra import build_adjacency, dijkstra, distance_matrix
from tsp import route_cost, nearest_neighbor, sweep_route, two_opt, or_opt, improve, multi_start
from cvrp import run_all as cvrp_run_all, check

OUT = "data"
results = []


def report(name, ok, detail, guarantees, not_guarantees):
    results.append((name, ok))
    print(f"\n{'✅ 통과' if ok else '❌ 실패'}  {name}")
    print(f"   결과: {detail}")
    print(f"   보증하는 것: {guarantees}")
    print(f"   보증하지 않는 것: {not_guarantees}")


def main():
    G = ox.load_graphml(os.path.join(OUT, "graph.graphml"))
    pts = pd.read_csv(os.path.join(OUT, "points.csv"))
    depot = int(pts.node[0])
    adj = build_adjacency(G)
    cands = [n for n in G.nodes if n != depot]
    rnd = random.Random(12345)          # 검증용 고정 시드 (실험 시나리오와 겹치지 않게)

    # ---------- 1. 다익스트라 ----------
    sources = rnd.sample(list(G.nodes), 30)
    max_err, pairs = 0.0, 0
    for s in sources:
        mine = dijkstra(adj, s)
        ref = nx.single_source_dijkstra_path_length(G, s, weight="length")
        assert set(mine) == set(ref), "도달 가능한 교차로 집합이 다름"
        for t, d in ref.items():
            max_err = max(max_err, abs(mine[t] - d))
            pairs += 1
    report("1. 다익스트라 정확성", max_err < 1e-6,
           f"출발점 30곳 × 모든 교차로 = {pairs:,}쌍, 최대 오차 {max_err:.2e} m",
           "직접 구현한 다익스트라가 이 도로망에서 NetworkX와 같은 최단거리를 계산함",
           "OSM 도로 데이터 자체의 정확성, 회전 제한·신호 등 반영 여부")

    # ---------- 2. 배송 계획 유효성 ----------
    n_plans, n_methods = 0, set()
    for k in range(5):
        r = random.Random(500 + k)
        nodes = [depot] + r.sample(cands, 100)
        demand = [0] + [r.randint(1, 3) for _ in range(100)]
        M = distance_matrix(adj, nodes)
        lats = [G.nodes[n]["y"] for n in nodes]
        lons = [G.nodes[n]["x"] for n in nodes]
        for cap in (30, 60, 120):
            res = cvrp_run_all(M, lats, lons, demand, cap, ortools_seconds=2, use_ortools=HAS_ORTOOLS)
            for name, (routes, _, _) in res.items():
                check(routes, demand, cap, len(nodes))      # 위반 시 여기서 멈춤
                n_plans += 1
                n_methods.add(name)
    report("2. 배송 계획 유효성", True,
           f"시나리오 5개 × 용량 3종 × 방식 {len(n_methods)}개 = 배송 계획 {n_plans}개 모두 위반 없음",
           "모든 배송지를 정확히 한 번 방문, 차량별 박스 합 ≤ 용량, 모든 경로가 터미널 출발·복귀",
           "경로가 짧다는 것(품질은 3·4번과 실험에서 별도 확인)")

    # ---------- 3. 개선 연산 ----------
    worse, checks, not_local = 0, 0, 0
    for k in range(10):
        r = random.Random(700 + k)
        nodes = [depot] + r.sample(cands, 40)
        M = distance_matrix(adj, nodes)
        lats = [G.nodes[n]["y"] for n in nodes]
        lons = [G.nodes[n]["x"] for n in nodes]
        rand_route = [0] + r.sample(range(1, len(nodes)), len(nodes) - 1) + [0]
        for start in (nearest_neighbor(M), sweep_route(lats, lons), rand_route):
            c0 = route_cost(start, M)
            for op in (two_opt, or_opt, improve):
                out = op(start, M)
                checks += 1
                assert sorted(out[1:-1]) == sorted(start[1:-1]) and out[0] == 0 == out[-1]
                if route_cost(out, M) > c0 + 1e-6:
                    worse += 1
            # 빠른 계산식(O(1) 변화량)이 맞다면, 2-opt 결과에는 더 줄일 수 있는 뒤집기가 남아 있으면 안 됨
            t = two_opt(start, M)
            ct = route_cost(t, M)
            L = len(t)
            for i in range(1, L - 2):
                for j in range(i + 1, L - 1):
                    if route_cost(t[:i] + t[i:j + 1][::-1] + t[j + 1:], M) < ct - 1e-6:
                        not_local += 1
    report("3. 개선 연산 정확성", worse == 0 and not_local == 0,
           f"{checks}회 적용 중 거리 증가 {worse}회 / 2-opt 결과에서 전체 재계산으로 찾은 추가 개선 {not_local}건",
           "2-opt·Or-opt가 거리를 늘리지 않고, 비대칭 거리용 빠른 계산식이 실제 경로 거리와 일치함",
           "개선 결과가 최적해라는 것(국소 최적일 뿐)")

    # ---------- 4. 작은 문제 품질 ----------
    rows = []
    t0 = time.time()
    for k in range(20):
        r = random.Random(900 + k)
        nodes = [depot] + r.sample(cands, 8)
        M = distance_matrix(adj, nodes)
        lats = [G.nodes[n]["y"] for n in nodes]
        lons = [G.nodes[n]["x"] for n in nodes]
        opt = min(route_cost([0, *p, 0], M) for p in itertools.permutations(range(1, 9)))
        nn = nearest_neighbor(M)
        sols = {"최근접 이웃": nn, "+2-opt": two_opt(nn, M), "+2-opt+Or-opt": improve(nn, M),
                "다중 시작(0.2초)": multi_start(M, lats, lons, seconds=0.2)}
        rows.append({name: (route_cost(s, M) / opt - 1) * 100 for name, s in sols.items()})
    df = pd.DataFrame(rows)
    lines = [f"{c}: 평균 +{df[c].mean():.2f}%, 최악 +{df[c].max():.2f}%, 최적해 일치 {(df[c] < 1e-6).sum()}/20"
             for c in df.columns]
    report("4. 작은 문제의 해 품질 (배송지 8곳, 차량 1대)", True,
           "\n          ".join([""] + lines) + f"\n          (전수 탐색 8! = 40,320가지 × 20문제, {time.time() - t0:.0f}초)",
           "배송지 8곳 규모에서 각 방식이 최적해와 얼마나 가까운지",
           "배송지 50~100곳 규모의 최적성(큰 문제는 최적해를 알 수 없어 OR-Tools와 비교로 대신함)")

    print("\n" + "=" * 60)
    print("요약:", ", ".join(f"{n.split('.')[0]}번 {'통과' if ok else '실패'}" for n, ok in results))
    if not HAS_ORTOOLS:
        print("(OR-Tools를 불러오지 못해 2번 검증에서 OR-Tools 결과는 제외됨)")


if __name__ == "__main__":
    main()
