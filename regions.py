"""지역 설정 - 지역(구)과 터미널을 한 곳에서 관리한다.
미리 준비한 지역(PRESETS)은 도로망을 data 폴더에 저장해 두어 웹에서 바로 뜬다.
그 밖의 지역은 웹에서 '불러오기'를 누르면 OpenStreetMap에서 내려받는다."""

PRESETS = {
    "michuhol": {
        "label": "인천 미추홀구",
        "place": "Michuhol-gu, Incheon, South Korea",
        "depot": (37.439062, 126.648312),
        "depot_name": "CJ대한통운 택배 남동A터미널 (학익동 587-190)",
        "data": "data",
        "case_study": True,          # 반복 실험·검증을 수행한 사례 지역
    },
    "songpa": {
        "label": "서울 송파구",
        "place": "Songpa-gu, Seoul, South Korea",
        "depot": (37.474688, 127.123437),   # Plus Code F4FF+V9 (서울)
        "depot_name": "서울동남권물류단지 (장지동 671)",
        "data": "data_songpa",
        "case_study": False,
    },
}

# 웹에서 직접 불러올 수 있는 지역 (OpenStreetMap 검색용 이름)
CITIES = {
    "서울특별시": ["강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구", "노원구",
              "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구", "성북구", "송파구",
              "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"],
    # 인천은 2026년 행정구역 개편으로 경계가 바뀐 구가 있어, 개편 영향이 없는 구만 넣음
    "인천광역시": ["미추홀구", "연수구", "남동구", "부평구", "계양구"],
}


def place_query(city, gu):
    return f"{gu}, {city}, 대한민국"
