# -*- coding: utf-8 -*-
"""Player UI and listening-statistics regression tests.

Run with the project build environment:
    .buildenv312\\Scripts\\python.exe _test_player_ui.py
"""
import json
import hashlib
import os
import socket
import sys
import tempfile
import time
import urllib.parse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import _cfg_sandbox  # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)

_tmp = tempfile.TemporaryDirectory(prefix="desktop-sing-player-test-")
os.environ["DESKTOP_SING_LISTEN_PATH"] = os.path.join(_tmp.name, "listening.json")

import lyrics_overlay as L  # noqa: E402
import lyrics_view as V  # noqa: E402
from app.lyrics_service import LyricsService  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFontMetrics  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402


FAILS = []


def check(name, cond, detail=""):
    print(("  ok  - " if cond else "  FAIL- ") + name
          + ((" | " + str(detail)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def seed(tracker, title, seconds, *, final=False, force=False):
    tracker.on_media({"title": title, "artist": "Test Artist",
                      "source": "test", "album": "ignored"})
    tracker._seconds = float(seconds)
    tracker._persisted_seconds = 0.0
    tracker._status = "PLAYING"
    tracker.flush(final=final, force=force)


app = QApplication.instance() or QApplication([])
L._load_fonts()
L.set_ui_lang("zh-CN")

# ---- ListeningStore / ListeningTracker ------------------------------------
path = os.path.join(_tmp.name, "tracker.json")
store = L.listening_store.ListeningStore(path)
enabled = [True]
tracker = L.listening_store.ListeningTracker(store, lambda: enabled[0])

seed(tracker, "Short", 10.0, final=True)
check("10 秒不落盘", not store.stats()["total_seconds"],
      store.stats())

seed(tracker, "Partial", 25.0)
stats = store.stats()
check("25 秒刷新后立即可见", stats["total_seconds"] == 25.0, stats)
check("刷新快照不计播放次数", stats["month_plays"] == 0, stats)

tracker.flush(final=False)
check("重复刷新不重复累计秒数", store.stats()["total_seconds"] == 25.0,
      store.stats())
tracker.flush(final=True)
stats = store.stats()
check("最终结算只计一次播放", stats["month_plays"] == 1, stats)
check("最终结算不重复累计秒数", stats["total_seconds"] == 25.0, stats)
tracker.flush(final=True)
check("重复最终结算无副作用", store.stats()["month_plays"] == 1,
      store.stats())

# Same-track SMTC metadata refreshes must not restart the session.
tracker.on_media({"title": "Stable", "artist": "Test Artist",
                  "source": "test"})
tracker._seconds = 18.0
tracker._status = "PLAYING"
for _ in range(4):
    tracker.on_media({"title": "Stable", "artist": "Test Artist",
                      "source": "test", "album": "metadata refresh"})
check("同曲元数据刷新不重置累计", tracker._seconds == 18.0,
      tracker._seconds)
tracker._seconds = 22.0
tracker.on_media({"title": "Next", "artist": "Test Artist",
                  "source": "test"})
check("切歌时最终结算上一首", store.stats()["month_plays"] == 2,
      store.stats())

# Disabling statistics must settle the current session first.
tracker.on_media({"title": "Disable", "artist": "Test Artist",
                  "source": "test"})
tracker._seconds = 31.0
tracker._status = "PLAYING"
enabled[0] = False
tracker.flush(final=True, force=True)
check("关闭统计前强制结算已听时长", store.stats()["total_seconds"] >= 78.0,
      store.stats())
check("关闭统计后本次播放计数一次", store.stats()["month_plays"] == 3,
      store.stats())
tracker.reset()
tracker.on_media({"title": "Ignored", "artist": "Test Artist",
                  "source": "test"})
tracker._seconds = 40.0
tracker._status = "PLAYING"
tracker.flush(final=True)
check("关闭统计后不再写入", "Ignored" not in
      [t["title"] for t in store.recent_tracks(20)],
      store.recent_tracks(20))
enabled[0] = True

# Clear then reset must not resurrect the in-memory session.
seed(tracker, "Before clear", 30.0)
tracker.flush(final=True, force=True)
store.clear()
tracker.reset()
tracker.flush(final=True)
check("清空后旧会话不回写", not store.recent_tracks(20),
      store.recent_tracks(20))

# ---- Playlist metadata -----------------------------------------------------
sample_playlist = "\n".join((
    "#EXTM3U",
    "#EXTINF:225,示例歌手 - 示例曲目",
    "https://example.com/sample.mp3",
    "02 - Second.mp3",
))
playlist_tracks = V._parse_m3u(sample_playlist)
check("M3U 只解析元数据",
      len(playlist_tracks) == 2
      and playlist_tracks[0]["title"] == "示例曲目"
      and playlist_tracks[0]["artist"] == "示例歌手"
      and playlist_tracks[0]["duration"] == 225.0
      and "audio_bytes" not in playlist_tracks[0],
      playlist_tracks)
check("M3U 按曲名歌手去重",
      len(V._parse_m3u(
          "#EXTM3U\n"
          "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/a.mp3\n"
          "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/b.mp3"
      )) == 1,
      V._parse_m3u("#EXTM3U\n"
                   "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/a.mp3\n"
                   "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/b.mp3"))
check("纯文本不解析为曲目", V._parse_m3u("这不是歌单") == [],
      V._parse_m3u("这不是歌单"))
check("歌单链接拒绝本地地址",
      not V._playlist_host_is_public("localhost")
      and not V._playlist_host_is_public("127.0.0.1"),
      (V._playlist_host_is_public("localhost"),
       V._playlist_host_is_public("127.0.0.1")))
check("私网与保留地址全部拒绝",
      not V._playlist_public_addresses("127.0.0.1")
      and not V._playlist_public_addresses("169.254.169.254")
      and not V._playlist_public_addresses("0.0.0.0"),
      (V._playlist_public_addresses("127.0.0.1"),
       V._playlist_public_addresses("169.254.169.254"),
       V._playlist_public_addresses("0.0.0.0")))
check("CGNAT 与云元数据地址拒绝",
      not V._playlist_public_addresses("100.64.0.1")
      and not V._playlist_public_addresses("100.100.100.200")
      and not V._playlist_public_addresses("192.168.1.1"),
      (V._playlist_public_addresses("100.64.0.1"),
       V._playlist_public_addresses("100.100.100.200"),
       V._playlist_public_addresses("192.168.1.1")))
check("公网地址放行",
      bool(V._playlist_public_addresses("8.8.8.8"))
      and bool(V._playlist_public_addresses("1.1.1.1")),
      (V._playlist_public_addresses("8.8.8.8"),
       V._playlist_public_addresses("1.1.1.1")))
check("IPv6 环回拒绝且公网放行",
      not V._playlist_public_addresses("::1")
      and bool(V._playlist_public_addresses("2606:4700:4700::1111")),
      (V._playlist_public_addresses("::1"),
       V._playlist_public_addresses("2606:4700:4700::1111")))
check("QQ 平台链接放行，其他平台仍拒绝",
      V._playlist_is_platform_url("music.163.com")
      and V._playlist_is_platform_url("y.qq.com")
      and V._qq_playlist_host("y.qq.com")
      and V._qq_playlist_host("c6.y.qq.com")
      and not V._qq_playlist_host("music.163.com")
      and not V._qq_playlist_host("evil-qq.com"),
      (V._playlist_is_platform_url("music.163.com"),
       V._qq_playlist_host("y.qq.com"),
       V._qq_playlist_host("c6.y.qq.com"),
       V._qq_playlist_host("evil-qq.com")))

# ---- QQ Music share links -------------------------------------------------
qq_share = ("分享歌单「易入人心的华语民谣」："
            "https://c6.y.qq.com/base/fcgi-bin/u?__=6RTHDHu5qQ6d "
            "（来自 QQ 音乐）")
check("QQ 分享文本提取短链",
      V._extract_playlist_url(qq_share)
      == "https://c6.y.qq.com/base/fcgi-bin/u?__=6RTHDHu5qQ6d",
      V._extract_playlist_url(qq_share))
check("M3U 链接仍可从带说明文本中提取",
      V._extract_playlist_url(
          "我的歌单：https://example.com/list.m3u8，复制后打开")
      == "https://example.com/list.m3u8",
      V._extract_playlist_url(
          "我的歌单：https://example.com/list.m3u8，复制后打开"))

qq_ids = [
    ("网页歌单", "https://y.qq.com/n/ryqq/playlist/1374105607"),
    ("详情页", "https://y.qq.com/n/ryqq/playlistDetail/1374105607"),
    ("手机分享页", "https://i.y.qq.com/n2/m/share/details/taoge.html"
                   "?ADTAG=pc_v17&id=1374105607&openinqqmusic=1"),
]
check("QQ 歌单 ID 支持三种分享路径",
      all(V._qq_playlist_id_in_url(url) == "1374105607"
          for _name, url in qq_ids),
      [(name, V._qq_playlist_id_in_url(url)) for name, url in qq_ids])
check("QQ 链接缺少歌单 ID 不臆造",
      V._qq_playlist_id_in_url("https://y.qq.com/n/ryqq/playlist/")
      == "")
check("QQ 歌曲链路不误读歌单 ID",
      V._qq_playlist_id_in_url(
          "https://y.qq.com/n/ryqq/songDetail/003abc?id=1374105607")
      == "")
check("QQ 短链重定向只能落在 QQ 域",
      V._qq_playlist_host("i.y.qq.com")
      and not V._qq_playlist_host("i.y.qq.com.evil.example"))

qq_payload = {
    "code": 0,
    "subcode": 0,
    "cdlist": [{
        "disstid": "1374105607",
        "dissname": "易入人心的华语民谣",
        "songlist": [
            {"songname": "当你老了", "songmid": "mid-1",
             "singer": [{"name": "赵照"}], "interval": 310,
             "albumname": "示例专辑"},
            {"songname": "当你老了", "songmid": "mid-1",
             "singer": [{"name": "赵照"}], "interval": 310,
             "albumname": "示例专辑"},
            {"songname": "南山南", "songmid": "mid-2",
             "singer": [{"name": "马頔"}, {"name": "其他"}],
             "interval": "325", "albumname": "孤岛"},
        ],
    }],
}
qq_tracks = V._parse_qq_playlist_payload(qq_payload)
check("QQ 歌单只解析元数据并去重",
      len(qq_tracks) == 2
      and qq_tracks[0]["title"] == "当你老了"
      and qq_tracks[0]["artist"] == "赵照"
      and qq_tracks[0]["duration"] == 310.0
      and qq_tracks[0]["source"] == "qqmusic:mid-1"
      and qq_tracks[1]["artist"] == "马頔 / 其他"
      and qq_tracks[1]["duration"] == 325.0
      and "audio_bytes" not in qq_tracks[0],
      qq_tracks)


def _raises_value(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


check("QQ 适配器拒绝非 QQ 主机",
      _raises_value(V._qq_request_once, "https://evil.example/x",
                    headers={}))
check("QQ 空歌单/错误响应不产出假曲目",
      _raises_value(V._parse_qq_playlist_payload, {"code": 1})
      and _raises_value(V._parse_qq_playlist_payload,
                        {"code": 0, "cdlist": []})
      and _raises_value(V._parse_qq_playlist_payload,
                        {"code": 0, "cdlist": [{"songlist": []}]})
      and _raises_value(V._parse_qq_playlist_payload,
                        {"code": 0, "cdlist": [{
                            "total_song_num": 1001,
                            "songlist": [{"songname": "A"}]}]}))

original_qq_follow = V._qq_follow
qq_api_urls = []


def _fake_qq_follow(url, **kwargs):
    qq_api_urls.append(url)
    return url, json.dumps(qq_payload).encode("utf-8")


V._qq_follow = _fake_qq_follow
try:
    qq_api_tracks = V._fetch_qq_playlist_tracks(
        "https://y.qq.com/n/ryqq/playlist/1374105607")
finally:
    V._qq_follow = original_qq_follow
check("QQ 歌单导入请求公开 API 且不取音频",
      len(qq_api_tracks) == 2
      and "disstid=1374105607" in qq_api_urls[0]
      and "fcg_ucc_getcdinfo_byids_cp.fcg" in qq_api_urls[0],
      qq_api_urls)

original_loader = V._load_playlist_tracks
qq_thread_calls = []
V._load_playlist_tracks = lambda url: qq_thread_calls.append(url) or qq_tracks
qq_results = []
qq_failures = []
qq_thread = V.PlaylistFetchThread(
    "https://c6.y.qq.com/base/fcgi-bin/u?__=6RTHDHu5qQ6d")
qq_thread.completed.connect(qq_results.append)
qq_thread.failed.connect(qq_failures.append)
try:
    qq_thread.run()
finally:
    V._load_playlist_tracks = original_loader
app.processEvents()
check("QQ 短链导入线程可完成",
      qq_results == [qq_tracks] and not qq_failures
      and qq_thread_calls == [
          "https://c6.y.qq.com/base/fcgi-bin/u?__=6RTHDHu5qQ6d"],
      (qq_results, qq_failures, qq_thread_calls))


# ---- Multi-platform playlist imports --------------------------------------
platform_hosts = [
    ("qq", "y.qq.com"),
    ("netease", "music.163.com"),
    ("netease", "y.music.163.com"),
    ("netease", "163cn.tv"),
    ("kugou", "m.kugou.com"),
    ("kugou", "gateway.kugou.com"),
    ("kuwo", "m.kuwo.cn"),
    ("migu", "music.migu.cn"),
    ("migu", "h5.nf.migu.cn"),
]
check("五个平台 host 判定",
      all(V._playlist_platform_kind(host) == kind
          for kind, host in platform_hosts)
      and V._playlist_platform_kind("evil-kugou.com") == ""
      and V._playlist_platform_kind("kugou.com.evil.example") == ""
      and V._playlist_platform_kind("open.spotify.com") == ""
      and V._playlist_is_platform_url("open.spotify.com"),
      [(host, V._playlist_platform_kind(host))
       for _kind, host in platform_hosts])

netease_ids = [
    ("hash 路由", "https://music.163.com/#/playlist?id=3778678"),
    ("手机分享", "https://y.music.163.com/m/playlist?id=3778678&userid=1"),
    ("路径形式", "https://music.163.com/playlist/3778678"),
]
check("网易云歌单 ID 支持三种分享路径",
      all(V._netease_playlist_id_in_url(url) == "3778678"
          for _name, url in netease_ids),
      [(name, V._netease_playlist_id_in_url(url))
       for name, url in netease_ids])

kugou_ids = [
    ("网页歌单", "https://www.kugou.com/yy/special/single/9126490.html"),
    ("移动歌单", "https://m.kugou.com/plist/list/9126490?json=true"),
    ("分享页", "https://www.kugou.com/share/abc?id=9126490"),
]
check("酷狗歌单 ID 支持三种分享路径",
      all(V._kugou_playlist_id_in_url(url) == "9126490"
          for _name, url in kugou_ids),
      [(name, V._kugou_playlist_id_in_url(url))
       for name, url in kugou_ids])
check("酷狗 global_collection_id 优先复用",
      V._kugou_global_id_in_url(
          "https://m.kugou.com/plist/list/1?global_collection_id="
          "collection_3_9126490_4_0")
      == "collection_3_9126490_4_0")

kuwo_ids = [
    ("网页歌单", "https://www.kuwo.cn/playlist_detail/2952464073"),
    ("移动歌单", "https://m.kuwo.cn/newh5app/playlist_detail/2952464073"),
]
check("酷我歌单 ID 支持两种分享路径",
      all(V._kuwo_playlist_id_in_url(url) == "2952464073"
          for _name, url in kuwo_ids),
      [(name, V._kuwo_playlist_id_in_url(url))
       for name, url in kuwo_ids])

migu_ids = [
    ("网页歌单", "https://music.migu.cn/v3/music/playlist/115481041"),
    ("H5 分享", "https://h5.nf.migu.cn/music/playlist?playlistId=115481041"),
]
check("咪咕歌单 ID 支持两种分享路径",
      all(V._migu_playlist_id_in_url(url) == "115481041"
          for _name, url in migu_ids),
      [(name, V._migu_playlist_id_in_url(url))
       for name, url in migu_ids])

netease_payload = {
    "code": 200,
    "playlist": {
        "trackCount": 3,
        "tracks": [
            {"name": "晴天", "id": 186016, "ar": [{"name": "周杰伦"}],
             "al": {"name": "叶惠美"}, "dt": 269000},
            {"name": "晴天", "id": 186016, "ar": [{"name": "周杰伦"}],
             "al": {"name": "叶惠美"}, "dt": 269000},
            {"name": "七里香", "id": 185811,
             "artists": [{"name": "周杰伦"}],
             "album": {"name": "七里香"}, "dt": "299000"},
        ],
    },
}
netease_tracks = V._parse_netease_playlist_payload(netease_payload)
check("网易云歌单只解析元数据并去重",
      len(netease_tracks) == 2
      and netease_tracks[0]["title"] == "晴天"
      and netease_tracks[0]["artist"] == "周杰伦"
      and netease_tracks[0]["duration"] == 269.0
      and netease_tracks[0]["source"] == "netease:186016"
      and netease_tracks[1]["duration"] == 299.0
      and "audio_bytes" not in netease_tracks[0],
      netease_tracks)
check("网易云空歌单/错误响应不产出假曲目",
      _raises_value(V._parse_netease_playlist_payload, {"code": 400})
      and _raises_value(V._parse_netease_playlist_payload,
                        {"code": 200, "playlist": {"tracks": []}})
      and _raises_value(V._parse_netease_playlist_payload,
                        {"code": 200, "playlist": {
                            "trackCount": 1001, "tracks": [{"name": "A"}]}}))

original_follow = V._platform_follow
netease_api_urls = []


def _fake_netease_follow(url, **kwargs):
    netease_api_urls.append(url)
    return url, json.dumps(netease_payload).encode("utf-8")


V._platform_follow = _fake_netease_follow
try:
    netease_api_tracks = V._fetch_netease_playlist_tracks(
        "https://music.163.com/#/playlist?id=3778678")
finally:
    V._platform_follow = original_follow
check("网易云导入请求公开 API 且不取音频",
      len(netease_api_tracks) == 2
      and len(netease_api_urls) == 1
      and "/api/v6/playlist/detail?id=3778678" in netease_api_urls[0]
      and netease_api_urls[0].startswith("https://music.163.com/"),
      netease_api_urls)

kugou_signature = V._kugou_signature({"b": 2, "a": 1})
expected_signature = hashlib.md5(
    (V._KUGOU_SIGN_SALT + "a=1b=2" + V._KUGOU_SIGN_SALT).encode("utf-8")
).hexdigest()
check("酷狗签名按 MIT 文档的方案计算",
      kugou_signature == expected_signature, kugou_signature)

original_global_id = V._kugou_playlist_global_id
original_kugou_payload = V._kugou_api_payload
kugou_params = []


def _fake_global_id(_url):
    return "collection_3_9126490_4_0"


def _fake_kugou_payload(params):
    kugou_params.append(dict(params))
    return {"error_code": 0, "data": {
        "count": 2,
        "songs": [
            {"name": "周杰伦 - 晴天", "singerinfo": [{"name": "周杰伦"}],
             "albuminfo": {"name": "叶惠美"}, "timelen": 269000,
             "hash": "H1"},
            {"name": "七里香", "singerinfo": [{"name": "周杰伦"}],
             "albuminfo": {"name": "七里香"}, "timelength": "299000",
             "hash": "H2"},
        ],
    }}


V._kugou_playlist_global_id = _fake_global_id
V._kugou_api_payload = _fake_kugou_payload
try:
    kugou_tracks = V._fetch_kugou_playlist_tracks(
        "https://www.kugou.com/yy/special/single/9126490.html")
finally:
    V._kugou_playlist_global_id = original_global_id
    V._kugou_api_payload = original_kugou_payload
check("酷狗歌单按 global id 分页并解析元数据",
      len(kugou_tracks) == 2
      and kugou_tracks[0]["title"] == "晴天"
      and kugou_tracks[0]["artist"] == "周杰伦"
      and kugou_tracks[0]["duration"] == 269.0
      and kugou_tracks[1]["title"] == "七里香"
      and kugou_tracks[1]["duration"] == 299.0
      and kugou_params[0]["begin_idx"] == 0
      and kugou_params[0]["global_collection_id"]
      == "collection_3_9126490_4_0",
      (kugou_tracks, kugou_params))

kugou_api_urls = []
V._platform_follow = (
    lambda url, **kwargs: (kugou_api_urls.append(url)
                           or (url, b'{"error_code":0}'))
)
try:
    V._kugou_api_payload({"begin_idx": 100,
                          "global_collection_id":
                          "collection_3_9126490_4_0"})
finally:
    V._platform_follow = original_follow
_kugou_query = dict(urllib.parse.parse_qs(
    urllib.parse.urlparse(kugou_api_urls[0]).query))
check("酷狗 API 使用签名 gateway 且只取元数据",
      "get_other_list_file_nofilt" in kugou_api_urls[0]
      and _kugou_query.get("begin_idx") == ["100"]
      and len(_kugou_query.get("signature", [""])[0]) == 32
      and "mp3" not in kugou_api_urls[0].lower(),
      kugou_api_urls)

kuwo_payload = {
    "code": 200,
    "data": {
        "total": 3,
        "musicList": [
            {"name": "晴天", "artist": "周杰伦", "duration": 269,
             "album": "叶惠美", "musicrid": "MUSIC_1"},
            {"name": "晴天", "artist": "周杰伦", "duration": 269,
             "album": "叶惠美", "musicrid": "MUSIC_1"},
            {"name": "七里香", "artist": "周杰伦", "duration": "299",
             "album": "七里香", "musicrid": "MUSIC_2"},
        ],
    },
}
kuwo_api_urls = []


def _fake_kuwo_follow(url, **kwargs):
    kuwo_api_urls.append(url)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if query.get("pn") == ["1"]:
        return url, json.dumps(kuwo_payload).encode("utf-8")
    return url, json.dumps(
        {"code": 200, "data": {"total": 3, "musicList": []}}
    ).encode("utf-8")


V._platform_follow = _fake_kuwo_follow
try:
    kuwo_tracks = V._fetch_kuwo_playlist_tracks(
        "https://www.kuwo.cn/playlist_detail/2952464073")
finally:
    V._platform_follow = original_follow
check("酷我歌单解析元数据并去重",
      len(kuwo_tracks) == 2
      and kuwo_tracks[0]["title"] == "晴天"
      and kuwo_tracks[0]["duration"] == 269.0
      and kuwo_tracks[1]["album"] == "七里香"
      and kuwo_tracks[1]["source"] == "kuwo:MUSIC_2"
      and len(kuwo_api_urls) == 2
      and "pid=2952464073" in kuwo_api_urls[0]
      and "pn=1" in kuwo_api_urls[0]
      and "rn=100" in kuwo_api_urls[0],
      (kuwo_tracks, kuwo_api_urls))

migu_payload = {
    "code": "000000",
    "data": {
        "totalCount": 2,
        "songList": [
            {"songName": "晴天", "singerList": [{"name": "周杰伦"}],
             "album": "叶惠美", "duration": 269, "contentId": "C1"},
            {"songName": "七里香", "singerList": [{"name": "周杰伦"}],
             "album": "七里香", "duration": "299", "contentId": "C2"},
        ],
    },
}
migu_api_urls = []
V._platform_follow = (
    lambda url, **kwargs: (migu_api_urls.append(url)
                           or (url,
                               json.dumps(migu_payload).encode("utf-8")))
)
try:
    migu_tracks = V._fetch_migu_playlist_tracks(
        "https://music.migu.cn/v3/music/playlist/115481041")
finally:
    V._platform_follow = original_follow
check("咪咕歌单解析元数据并去重",
      len(migu_tracks) == 2
      and migu_tracks[0]["artist"] == "周杰伦"
      and migu_tracks[1]["duration"] == 299.0
      and migu_tracks[1]["source"] == "migu:C2"
      and len(migu_api_urls) == 1
      and "app.c.nf.migu.cn" in migu_api_urls[0]
      and "playlistId=115481041" in migu_api_urls[0]
      and "pageSize=50" in migu_api_urls[0],
      (migu_tracks, migu_api_urls))

check("平台适配器拒绝白名单外主机",
      _raises_value(V._platform_request_once,
                    "https://evil.example/playlist",
                    host_check=V._kugou_playlist_host, headers={}))

dispatch_calls = []
_dispatch_names = ("_fetch_qq_playlist_tracks", "_fetch_netease_playlist_tracks",
                   "_fetch_kugou_playlist_tracks", "_fetch_kuwo_playlist_tracks",
                   "_fetch_migu_playlist_tracks")
_dispatch_originals = {name: getattr(V, name) for name in _dispatch_names}
for _name in _dispatch_names:
    setattr(V, _name,
            lambda url, _n=_name: dispatch_calls.append(_n)
            or [{"title": _n, "artist": "", "duration": 0.0,
                 "source": ""}])
try:
    for _kind, _host in (
            ("qq", "y.qq.com"), ("netease", "music.163.com"),
            ("kugou", "m.kugou.com"), ("kuwo", "m.kuwo.cn"),
            ("migu", "music.migu.cn")):
        V._load_playlist_tracks("https://%s/playlist" % _host)
finally:
    for _name, _func in _dispatch_originals.items():
        setattr(V, _name, _func)
check("歌单导入按平台分派到对应适配器",
      len(dispatch_calls) == 5
      and [name.split("_")[2] for name in dispatch_calls]
      == ["qq", "netease", "kugou", "kuwo", "migu"],
      dispatch_calls)


class _FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self):
        self.slots = []


class _FakeFetchThread:
    last = None

    def __init__(self, url, parent=None):
        self.url = url
        self.completed = _FakeSignal()
        self.failed = _FakeSignal()
        _FakeFetchThread.last = self

    def start(self):
        pass


original_thread = V.PlaylistFetchThread
playlist_page = V.PlaylistPage(L._tr)
V.PlaylistFetchThread = _FakeFetchThread
try:
    for _kind, _url in (
            ("netease", "https://music.163.com/#/playlist?id=3778678"),
            ("kugou", "https://www.kugou.com/yy/special/single/9126490.html"),
            ("kuwo", "https://www.kuwo.cn/playlist_detail/2952464073"),
            ("migu", "https://music.migu.cn/v3/music/playlist/115481041")):
        playlist_page.url_input.setText(_url)
        playlist_page._import_url()
        check("歌单输入框放行 %s 平台链接" % _kind,
              playlist_page._state == "loading"
              and _FakeFetchThread.last.url == _url,
              (playlist_page._state,
               getattr(_FakeFetchThread.last, "url", None)))
        playlist_page._cancel_import()
    playlist_page.url_input.setText(
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    playlist_page._import_url()
    check("未支持平台给出导出提示且不起线程",
          playlist_page._state == "error"
          and "M3U/M3U8" in playlist_page.error.text()
          and _FakeFetchThread.last.url
          == "https://music.migu.cn/v3/music/playlist/115481041",
          (playlist_page._state, playlist_page.error.text()))
finally:
    V.PlaylistFetchThread = original_thread
    playlist_page.deleteLater()


fetch_results = []
fetch_failures = []
fetch_thread = V.PlaylistFetchThread("https://example.com/playlist.m3u8")
fetch_thread.completed.connect(fetch_results.append)
fetch_thread.failed.connect(fetch_failures.append)
original_fetch = V._fetch_playlist_bytes
V._fetch_playlist_bytes = lambda url: sample_playlist.encode("utf-8")
try:
    fetch_thread.run()
finally:
    V._fetch_playlist_bytes = original_fetch
app.processEvents()
check("歌单 URL 导入线程可完成",
      fetch_results == [playlist_tracks]
      and not fetch_failures,
      (fetch_results, fetch_failures))


# ---- Playlist status column must fit localized text ------------------------
status_width_rows = []
status_clip_rows = []
for status_lang in ("zh-CN", "zh-TW", "en", "ja"):
    L.set_ui_lang(status_lang)
    row = V.PlaylistRowButton(
        {"title": "示例曲目", "artist": "示例歌手", "duration": 225.0}, L._tr)
    row.setStyleSheet(
        "QLabel#playlistStatus { font-size:12px; font-weight:500; }")
    row.resize(760, 56)
    row.show()
    app.processEvents()
    for status_matched in (False, True):
        row._has_local_lyrics = lambda value=status_matched: value
        row._update_status_state()
        app.processEvents()
        status_metrics = QFontMetrics(row.status.font())
        status_needed = status_metrics.horizontalAdvance(row.status.text())
        status_width_rows.append((status_lang, status_matched, status_needed,
                                  row.status.width(),
                                  row.status.minimumWidth(),
                                  row.status.toolTip(),
                                  row.accessibleName()))
        status_tooltip_ok = row.status.toolTip() == row.status.text()
        status_access_ok = row.status.text() in row.accessibleName()
        if (row.status.width() < status_needed
                or row.status.minimumWidth() < status_needed
                or not status_tooltip_ok or not status_access_ok):
            status_clip_rows.append(
                (status_lang, status_matched, status_needed,
                 row.status.width(), row.status.minimumWidth(),
                 status_tooltip_ok, status_access_ok))
    row.close()
    row.deleteLater()
L.set_ui_lang("zh-CN")
check("歌单状态列四语言不被裁切（含 tooltip/accessibleName）",
      not status_clip_rows, status_clip_rows)
ja_unmatched_needed = next(
    needed for lang, matched, needed, *_ in status_width_rows
    if lang == "ja" and not matched)
check("ja unmatched 文本宽度超过旧 112px 硬编码（旧布局必裁）",
      ja_unmatched_needed > 112, ja_unmatched_needed)

class _RedirectResponse:
    def __init__(self, status, headers):
        self.status = status
        self.headers = headers
    def getheader(self, name):
        return self.headers.get(name)
    def read(self, count=-1):
        return b""

class _RedirectConnection:
    requests = []
    def __init__(self, *args, **kwargs):
        self.pinned_ip = ""
    def request(self, method, path, headers=None):
        _RedirectConnection.requests.append(path)
    def getresponse(self):
        if len(_RedirectConnection.requests) == 1:
            return _RedirectResponse(302,
                                     {"Location": "http://127.0.0.1/x.m3u"})
        return _RedirectResponse(200, {})
    def close(self):
        pass

original_pinned_connection = V._PinnedHTTPSConnection
_RedirectConnection.requests.clear()
V._PinnedHTTPSConnection = _RedirectConnection
redirect_failure = ""
try:
    try:
        V._fetch_playlist_bytes("https://example.com/redirect.m3u")
    except Exception as exc:
        redirect_failure = str(exc)
finally:
    V._PinnedHTTPSConnection = original_pinned_connection
check("重定向到私网被拒绝",
      redirect_failure == "private-playlist-host"
      and _RedirectConnection.requests == ["/redirect.m3u"],
      (redirect_failure, _RedirectConnection.requests))

# ---- HTTPS playlist connections must wrap TLS over the pinned socket ------
class _FakePinnedSocket:
    def setsockopt(self, *args):
        pass


class _FakeTLSContext:
    def __init__(self):
        self.calls = []
        self.wrapped = _FakePinnedSocket()

    def wrap_socket(self, sock, server_hostname=None):
        self.calls.append((sock, server_hostname))
        return self.wrapped


tls_context = _FakeTLSContext()
https_conn = V._PinnedHTTPSConnection(
    "raw.githubusercontent.com", 443, timeout=5.0, context=tls_context)
https_conn.pinned_ip = "93.184.216.34"
connect_targets = []
https_conn._create_connection = (
    lambda address, timeout=None, source_address=None:
    connect_targets.append(address) or _FakePinnedSocket())
https_conn.connect()
check("HTTPS 连接 pin 到已校验 IP", connect_targets == [("93.184.216.34", 443)],
      connect_targets)
check("HTTPS 连接执行 TLS 包装",
      len(tls_context.calls) == 1
      and tls_context.calls[0][1] == "raw.githubusercontent.com",
      tls_context.calls)
check("HTTPS 连接使用 TLS socket", https_conn.sock is tls_context.wrapped,
      type(getattr(https_conn, "sock", None)).__name__)


class _PlaylistResponse:
    status = 200

    def getheader(self, name):
        return None

    def read(self, count=-1):
        return b"#EXTM3U\n#EXTINF:90,Pinned - Track\nhttps://example.com/x.mp3\n"


class _PlaylistHTTPSConnection:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.pinned_ip = ""
        self.closed = False
        _PlaylistHTTPSConnection.instances.append(self)

    def request(self, method, path, headers=None):
        self.request_path = path

    def getresponse(self):
        return _PlaylistResponse()

    def close(self):
        self.closed = True


original_resolve = V._playlist_public_addresses
original_https = V._PinnedHTTPSConnection
_PlaylistHTTPSConnection.instances.clear()
V._playlist_public_addresses = lambda host: [("93.184.216.34", 0)]
V._PinnedHTTPSConnection = _PlaylistHTTPSConnection
try:
    fetched = V._fetch_playlist_bytes("https://example.com/list.m3u")
finally:
    V._playlist_public_addresses = original_resolve
    V._PinnedHTTPSConnection = original_https
fetched_conn = (_PlaylistHTTPSConnection.instances[0]
                if _PlaylistHTTPSConnection.instances else None)
check("https 歌单抓取走 TLS 连接并返回数据",
      fetched.startswith(b"#EXTM3U") and fetched_conn is not None
      and fetched_conn.pinned_ip == "93.184.216.34" and fetched_conn.closed,
      (fetched[:14], getattr(fetched_conn, "pinned_ip", None)))


# ---- Multi-IP fallback: try each pinned address before giving up ----------
class _MultiIpConnection(_PlaylistHTTPSConnection):
    attempts = []

    def getresponse(self):
        _MultiIpConnection.attempts.append(self.pinned_ip)
        if self.pinned_ip == "203.0.113.10":
            raise socket.timeout("pinned ip unreachable")
        return _PlaylistResponse()


_MultiIpConnection.attempts.clear()
V._playlist_public_addresses = lambda host: [
    ("203.0.113.10", 0), ("203.0.113.11", 0)]
V._PinnedHTTPSConnection = _MultiIpConnection
multi_ip_data = b""
multi_ip_error = ""
try:
    try:
        multi_ip_data = V._fetch_playlist_bytes("https://example.com/list.m3u")
    except Exception as exc:
        multi_ip_error = str(exc)
finally:
    V._playlist_public_addresses = original_resolve
    V._PinnedHTTPSConnection = original_https
check("多 IP 回退：首个地址超时后改用下一个",
      multi_ip_data.startswith(b"#EXTM3U") and not multi_ip_error
      and _MultiIpConnection.attempts == ["203.0.113.10", "203.0.113.11"],
      (multi_ip_data[:14], multi_ip_error, _MultiIpConnection.attempts))


class _DeadIpConnection(_PlaylistHTTPSConnection):
    attempts = []

    def getresponse(self):
        _DeadIpConnection.attempts.append(self.pinned_ip)
        raise ConnectionResetError("pinned ip reset")


_DeadIpConnection.attempts.clear()
V._playlist_public_addresses = lambda host: [
    ("203.0.113.20", 0), ("203.0.113.21", 0)]
V._PinnedHTTPSConnection = _DeadIpConnection
dead_ip_error = ""
dead_ip_type = ""
try:
    try:
        V._fetch_playlist_bytes("https://example.com/list.m3u")
    except Exception as exc:
        dead_ip_error = str(exc)
        dead_ip_type = type(exc).__name__
finally:
    V._playlist_public_addresses = original_resolve
    V._PinnedHTTPSConnection = original_https
check("多 IP 回退：全部失败时抛最后一个错误",
      dead_ip_type == "ConnectionResetError"
      and _DeadIpConnection.attempts == ["203.0.113.20", "203.0.113.21"],
      (dead_ip_type, dead_ip_error, _DeadIpConnection.attempts))

# ---- Real main player construction ----------------------------------------
ov = L.LyricOverlay(L.MediaWatcher())
ov.song = {"title": "夜航西飞", "artist": "示例歌手", "source": "test",
           "duration": 240.0}
ov.lines = [[0.0, "灯光从窗边慢慢退去"], [6.0, "我把今天折进风里"],
            [12.0, "沿着没有名字的街道"], [18.0, "听见城市轻轻呼吸"]]
ov._trans_map = {0: "The lights fade slowly", 1: "I fold today into the wind"}
ov.duration = 240.0
ov.status = "PLAYING"
ov.anchor_pos = 8.0
ov.anchor_ts = time.monotonic()
ov.current_resume_id = lambda: ""

lyrics_cache_dir = tempfile.mkdtemp(prefix="desktop-sing-lyrics-cache-")
old_cache_dir = L.CACHE_DIR
L.CACHE_DIR = lyrics_cache_dir
lyrics_service = LyricsService(L)
ov.lyrics_service = lyrics_service
with open(lyrics_service.cache_path("示例曲目", "示例歌手"), "w",
          encoding="utf-8") as handle:
    json.dump({"v": 4, "lines": [[0.0, "第一句"], [3.0, "第二句"]],
               "trans": [[0.1, "First"], [3.1, "Second"]],
               "words": {}, "sk": False, "roma": []},
              handle, ensure_ascii=False)

player = V.MainPlayerWindow(ov)
player.resize(1260, 820)
player.show()
app.processEvents()
player._refresh_now(force=True)
player._timer.stop()
player.now.update_progress(72.0, 240.0, True)
app.processEvents()

check("主播放器窗口可构造", player.isVisible(), player.size())
check("窗口标题正确", "正在播放" in player.windowTitle(),
      player.windowTitle())
check("进度条挂在播放条下", player.now.slider.parent() is player.now.bar,
      type(player.now.slider.parent()).__name__)
check("进度条可见且有宽度", player.now.slider.isVisible()
      and player.now.slider.width() >= 80, player.now.slider.geometry())
check("进度条与播放条相交",
      player.now.slider.geometry().intersects(player.now.bar.rect()),
      (player.now.slider.geometry(), player.now.bar.rect()))
check("进度值已更新", player.now.slider.value() == 300,
      player.now.slider.value())
check("播放条滑轨左右对称",
      player.now.slider.x() == 20
      and player.now.bar.width() - player.now.slider.geometry().right() - 1 == 20,
      (player.now.slider.x(), player.now.slider.geometry().right(),
       player.now.bar.width()))
check("QSizeGrip 透明且收在圆角内",
      isinstance(player.grip, V._SizeGrip)
      and player.grip.testAttribute(Qt.WA_TranslucentBackground)
      and player.grip.geometry().right() < player.shell.width() - 6
      and player.grip.geometry().bottom() < player.shell.height() - 6,
      (player.grip.geometry(), player.shell.size()))
player._timer.start()

player.navigate("report")
app.processEvents()
check("听歌报告入口可用", player.stack.currentWidget() is player.report)
check("榜首时长使用强调色",
      player.report.artist_meta.objectName() == "artistMeta"
      and "QLabel#artistMeta" in player.shell.styleSheet(),
      (player.report.artist_meta.objectName(),
       "QLabel#artistMeta" in player.shell.styleSheet()))
check("报告空态给出明确的 20 秒规则",
      player.report.empty.isVisible()
      and "20" in player.report.empty.text(), player.report.empty.text())
check("报告空态隐藏零值图表",
      not player.report.spark.isVisible()
      and not player.report.artist_card.isVisible()
      and not player.report.today.isVisible(),
      (player.report.spark.isVisible(), player.report.artist_card.isVisible(),
       player.report.today.isVisible()))

narrow_report = V.ReportPage(L._tr)
narrow_report.resize(884, 620)
narrow_report.set_stats({
    "total_seconds": 7200, "month_tracks": 12, "month_minutes": 120,
    "streak": 4, "active_days": 9, "daily": [],
    "top_artists": [{"name": "Demo", "seconds": 3200}],
    "top_tracks": [{"title": "Track", "artist": "Demo", "seconds": 3200}],
})
narrow_report.show()
app.processEvents()
check("报告页窄高可滚动",
      narrow_report.scroll.verticalScrollBar().maximum() > 0,
      narrow_report.scroll.verticalScrollBar().maximum())
check("报告页 spark 不越出 hero",
      narrow_report.spark.geometry().bottom()
      <= narrow_report.hero.contentsRect().bottom(),
      (narrow_report.spark.geometry(),
       narrow_report.hero.contentsRect()))

canvas_metrics = V.LyricsCanvas(L._tr)
translation_rect = canvas_metrics._translation_rect(100.0, 600.0)
next_line_top = 100.0 + canvas_metrics._line_h - 16.0
check("当前句译文与下一句保持 2px 间隙",
      translation_rect.bottom() <= next_line_top - 2.0,
      (translation_rect, next_line_top))
narrow_report.deleteLater()
canvas_metrics.deleteLater()

player.navigate("history")
app.processEvents()
player.playlist.refresh()
app.processEvents()

def current_playlist_rows():
    return [player.playlist.list_lay.itemAt(index).widget()
            for index in range(player.playlist.list_lay.count())
            if isinstance(player.playlist.list_lay.itemAt(index).widget(),
                          V.PlaylistRowButton)]

check("URL 输入具备无障碍名称与说明",
      player.playlist.url_input.accessibleName()
      and player.playlist.url_input.accessibleDescription(),
      (player.playlist.url_input.accessibleName(),
       player.playlist.url_input.accessibleDescription()))
playlist_tracks = [{"title": "示例曲目", "artist": "示例歌手",
                    "duration": 225.0, "source": "https://example.com/x.mp3"}]
player.playlist.set_loading()
app.processEvents()
check("歌单加载态互斥", not player.playlist.import_btn.isEnabled()
      and player.playlist.list_lay.count() > 0
      and not player.playlist.error.isVisible(), player.playlist._state)
check("加载态显示取消",
      player.playlist.cancel_btn.isVisible()
      and player.playlist.cancel_btn.isEnabled(),
      (player.playlist.cancel_btn.isVisible(),
       player.playlist.cancel_btn.isEnabled()))
player.playlist._cancelled = True
player.playlist._cancel_import()
app.processEvents()
check("取消导入立即恢复空态",
      player.playlist._state == "empty"
      and player.playlist._tracks == []
      and not player.playlist.cancel_btn.isVisible(),
      (player.playlist._state, player.playlist._tracks,
       player.playlist.cancel_btn.isVisible()))
player.playlist._on_fetch_completed(
    player.playlist._fetch_generation, playlist_tracks)
app.processEvents()
check("取消导入忽略线程结果",
      player.playlist._state == "empty"
      and player.playlist._tracks == []
      and not player.playlist.cancel_btn.isVisible(),
      (player.playlist._state, player.playlist._tracks,
       player.playlist.cancel_btn.isVisible()))
player.playlist.set_error("测试错误")
app.processEvents()
check("歌单错误态可见", player.playlist.error.isVisible()
      and player.playlist._state == "error"
      and player.playlist.url_input.property("error") == "1",
      (player.playlist._state, player.playlist.url_input.property("error")))
player.playlist.set_tracks([])
app.processEvents()
check("歌单空态可见", player.playlist._state == "empty",
      player.playlist._state)
player.playlist.set_tracks(playlist_tracks)
app.processEvents()
playlist_rows = current_playlist_rows()
check("歌单行可构造", len(playlist_rows) == 1
      and playlist_rows[0].title.text() == "示例曲目", playlist_rows)
check("本地歌词缓存行显示已就绪",
      playlist_rows[0].status.property("matched") == "1"
      and "歌词已就绪" in playlist_rows[0].status.text()
      and playlist_rows[0].status.text().startswith("✓"),
      playlist_rows[0].status.text())

check("成功态显示导入数量",
      player.playlist.success.isVisible()
      and player.playlist.success.text() == "已导入 1 首曲目",
      player.playlist.success.text())
selected_tracks = []
player.playlist.track_selected.connect(selected_tracks.append)
playlist_rows[0].click()
app.processEvents()
check("点击曲目进入歌词页",
      player.stack.currentWidget() is player.now
      and selected_tracks == playlist_tracks
      and player._playlist_track == playlist_tracks[0],
      (player.stack.currentWidget(), selected_tracks, player._playlist_track))
player.grab().save("_player_playlist_track_opened.png")
player.navigate("history")
app.processEvents()
playlist_rows = player.playlist.findChildren(V.PlaylistRowButton)
check("选中曲目状态保持", playlist_rows[0].isChecked(),
      playlist_rows[0].isChecked())
player.grab().save("_player_playlist_selected.png")

playlist_tracks = [
    playlist_tracks[0],
    {"title": "Unmatched Track", "artist": "示例歌手", "duration": 180.0,
     "source": "https://example.com/unmatched.mp3"},
    {"title": "L" * 120, "artist": "A" * 90, "duration": 96.0,
     "source": "https://example.com/long.mp3"},
]
player.playlist.set_tracks(playlist_tracks)
app.processEvents()
playlist_rows = current_playlist_rows()
playlist_rows[1].click()
app.processEvents()
check("点击后当前行保持选中",
      playlist_rows[1].isChecked()
      and player.playlist._selected_track == playlist_tracks[1],
      (playlist_rows[1].isChecked(), player.playlist._selected_track))
player.navigate("history")
app.processEvents()
playlist_rows = current_playlist_rows()
check("行选择强制单选",
      playlist_rows[1].isChecked()
      and not playlist_rows[0].isChecked()
      and not playlist_rows[2].isChecked(),
      [row.isChecked() for row in playlist_rows])
playlist_rows[1].click()
app.processEvents()
player.navigate("history")
app.processEvents()
playlist_rows = current_playlist_rows()
check("重复点击不清除选中", playlist_rows[1].isChecked(),
      [row.isChecked() for row in playlist_rows])

# ---- P1-B: _import_url 竞态守卫（两次请求，第二次先返回）----------------
race_page = V.PlaylistPage(L._tr)
race_page.url_input.setText("https://example.com/one.m3u8")
race_page._import_url()
app.processEvents()
check("P1-B 首次请求进入 loading",
      race_page._state == "loading"
      and not race_page.import_btn.isEnabled()
      and not race_page.url_input.isEnabled(),
      (race_page._state, race_page.import_btn.isEnabled(),
       race_page.url_input.isEnabled()))
first_thread = race_page._fetch_thread
first_generation = race_page._fetch_generation
# loading 中再次触发被直接忽略，不重启线程、不递增 generation。
race_page.url_input.setText("https://example.com/two.m3u8")
race_page._import_url()
app.processEvents()
check("P1-B loading 时重复触发被忽略",
      race_page._fetch_thread is first_thread
      and race_page._fetch_generation == first_generation,
      (race_page._fetch_thread is first_thread,
       race_page._fetch_generation, first_generation))
# 模拟第二次请求：直接走 generation 路径（绕过 loading 守卫）。
race_page._cancelled = False
race_page._fetch_generation += 1
second_generation = race_page._fetch_generation
race_page.set_loading()
second_tracks = [{"title": "Second", "artist": "B", "duration": 1.0,
                  "source": "https://example.com/2.mp3"}]
race_page._on_fetch_completed(second_generation, second_tracks)
app.processEvents()
check("P1-B 第二次结果先回写",
      race_page._state == "tracks"
      and race_page._tracks == second_tracks,
      (race_page._state, race_page._tracks))
# 第一次旧线程迟到，必须被 generation 守卫丢弃。
stale_tracks = [{"title": "Stale", "artist": "A", "duration": 1.0,
                 "source": "https://example.com/1.mp3"}]
race_page._on_fetch_completed(first_generation, stale_tracks)
app.processEvents()
check("P1-B 迟到旧结果被忽略",
      race_page._state == "tracks"
      and race_page._tracks == second_tracks,
      (race_page._state, race_page._tracks))
# 取消后再到的旧结果也必须忽略。
race_page.url_input.setText("https://example.com/three.m3u8")
race_page._import_url()
app.processEvents()
third_generation = race_page._fetch_generation
race_page._cancel_import()
app.processEvents()
check("P1-B 取消后回到空态",
      race_page._state == "empty" and race_page._tracks == [],
      (race_page._state, race_page._tracks))
race_page._on_fetch_completed(third_generation, second_tracks)
app.processEvents()
check("P1-B 取消后迟到结果被忽略",
      race_page._state == "empty" and race_page._tracks == [],
      (race_page._state, race_page._tracks))
race_page.deleteLater()

check("超长元数据保留全文并提示",
      playlist_rows[2].title.toolTip() == playlist_tracks[2]["title"]
      and playlist_rows[2].artist.toolTip() == playlist_tracks[2]["artist"]
      and playlist_tracks[2]["title"] in playlist_rows[2].accessibleName()
      and playlist_tracks[2]["artist"] in playlist_rows[2].accessibleName(),
      (playlist_rows[2].title.toolTip(),
       playlist_rows[2].accessibleName()))
playlist_rows[2].setFocus()
app.processEvents()
QTest.keyClick(playlist_rows[2], Qt.Key_Return)
app.processEvents()
check("回车激活歌单行",
      player.stack.currentWidget() is player.now
      and playlist_rows[2].isChecked()
      and selected_tracks[-1] == playlist_tracks[2],
      (player.stack.currentWidget(), [row.isChecked() for row in playlist_rows],
       selected_tracks[-1]))
check("未匹配曲目进入明确空态",
      player.now.canvas.empty_message_key == "未找到本地歌词"
      and player.now.canvas.empty_description_key == "请添加本地歌词文件后再试。",
      (player.now.canvas.empty_message_key,
       player.now.canvas.empty_description_key))
playlist_rows[0].click()
app.processEvents()
player.navigate("history")
app.processEvents()
playlist_rows = current_playlist_rows()
check("切换行后旧行取消选中",
      playlist_rows[0].isChecked() and not playlist_rows[1].isChecked()
      and not playlist_rows[2].isChecked(),
      [row.isChecked() for row in playlist_rows])
check("歌单页入口可用", player.stack.currentWidget() is player.playlist
      or player.stack.currentWidget() is player.now)

player.navigate("settings")
check("设置入口可用", player.stack.currentWidget() is player.settings_page,
      type(player.stack.currentWidget()).__name__)

player.navigate("now")
player.toggle_immersive()
app.processEvents()
check("进入沉浸模式", player._immersive and not player.sidebar.isVisible(),
      player._immersive)
player.toggle_immersive()
app.processEvents()
check("退出沉浸模式", not player._immersive and player.sidebar.isVisible(),
      player._immersive)

# ---- Language switch refreshes brand / immersive / stage eyebrow -----------
def _has_cjk(text):
    for ch in text or "":
        code = ord(ch)
        if 0x2E80 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF:
            return True
    return False


ov.main_player = player
ov.set_ui_lang("zh-CN")
app.processEvents()
ov.set_ui_lang("en")
app.processEvents()
check("set_ui_lang 联动刷新播放器",
      "Desktop-sing" in player.windowTitle()
      and not _has_cjk(player.windowTitle())
      and player.sidebar.brand_name.text() == "Desktop-sing"
      and player.now.immersive_btn.text() == "Immersive lyrics"
      and player.now.source.text() == "Now playing",
      (player.windowTitle(), player.sidebar.brand_name.text(),
       player.now.immersive_btn.text(), player.now.source.text()))

L.set_ui_lang("en")
player.retranslate_ui()
app.processEvents()
check("切 en 后窗口标题无中文",
      "Desktop-sing" in player.windowTitle()
      and not _has_cjk(player.windowTitle()), player.windowTitle())
check("切 en 后侧栏品牌", player.sidebar.brand_name.text() == "Desktop-sing",
      player.sidebar.brand_name.text())
check("切 en 后沉浸按钮", player.now.immersive_btn.text() == "Immersive lyrics",
      player.now.immersive_btn.text())
check("切 en 后舞台 eyebrow", player.now.source.text() == "Now playing",
      player.now.source.text())
check("切 en 后最小化/最大化提示",
      player.titlebar.b_min.toolTip() == "Minimize"
      and player.titlebar.b_max.toolTip() == "Maximize"
      and player.titlebar.b_min.accessibleName() == "Minimize"
      and player.titlebar.b_max.accessibleName() == "Maximize",
      (player.titlebar.b_min.toolTip(), player.titlebar.b_max.toolTip()))
L.set_ui_lang("ja")
player.retranslate_ui()
app.processEvents()
check("切 ja 后沉浸按钮", player.now.immersive_btn.text() == "没入歌詞",
      player.now.immersive_btn.text())
check("切 ja 后舞台 eyebrow", player.now.source.text() == "再生中",
      player.now.source.text())
check("切 ja 后最小化/最大化提示",
      player.titlebar.b_min.toolTip() == "最小化"
      and player.titlebar.b_max.toolTip() == "最大化",
      (player.titlebar.b_min.toolTip(), player.titlebar.b_max.toolTip()))
player.now.update_track({"title": "夜航西飞", "artist": "示例歌手",
                         "duration": 240.0}, None)
L.set_ui_lang("en")
player.retranslate_ui()
app.processEvents()
check("有曲目时切语言不覆盖歌名",
      player.now.title.text() == "夜航西飞"
      and player.now.track_title.text() == "夜航西飞",
      (player.now.title.text(), player.now.track_title.text()))
L.set_ui_lang("zh-CN")
player.retranslate_ui()
app.processEvents()

# ---- English plural forms and playlist success message ----------------------
L.set_ui_lang("en")
report = V.ReportPage(L._tr)
report.set_stats({"total_seconds": 61, "month_tracks": 1,
                  "streak": 1, "active_days": 1})
check("en 单数: 1 track / 1 day / 1 day",
      (report.track_count.text(), report.streak.value.text(),
       report.active.value.text()) == ("1 track", "1 day", "1 day"),
      (report.track_count.text(), report.streak.value.text(),
       report.active.value.text()))
report.set_stats({"total_seconds": 61, "month_tracks": 3,
                  "streak": 2, "active_days": 4})
check("en 复数: 3 tracks / 2 days / 4 days",
      (report.track_count.text(), report.streak.value.text(),
       report.active.value.text()) == ("3 tracks", "2 days", "4 days"),
      (report.track_count.text(), report.streak.value.text(),
       report.active.value.text()))
report.deleteLater()
row_single = V.HistoryRow({"title": "One", "artist": "A", "plays": 1}, L._tr)
row_many = V.HistoryRow({"title": "Two", "artist": "B", "plays": 3}, L._tr)
check("en 单数: 1 play", row_single.plays.text() == "1 play",
      row_single.plays.text())
check("en 复数: 3 plays", row_many.plays.text() == "3 plays",
      row_many.plays.text())
row_single.deleteLater()
row_many.deleteLater()

playlist_preview = V.PlaylistPage(L._tr)
playlist_preview.set_tracks([
    {"title": "One", "artist": "A", "duration": 90.0, "source": "local"}])
check("en 成功态单数", playlist_preview.success.text() == "Imported 1 track",
      playlist_preview.success.text())
playlist_preview.set_tracks([
    {"title": "One", "artist": "A", "duration": 90.0, "source": "local"},
    {"title": "Two", "artist": "B", "duration": 90.0, "source": "local"},
    {"title": "Three", "artist": "C", "duration": 90.0, "source": "local"}])
check("en 成功态复数", playlist_preview.success.text() == "Imported 3 tracks",
      playlist_preview.success.text())
playlist_preview.deleteLater()
app.processEvents()
L.set_ui_lang("zh-CN")

player.enter_mini()
app.processEvents()
check("切换到迷你模式会隐藏主窗口", not player.isVisible())

# ---- Settings persistence -------------------------------------------------
panel = L.SettingsPanel(ov)
panel._on_listen_stats(False)
with open(L.CONFIG_PATH, encoding="utf-8") as f:
    saved = json.load(f)
check("关闭听歌统计会持久化", saved.get("listen_stats") is False,
      saved.get("listen_stats"))
panel._on_listen_stats(True)
with open(L.CONFIG_PATH, encoding="utf-8") as f:
    saved = json.load(f)
check("重新开启听歌统计会持久化", saved.get("listen_stats") is True,
      saved.get("listen_stats"))

player._timer.stop()
player.hide()
player.deleteLater()
panel.hide()
panel.deleteLater()
try:
    ov.hotkeys.unregister()
except Exception:
    pass
app.processEvents()

print("\nRESULT", "PASS" if not FAILS else "FAIL (%d)" % len(FAILS))
if FAILS:
    print("Failed:", ", ".join(FAILS))
sys.exit(0 if not FAILS else 1)
