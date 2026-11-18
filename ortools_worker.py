"""OR-Tools를 별도 프로세스에서 실행 (웹 화면의 표/그래프 라이브러리(pyarrow)와 Windows DLL이 충돌해서 분리함)
입력: 표준입력 JSON {M, demand, capacity, seconds} / 출력: 차량별 경로 JSON"""
import json
import sys

from cvrp import ortools_cvrp

d = json.load(sys.stdin)
print(json.dumps(ortools_cvrp(d["M"], d["demand"], d["capacity"], d["seconds"])))
