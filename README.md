# 라스트마일 배송 경로 개선 (실제 도로망 + 차량 용량 제약)

인천 미추홀구 실제 도로망(OpenStreetMap) 위에서, 배송지와 박스 수가 주어졌을 때
차량 용량을 지키면서 총 주행거리가 짧은 차량별 배송 계획을 만든다.

- 웹 데모: https://lastmile-routing-ogsg2zgctlamjmi8vbqvj5.streamlit.app/
- 범위: 차량 주행거리 최소화. 주차·도보 이동·건물 내 배송·고객 대기시간은 포함하지 않음.
- 출발점(가정): CJ대한통운 택배 남동A터미널, 미추홀구 학익동 587-190 (37.439062, 126.648312).
  실제 배송 권역을 재현한 것은 아님.
- 용량 제약: 박스 수 기준 단순화(크기·중량 미고려).

## 지역과 터미널

`regions.py`에서 지역과 출발점을 관리한다. 웹 화면 왼쪽에서 지역을 고를 수 있다.

| 지역 | 출발점(가정) | 용도 |
|---|---|---|
| 인천 미추홀구 (`data/`) | CJ대한통운 택배 남동A터미널, 학익동 587-190 | 반복 실험·검증을 수행한 사례 지역 |
| 서울 송파구 (`data_songpa/`) | 서울동남권물류단지, 장지동 671 | 다른 지역에서의 동작 확인용 (성능 실험은 하지 않음) |
| 그 밖의 서울·인천 구 | 직접 입력한 좌표 또는 지역 중심 근처 임시 터미널 | 웹에서 '이 지역 불러오기'로 도로망을 내려받음 |

미리 준비할 지역 추가: `regions.py`에 항목을 넣고 `python step1_network.py 지역키` 실행.

## 실행

```
pip install -r requirements.txt
streamlit run app.py        # 웹 화면
python verify.py            # 검증 4종 (2~4분)
```

## 파일 구성

| 파일 | 역할 |
|---|---|
| `dijkstra.py` | 직접 구현한 다익스트라, 거리행렬 |
| `tsp.py` | 차량 1대: 구역 순서(기준), 최근접 이웃, 2-opt, Or-opt, 다중 시작, OR-Tools |
| `cvrp.py` | 차량 여러 대: 구역 분할(기준), 세이빙(Clarke & Wright), 차량별 순서 개선, OR-Tools, 유효성 검사 |
| `app.py`, `service.py`, `basemap.py` | streamlit 웹 화면 |
| `ortools_worker.py` | OR-Tools를 별도 프로세스로 실행 (Windows에서 pyarrow와의 DLL 충돌 회피) |
| `check_stops.py` | 배송지 후보 점검(자동차 전용도로에만 연결된 교차로 수 확인, 필터 아님) |
| `verify.py` | 검증: 다익스트라 정확성 / 배송 계획 유효성 / 개선 연산 / 작은 문제 전수 탐색 대비 품질 |

## 실험 재현과 결과 파일 (`data/`)

| 실행 | 결과 파일 | 조건 |
|---|---|---|
| `python step1_network.py` | `graph.graphml`, `points.csv`, `dist_matrix.npy`, `step1_map.html` | 도로망 다운로드(최초 1회), 터미널 + 배송지 50곳 |
| `python step2_tsp.py` | `step2_experiment.csv`, `step2_map.html` | 차량 1대, 배송지 50곳 × 30개 시나리오(seed 1000~1029), OR-Tools 탐색 제한 2초, 다중 시작 2초 설정 |
| `python step3_cvrp.py` | `step3_experiment.csv`, `step3_map.html` | 배송지 100곳 × 20개 시나리오(seed 2000~2019), 박스 1~3개, 용량 60, OR-Tools 탐색 제한 3초 |
| `python step4_ortools_time.py` | `step4_ortools_time.csv` | 위 실험의 앞 5개 시나리오씩 고정, OR-Tools 2·5·10·30초 비교 |

- 시간은 모두 같은 PC에서 측정한 경로 계산 시간(거리행렬 계산 제외).
- OR-Tools 결과(30초 포함)는 최적해를 보장하는 기준이 아님.
- `data_old_inha`(제출본에 포함 시): 출발점을 인하대 인근 임의 좌표로 둔 이전 실험, 터미널 위치 민감도 비교용.

지도 데이터 © OpenStreetMap contributors
