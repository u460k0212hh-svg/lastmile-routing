"""직접 구현한 다익스트라 알고리즘 (수업 9장 지하철 최단경로를 실제 도로망에 적용)"""
import heapq
import math


def build_adjacency(G, weight="length"):
    """도로망 그래프를 {출발노드: {도착노드: 거리(m)}} 형태로 변환.
    같은 두 교차로 사이에 도로가 여러 개면 가장 짧은 것만 남긴다."""
    adj = {n: {} for n in G.nodes}
    for u, v, data in G.edges(data=True):
        w = float(data.get(weight, 1.0))
        if v not in adj[u] or w < adj[u][v]:
            adj[u][v] = w
    return adj


def dijkstra(adj, source):
    """source에서 모든 노드까지의 최단거리. 도달 불가 노드는 결과에 없음."""
    dist = {source: 0.0}
    heap = [(0.0, source)]
    done = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        for v, w in adj[u].items():
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def distance_matrix(adj, nodes):
    """nodes[i] -> nodes[j] 도로 거리 행렬 (일방통행 때문에 비대칭일 수 있음)"""
    n = len(nodes)
    M = [[math.inf] * n for _ in range(n)]
    for i, s in enumerate(nodes):
        d = dijkstra(adj, s)
        for j, t in enumerate(nodes):
            M[i][j] = d.get(t, math.inf)
    return M


def haversine(lat1, lon1, lat2, lon2):
    """두 좌표 사이 직선거리(m)"""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
