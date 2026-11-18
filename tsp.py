"""차량 1대 배송 순서 결정 알고리즘 (TSP)
경로(route)는 항상 0(출발점)에서 시작해 0으로 돌아오는 리스트. 예: [0, 5, 2, 9, 0]
일방통행 때문에 M[i][j] != M[j][i] 일 수 있으므로(비대칭) 모든 비용은 방향을 고려해 계산한다."""
import math
import time


def route_cost(route, M):
    return sum(M[route[k]][route[k + 1]] for k in range(len(route) - 1))


def sweep_route(lats, lons):
    """기준 방식: 출발점을 중심으로 시계방향으로 한 바퀴 도는 순서.
    지도를 보고 '이쪽 동네부터 차례로' 도는 기사의 감각을 흉내 낸 것."""
    lat0, lon0 = lats[0], lons[0]
    stops = list(range(1, len(lats)))
    stops.sort(key=lambda i: -math.atan2(lats[i] - lat0, lons[i] - lon0))
    return [0] + stops + [0]


def nearest_neighbor(M):
    """최근접 이웃: 지금 위치에서 아직 안 간 곳 중 가장 가까운 곳으로 간다."""
    n = len(M)
    route, cur, left = [0], 0, set(range(1, n))
    while left:
        nxt = min(left, key=lambda j: M[cur][j])
        route.append(nxt)
        left.remove(nxt)
        cur = nxt
    return route + [0]


def _prefix(route, M):
    """경로를 정방향/역방향으로 갈 때의 누적 거리 (구간 뒤집기 비용을 O(1)에 계산하기 위함)"""
    F, B = [0.0], [0.0]
    for k in range(len(route) - 1):
        F.append(F[-1] + M[route[k]][route[k + 1]])
        B.append(B[-1] + M[route[k + 1]][route[k]])
    return F, B


def two_opt(route, M, max_passes=100):
    """2-opt 개선: 경로 중간 구간(i~j)을 뒤집어 보고 거리가 줄면 채택, 더 이상 안 줄 때까지 반복.
    비대칭 거리라 구간을 뒤집으면 구간 안쪽 이동 방향도 바뀐다 -> 역방향 누적거리로 바로 계산.
    (경로 전체를 다시 더하지 않아 후보 하나당 계산이 O(1))"""
    route = route[:]
    n = len(route)
    for _ in range(max_passes):
        improved = False
        F, B = _prefix(route, M)
        for i in range(1, n - 2):
            a = route[i - 1]
            for j in range(i + 1, n - 1):
                b, c, d = route[i], route[j], route[j + 1]
                old = M[a][b] + (F[j] - F[i]) + M[c][d]
                new = M[a][c] + (B[j] - B[i]) + M[b][d]
                if new < old - 1e-9:
                    route[i:j + 1] = route[i:j + 1][::-1]
                    improved = True
                    F, B = _prefix(route, M)
                    a = route[i - 1]
        if not improved:
            break
    return route


def or_opt(route, M, max_passes=100):
    """Or-opt 개선: 연속된 배송지 1~3곳 묶음을 뒤집지 않고 다른 위치로 옮겨 본다.
    일방통행이 많아 구간을 뒤집는 2-opt가 손해를 보는 경우를 보완한다."""
    route = route[:]
    for _ in range(max_passes):
        improved = False
        for k in (1, 2, 3):
            i = 1
            while i + k <= len(route) - 1:
                s0, s1 = route[i], route[i + k - 1]
                prev, nxt = route[i - 1], route[i + k]
                gain_remove = M[prev][s0] + M[s1][nxt] - M[prev][nxt]
                rest = route[:i] + route[i + k:]
                best_p, best_delta = None, -1e-9
                for p in range(1, len(rest)):
                    if p == i:
                        continue
                    x, y = rest[p - 1], rest[p]
                    delta = M[x][s0] + M[s1][y] - M[x][y] - gain_remove
                    if delta < best_delta:
                        best_p, best_delta = p, delta
                if best_p is not None:
                    route = rest[:best_p] + route[i:i + k] + rest[best_p:]
                    improved = True
                i += 1
        if not improved:
            break
    return route


def improve(route, M):
    """2-opt와 Or-opt를 번갈아 적용, 둘 다 더 못 줄일 때까지"""
    best = route_cost(route, M)
    while True:
        route = or_opt(two_opt(route, M), M)
        c = route_cost(route, M)
        if c >= best - 1e-9:
            return route
        best = c


def multi_start(M, lats, lons, seconds=2.0, seed=0):
    """여러 시작 경로에서 개선을 반복하고 가장 좋은 결과를 고른다 (제한 시간 안에서).
    시작 경로: 최근접 이웃, 구역 순서, 그리고 '가까운 후보 중 무작위로 고르는' 변형 최근접 이웃."""
    import random
    rnd = random.Random(seed)
    t_end = time.time() + seconds
    best = improve(nearest_neighbor(M), M)
    best_c = route_cost(best, M)
    starts = [sweep_route(lats, lons)]
    while time.time() < t_end:
        if starts:
            r0 = starts.pop()
        else:
            n = len(M)
            r0, cur, left = [0], 0, set(range(1, n))
            while left:
                cand = sorted(left, key=lambda j: M[cur][j])[:3]
                nxt = rnd.choice(cand)
                r0.append(nxt); left.remove(nxt); cur = nxt
            r0.append(0)
        r = improve(r0, M)
        c = route_cost(r, M)
        if c < best_c - 1e-9:
            best, best_c = r, c
    return best


def ortools_tsp(M, seconds=5):
    """비교 기준: 구글 OR-Tools (상용 수준 최적화 라이브러리). 제한 시간 안에서 찾은 최선의 해."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    n = len(M)
    Mi = [[int(round(M[i][j])) for j in range(n)] for i in range(n)]
    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def cb(a, b):
        return Mi[manager.IndexToNode(a)][manager.IndexToNode(b)]

    t = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(t)
    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    p.time_limit.FromSeconds(seconds)
    sol = routing.SolveWithParameters(p)
    idx, route = routing.Start(0), []
    while not routing.IsEnd(idx):
        route.append(manager.IndexToNode(idx))
        idx = sol.Value(routing.NextVar(idx))
    return route + [0]


def run_all(M, lats, lons, ortools_seconds=5):
    """여섯 가지 방식을 모두 돌려 {이름: (경로, 거리m, 계산시간s)} 반환"""
    out = {}
    t = time.time(); r = sweep_route(lats, lons); out["기준(구역 순서)"] = (r, route_cost(r, M), time.time() - t)
    t = time.time(); r = nearest_neighbor(M); out["최근접 이웃"] = (r, route_cost(r, M), time.time() - t)
    nn = r
    t0 = time.time(); r = two_opt(nn, M); out["최근접 이웃 + 2-opt"] = (r, route_cost(r, M), time.time() - t0 + out["최근접 이웃"][2])
    t0 = time.time(); r = improve(nn, M); out["최근접 이웃 + 2-opt + Or-opt"] = (r, route_cost(r, M), time.time() - t0 + out["최근접 이웃"][2])
    t0 = time.time(); r = multi_start(M, lats, lons, seconds=ortools_seconds); out["다중 시작(같은 시간)"] = (r, route_cost(r, M), time.time() - t0)
    try:
        t = time.time(); r = ortools_tsp(M, ortools_seconds); out["OR-Tools(비교 기준)"] = (r, route_cost(r, M), time.time() - t)
    except Exception as e:  # 설치/DLL 문제로 OR-Tools를 못 쓰면 나머지 결과만 반환
        global _warned
        if not _warned:
            print("[알림] OR-Tools를 불러오지 못해 비교에서 제외합니다:", type(e).__name__, e)
            _warned = True
    return out


_warned = False
