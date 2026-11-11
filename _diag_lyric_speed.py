# -*- coding: utf-8 -*-
"""歌词源速度基准：网易云 / QQ / 酷狗 / lrclib，搜索+取词耗时与成功率。"""
import base64
import json
import re
import socket
import statistics
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

SONGS = [("晴天", "周杰伦"), ("Welcome to Wonderland", "Anson Seabra")]
SAMPLES = 3


def http(url, data=None, headers=None, timeout=8):
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": UA, **(headers or {})})
    t0 = time.time()
    with DIRECT.open(req, timeout=timeout) as resp:
        body = resp.read()
    return body, time.time() - t0


# ---------------- 网易云 ----------------
def netease(query):
    body = urllib.parse.urlencode(
        {"s": query, "type": 1, "offset": 0, "limit": 10, "total": "true"}).encode()
    raw, t = http("https://music.163.com/api/search/get/web", body,
                  {"Referer": "https://music.163.com/",
                   "Content-Type": "application/x-www-form-urlencoded",
                   "Cookie": "os=pc; appver=2.9.7"})
    songs = (json.loads(raw.decode("utf-8", "ignore")).get("result") or {}).get("songs") or []
    if not songs:
        return t, 0.0, 0
    sid = songs[0].get("id")
    raw2, t2 = http("https://music.163.com/api/song/lyric?id=%s&lv=1&kv=1&tv=-1" % sid,
                    headers={"Referer": "https://music.163.com/"})
    d = json.loads(raw2.decode("utf-8", "ignore"))
    lrc = (d.get("lrc") or {}).get("lyric") or ""
    return t, t2, lrc.count("\n")


# ---------------- QQ ----------------
def qq(query):
    payload = json.dumps({"req": {
        "method": "DoSearchForQQMusicDesktop",
        "module": "music.search.SearchCgiService",
        "param": {"search_type": 0, "query": query, "page_num": 1, "num_per_page": 10},
    }}).encode()
    raw, t = http("https://u.y.qq.com/cgi-bin/musicu.fcg", payload,
                  {"Referer": "https://y.qq.com/", "Content-Type": "application/json"})
    body = ((json.loads(raw.decode("utf-8", "ignore")).get("req") or {})
            .get("data") or {}).get("body") or {}
    songs = ((body.get("song") or {}).get("list") or [])
    if not songs:
        return t, 0.0, 0
    mid = songs[0].get("mid")
    url = ("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?"
           "pcachetime=%d&songmid=%s&g_tk=5381&loginUin=0&hostUin=0&format=json"
           "&inCharset=utf8&outCharset=utf-8&notice=0&platform=yqq.json&needNewCode=0"
           % (int(time.time() * 1000), urllib.parse.quote(mid or "")))
    raw2, t2 = http(url, headers={"Referer": "https://y.qq.com/"})
    text = raw2.decode("utf-8", "ignore")
    m = re.match(r"^\w+\((.*)\)\s*$", text, re.S)
    if m:
        text = m.group(1)
    d = json.loads(text)
    enc = d.get("lyric") or ""
    lrc = base64.b64decode(enc).decode("utf-8", "ignore") if enc else ""
    return t, t2, lrc.count("\n")


# ---------------- 酷狗 ----------------
def kugou(query):
    url = ("http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword=%s"
           "&page=1&pagesize=10&showtype=1" % urllib.parse.quote(query))
    raw, t = http(url)
    info = ((json.loads(raw.decode("utf-8", "ignore")).get("data") or {}).get("info") or [])
    if not info:
        return t, 0.0, 0
    it = info[0]
    lurl = ("https://lyrics.kugou.com/search?ver=1&man=yes&client=pc&keyword=%s"
            "&duration=%s&hash=%s" % (urllib.parse.quote(it.get("songname") or ""),
                                      it.get("duration") or 0, it.get("hash") or ""))
    raw2, t2 = http(lurl)
    cands = json.loads(raw2.decode("utf-8", "ignore")).get("candidates") or []
    if not cands:
        return t, t2, 0
    c = cands[0]
    raw3, t3 = http("https://lyrics.kugou.com/download?ver=1&client=pc&id=%s"
                    "&accesskey=%s&fmt=krc&charset=utf8" % (c.get("id"), c.get("accesskey")))
    content = json.loads(raw3.decode("utf-8", "ignore")).get("content") or ""
    return t, t2 + t3, (1 if content else 0)


# ---------------- lrclib（直连 + 逐 IP） ----------------
def lrclib(query):
    url = ("https://lrclib.net/api/search?track_name=%s&artist_name=%s"
           % (urllib.parse.quote(query.split(" ")[0]),
              urllib.parse.quote(query.rsplit(" ", 1)[-1])))
    try:
        raw, t = http(url, timeout=8)
        items = json.loads(raw.decode("utf-8", "ignore"))
        synced = [x for x in (items or []) if x.get("syncedLyrics")]
        return t, 0.0, len(synced)
    except Exception:
        # 逐 IP 兜底
        import ssl
        host = "lrclib.net"
        ips = []
        for _a, _t, _p, _c, sa in socket.getaddrinfo(host, 443, socket.AF_INET):
            if sa[0] not in ips:
                ips.append(sa[0])
        t0 = time.time()
        for ip in ips:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(6)
                s.connect((ip, 443))
                ws = ssl.create_default_context().wrap_socket(s, server_hostname=host)
                ws.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\n"
                            "Connection: close\r\n\r\n"
                            % (url.split(host, 1)[1], host, UA)).encode())
                buf = b""
                ws.settimeout(6)
                while True:
                    c = ws.recv(16384)
                    if not c:
                        break
                    buf += c
                ws.close()
                return time.time() - t0, 0.0, 1
            except Exception:
                continue
        return time.time() - t0, 0.0, 0


SOURCES = [("netease", netease), ("qq", qq), ("kugou", kugou), ("lrclib", lrclib)]

for title, artist in SONGS:
    query = "%s %s" % (title, artist)
    print("=" * 66)
    print("歌：《%s》 - %s    采样 %d 次" % (title, artist, SAMPLES))
    print("%-9s %10s %10s %10s %8s" % ("源", "搜索(中位)", "取词(中位)", "总耗时", "命中"))
    rows = []
    for sname, fn in SOURCES:
        st, lt, lines = [], [], []
        ok = 0
        for _ in range(SAMPLES):
            try:
                a, b, n = fn(query)
                st.append(a)
                lt.append(b)
                lines.append(n)
                if n:
                    ok += 1
            except Exception as e:
                st.append(99)
                lt.append(99)
                lines.append(0)
        med_s = statistics.median(st) if st else 0
        med_l = statistics.median(lt) if lt else 0
        total = med_s + med_l
        rows.append((total, sname, med_s, med_l, ok))
        print("%-9s %9.2fs %9.2fs %9.2fs %5d/%d" %
              (sname, med_s, med_l, total, ok, SAMPLES))
    rows.sort()
    print("→ 最快: %s (%.2fs)" % (rows[0][1], rows[0][0]))
    print()
