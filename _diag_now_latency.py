# -*- coding: utf-8 -*-
"""诊断 17:23 '预算内无一响应'：实测各源当前延迟，直连 vs 系统代理对比"""
import json, socket, ssl, time, urllib.request, urllib.parse, urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
RESULTS = []

def timed(label, fn):
    t0 = time.time()
    try:
        r = fn()
        dt = time.time() - t0
        RESULTS.append((label, dt, "OK" if r else "EMPTY"))
    except Exception as e:
        dt = time.time() - t0
        RESULTS.append((label, dt, "ERR " + type(e).__name__ + ": " + str(e)[:80]))

def netease_plain(direct):
    # 直连：绕过代理 handler
    if direct:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()  # 默认吃系统代理
    data = urllib.parse.urlencode({
        "s": "Welcome to Wonderland Anson Seabra", "limit": 5, "type": 1, "offset": 0,
    }).encode()
    req = urllib.request.Request(
        "http://music.163.com/api/search/get/web", data=data,
        headers={"User-Agent": UA, "Referer": "http://music.163.com"})
    with opener.open(req, timeout=4.0) as resp:
        j = json.loads(resp.read().decode("utf-8", "replace"))
        return bool(j.get("result", {}).get("songs"))

def netease_direct_ip():
    # 强制解析 IP 直连，绕过 DNS 与代理
    ips = socket.getaddrinfo("music.163.com", 80, socket.AF_INET)
    ip = ips[0][4][0]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = urllib.parse.urlencode({
        "s": "Welcome to Wonderland Anson Seabra", "limit": 5, "type": 1, "offset": 0,
    }).encode()
    req = urllib.request.Request(
        "http://" + ip + "/api/search/get/web", data=data,
        headers={"User-Agent": UA, "Referer": "http://music.163.com", "Host": "music.163.com"})
    with opener.open(req, timeout=4.0) as resp:
        j = json.loads(resp.read().decode("utf-8", "replace"))
        return bool(j.get("result", {}).get("songs"))

def kugou(direct):
    if direct:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()
    kw = urllib.parse.urlencode({"keyword": "Welcome to Wonderland Anson Seabra"})
    req = urllib.request.Request(
        "http://mobilecdn.kugou.com/api/v3/search/song?" + kw,
        headers={"User-Agent": UA})
    with opener.open(req, timeout=4.0) as resp:
        j = json.loads(resp.read().decode("utf-8", "replace"))
        return bool(j.get("data", {}).get("info"))

def qq(direct):
    if direct:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()
    body = json.dumps({
        "req": {"method": "DoSearchForQQMusicDesktop",
                "module": "music.search.SearchCgiService",
                "param": {"search_type": 0, "query": "Welcome to Wonderland Anson Seabra",
                          "page_num": 1, "num_per_page": 5}}
    }).encode()
    req = urllib.request.Request(
        "https://u.y.qq.com/cgi-bin/musicu.fcg", data=body,
        headers={"User-Agent": UA, "Content-Type": "application/json"})
    with opener.open(req, timeout=4.0) as resp:
        j = json.loads(resp.read().decode("utf-8", "replace"))
        return bool(j.get("req", {}).get("data", {}).get("body", {}).get("song", {}).get("list"))

def lrclib():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    q = urllib.parse.urlencode({"track_name": "Welcome to Wonderland",
                                "artist_name": "Anson Seabra"})
    req = urllib.request.Request("https://lrclib.net/api/search?" + q,
                                 headers={"User-Agent": "Desktop-sing/2.0.2"})
    with opener.open(req, timeout=8.0) as resp:
        arr = json.loads(resp.read().decode("utf-8", "replace"))
        return len(arr)

print("=== 系统代理:", urllib.request.getproxies(), flush=True)
timed("netease 直连   ", lambda: netease_plain(True))
timed("netease 走代理 ", lambda: netease_plain(False))
timed("netease IP直连 ", netease_direct_ip)
timed("kugou  直连    ", lambda: kugou(True))
timed("kugou  走代理  ", lambda: kugou(False))
timed("qq     直连    ", lambda: qq(True))
timed("qq     走代理  ", lambda: qq(False))
timed("lrclib 直连    ", lrclib)

print()
for label, dt, st in RESULTS:
    print("%s %6.2fs  %s" % (label, dt, st), flush=True)
