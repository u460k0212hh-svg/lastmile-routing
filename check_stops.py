"""배송지 후보 점검: 배송지가 '차가 지나가기만 하는 도로' 위에 놓였는지 확인
- 도로망(차량 이동)은 건드리지 않는다. 배송지 후보로 적절한지만 본다.
- 판단 기준: 교차로에 연결된 도로(들어오는 길 + 나가는 길)가 전부
  자동차 전용도로(motorway, motorway_link)이면 '배송 접근 불가' 후보로 본다.
  연결 도로 중 motorway가 하나 섞여 있는 것만으로는 제외하지 않는다.

실행: python check_stops.py   (수정은 하지 않고 개수만 보고)
"""
import ast
import os
import random
from collections import Counter

import pandas as pd
import osmnx as ox

OUT = "data"
NO_ACCESS = {"motorway", "motorway_link"}


def road_types(G, n):
    """교차로 n에 연결된 모든 도로의 종류 (들어오는 길 + 나가는 길)"""
    types = set()
    for _, _, d in list(G.in_edges(n, data=True)) + list(G.out_edges(n, data=True)):
        h = d.get("highway", "unknown")
        if isinstance(h, str) and h.startswith("["):
            h = ast.literal_eval(h)
        types.update(h if isinstance(h, list) else [h])
    return types


def is_no_access(G, n):
    t = road_types(G, n)
    return bool(t) and t <= NO_ACCESS


def main():
    G = ox.load_graphml(os.path.join(OUT, "graph.graphml"))
    pts = pd.read_csv(os.path.join(OUT, "points.csv"))
    depot = int(pts.node[0])
    cands = [n for n in G.nodes if n != depot]

    # 1) 도로망 전체에서 접근 불가 교차로가 몇 개인지
    bad_all = [n for n in cands if is_no_access(G, n)]
    touch_mw = [n for n in cands if road_types(G, n) & NO_ACCESS]
    print(f"[도로망 전체] 교차로 {len(cands)}개 중")
    print(f"  - 자동차 전용도로에만 연결된 교차로(배송 접근 불가): {len(bad_all)}개")
    print(f"  - 자동차 전용도로가 하나 이상 연결된 교차로(참고):   {len(touch_mw)}개")
    type_count = Counter(t for n in cands for t in road_types(G, n))
    print("  - 교차로에 연결된 도로 종류 분포:", dict(type_count.most_common()))
    print(f"  - 출발점(터미널) 교차로 연결 도로: {sorted(road_types(G, depot))}")

    # 2) 실제 실험에 쓰인 배송지 중 문제 지점 (각 스크립트와 똑같은 방식으로 다시 뽑음)
    sets = {"1단계 points.csv (50곳)": [list(pts.node[1:])]}
    s2 = []
    for s in range(30):
        random.seed(1000 + s)
        s2.append(random.sample(cands, 50))
    sets["2단계 반복 실험 (50곳 × 30)"] = s2
    s3 = []
    for s in [7] + [2000 + k for k in range(20)]:
        rnd = random.Random(s)
        s3.append(rnd.sample(cands, 100))
    sets["3단계 대표+반복 실험 / 웹 기본 화면 (100곳 × 21)"] = s3

    print("\n[실험에 쓰인 배송지]")
    bad_set = set(bad_all)
    for name, groups in sets.items():
        total = sum(len(g) for g in groups)
        hits = [n for g in groups for n in g if n in bad_set]
        affected = sum(1 for g in groups if any(n in bad_set for n in g))
        print(f"  {name}: 배송지 {total}개 중 접근 불가 {len(hits)}개, 영향받은 시나리오 {affected}/{len(groups)}")

    if bad_all:
        rows = [{"node": n, "lat": G.nodes[n]["y"], "lon": G.nodes[n]["x"],
                 "도로 종류": ", ".join(sorted(road_types(G, n)))} for n in bad_all]
        pd.DataFrame(rows).to_csv(os.path.join(OUT, "no_access_nodes.csv"), index=False, encoding="utf-8-sig")
        print("\n접근 불가 교차로 목록 저장: data/no_access_nodes.csv")

    print("\n[판단]")
    if not bad_all:
        print("  접근 불가 교차로가 없음 -> 수정 불필요, 기존 수치 유지")
    else:
        print("  접근 불가 교차로가 도로망에 존재함.")
        print("  이를 후보에서 빼면 후보 목록이 바뀌어 모든 무작위 시나리오가 달라지므로,")
        print("  수정할 경우 1~3단계와 웹 화면 수치를 전부 재실행해야 함 (작업 원칙 1).")


if __name__ == "__main__":
    main()
