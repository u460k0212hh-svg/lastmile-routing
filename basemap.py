"""배경 지도 설정. 지도 서비스마다 정책이 달라 막힐 수 있어 여러 개를 넣고,
지도 오른쪽 위에서 잘 보이는 것을 골라 쓰도록 했다."""
import folium

BASEMAPS = [
    ("Esri 회색 지도",
     "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
     "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"),
    ("Esri 일반 지도",
     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
     "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"),
    ("OpenStreetMap",
     "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
     "&copy; OpenStreetMap contributors"),
]


def make_map(lat, lon, zoom=14, online_tiles=False):
    """기본은 인터넷 지도 없이 흰 배경 + 도로망(add_road_background)으로 그린다.
    online_tiles=True면 인터넷 배경 지도도 선택지로 넣는다."""
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None)
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container{background:#ffffff !important;}</style>"))
    if online_tiles:
        for name, url, attr in BASEMAPS:
            folium.TileLayer(tiles=url, attr=attr, name=name, overlay=False,
                             control=True, show=False).add_to(m)
    return m


def add_road_background(m, G, show=True):
    """인터넷 지도 없이도 보이도록, 내려받은 도로망 자체를 연한 회색 선으로 그린다."""
    layer = folium.FeatureGroup(name="도로망 (오프라인)", show=show)
    for u, v, data in G.edges(data=True):
        geom = data.get("geometry")
        if geom is not None:
            coords = [(y, x) for x, y in geom.coords]
        else:
            coords = [(G.nodes[u]["y"], G.nodes[u]["x"]), (G.nodes[v]["y"], G.nodes[v]["x"])]
        folium.PolyLine(coords, color="#c8c8c8", weight=1.5, opacity=0.9).add_to(layer)
    layer.add_to(m)
