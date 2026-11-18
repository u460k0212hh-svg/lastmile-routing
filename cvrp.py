"""차량 여러 대 + 적재 용량 제약 (CVRP: Capacitated Vehicle Routing Problem)
routes: 차량별 경로 리스트. 각 경로는 [0, 배송지..., 0] (0 = 출발 터미널)
demand[i]: 배송지 i의 박스 수 (demand[0] = 0)"""
import math
import time

from tsp import route_cost, improve, nearest_neighbor


def total_cost(routes, M):
    return sum(route_cost(r, M) for r in routes)


def sweep_split(M, lats, lons, demand, capacity):
    """기준 방식: 터미널 중심으로 각도 순서대로 배송지를 정렬한 뒤, 차량 용량이 찰 때마다 끊어
    기사별 담당 구역을 나눈다. 구역 안에서는 '가까운 곳부터' 방문 (현장의 구역 담당제 + 기사 감각을 단순화)."""
    lat0, lon0 = lats[0], lons[0]
    order = sorted(range(1, len(lats)), key=lambda i: -math.atan2(lats[i] - lat0, lons[i] - lon0))
    routes, cur, load = [], [], 0
    for i in order:
        if load + demand[i] > capacity:
            routes.append([0] + cur + [0])
            cur, load = [], 0
        cur.append(i)
        load += demand[i]
    if cur:
        routes.append([0] + cur + [0])
    return [_nn_within(r[1:-1], M) for r in routes]


def _nn_within(stops, M):
    route, cur, left = [0], 0, set(stops)
    while left:
        nxt = min(left, key=lambda j: M[cur][j])
        route.append(nxt); left.remove(nxt); cur = nxt
    return route + [0]


def savings(M, demand, capacity):
    """세이빙 알고리즘 (Clarke & Wright, 1964).
    배송지마다 차를 따로 보내는 상태에서 시작해, 두 경로를 이었을 때 줄어드는 거리
    s(i,j) = d(i,0) + d(0,j) - d(i,j) 가 큰 순서대로, 용량이 허락하면 경로를 합친다.
    일방통행으로 거리가 비대칭이라 i의 '끝'과 j의 '시작'을 잇는 방향까지 구분한다."""
    n = len(M)
    route_of = {i: [i] for i in range(1, n)}      # 배송지 -> 그 배송지가 속한 경로(리스트 객체)
    load = {id(route_of[i]): demand[i] for i in range(1, n)}
    s = [(M[i][0] + M[0][j] - M[i][j], i, j)
         for i in range(1, n) for j in range(1, n) if i != j]
    s.sort(reverse=True)
    for val, i, j in s:
        if val <= 0:
            break
        ri, rj = route_of[i], route_of[j]
        if ri is rj or ri[-1] != i or rj[0] != j:
            continue
        if load[id(ri)] + load[id(rj)] > capacity:
            continue
        merged = ri + rj
        load[id(merged)] = load.pop(id(ri)) + load.pop(id(rj))
        for k in merged:
            route_of[k] = merged
    uniq = {id(r): r for r in route_of.values()}
    return [[0] + r + [0] for r in uniq.values()]


def improve_routes(routes, M):
    """차량별 경로 안에서 방문 순서만 2-opt + Or-opt로 개선 (담당 배송지는 그대로)"""
    return [improve(r, M) for r in routes]


def ortools_cvrp(M, demand, capacity, seconds=5):
    """비교 기준: OR-Tools CVRP"""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    n = len(M)
    V = math.ceil(sum(demand) / capacity) + 2          # 넉넉하게 차량을 주고, 안 쓰는 차는 비워 둠
    Mi = [[int(round(M[i][j])) for j in range(n)] for i in range(n)]
    manager = pywrapcp.RoutingIndexManager(n, V, 0)
    routing = pywrapcp.RoutingModel(manager)
    t = routing.RegisterTransitCallback(lambda a, b: Mi[manager.IndexToNode(a)][manager.IndexToNode(b)])
    routing.SetArcCostEvaluatorOfAllVehicles(t)
    d = routing.RegisterUnaryTransitCallback(lambda a: int(demand[manager.IndexToNode(a)]))
    routing.AddDimensionWithVehicleCapacity(d, 0, [capacity] * V, True, "Capacity")
    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    p.time_limit.FromSeconds(seconds)
    sol = routing.SolveWithParameters(p)
    routes = []
    for v in range(V):
        idx, r = routing.Start(v), []
        while not routing.IsEnd(idx):
            r.append(manager.IndexToNode(idx))
            idx = sol.Value(routing.NextVar(idx))
        if len(r) > 1:
            routes.append(r + [0])
    return routes


_warned = False


def run_all(M, lats, lons, demand, capacity, ortools_seconds=5, use_ortools=True):
    """{방식: (차량별 경로들, 총거리m, 계산시간s)}"""
    global _warned
    out = {}
    t = time.time(); r = sweep_split(M, lats, lons, demand, capacity); out["기준(구역 분할)"] = (r, total_cost(r, M), time.time() - t)
    t = time.time(); r2 = improve_routes(r, M); out["구역 분할 + 순서 개선"] = (r2, total_cost(r2, M), time.time() - t + out["기준(구역 분할)"][2])
    t = time.time(); r = savings(M, demand, capacity); out["세이빙"] = (r, total_cost(r, M), time.time() - t)
    t = time.time(); r2 = improve_routes(r, M); out["세이빙 + 순서 개선"] = (r2, total_cost(r2, M), time.time() - t + out["세이빙"][2])
    if not use_ortools:
        return out
    try:
        t = time.time(); r = ortools_cvrp(M, demand, capacity, ortools_seconds); out["OR-Tools(비교 기준)"] = (r, total_cost(r, M), time.time() - t)
    except Exception as e:
        if not _warned:
            print("[알림] OR-Tools를 불러오지 못해 비교에서 제외합니다:", type(e).__name__, e)
            _warned = True
    return out


def check(routes, demand, capacity, n):
    """검증: 모든 배송지를 정확히 한 번씩 방문하고, 어떤 차량도 용량을 넘지 않는가"""
    seen = [k for r in routes for k in r[1:-1]]
    assert sorted(seen) == list(range(1, n)), "방문 누락 또는 중복"
    assert all(r[0] == 0 and r[-1] == 0 for r in routes), "터미널에서 출발/복귀하지 않는 경로"
    assert all(sum(demand[k] for k in r) <= capacity for r in routes), "용량 초과"
