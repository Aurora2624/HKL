import requests, re, json, zlib, struct, time, html

SITE = "https://www.cd-zj.com"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
HDRS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9", "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none", "Upgrade-Insecure-Requests": "1"}
COOKIE = "verify_success=1; mac_verify=839bf1a7d1ecf39a17c3e6b8f394e919; verify_back_url=%2Ftype%2F2.html; PHPSESSID=5cs6hugfe0mrge0fecdeps7kq0;"

CATS_FULL = [
    ("13", "国产剧"), ("15", "日韩剧"), ("16", "海外剧"),
    ("6", "动作片"), ("7", "喜剧片"), ("8", "恐怖片"), ("9", "科幻片"),
    ("10", "爱情片"), ("11", "剧情片"), ("12", "战争片"), ("20", "纪录片"),
    ("25", "国产动漫"), ("26", "日韩动漫"), ("21", "大陆综艺"), ("22", "日韩综艺"),
]
CATS_LABEL = [
    ("qq", "腾讯SVIP精选"), ("bli", "B站SVIP精选"), ("youku", "优酷SVIP精选"),
    ("rss", "最近更新"),
]

TPL = {
    0: ["...##.....####...##..##.##....####....####....####....##.##..##...####.....##..."],
    1: ["...###....####..######.....###.....###.....###.....###.....###.....###..########"],
    2: ["..####...##..##.##....##......##.....##.....##.....##.....##.....##.....########"],
    4: [".....##.....###....####...##.##..##..##.##...##.########.....##......##......##."],
    5: ["..####...##..##.##....####....##.##..###..###.##......##.#....##.##..##...####.."],
    6: [".#####..##...##.......##.....##....###.......##.......##......####...##..#####.."],
    7: ["########......##......##.....##.....##.....##.....##.....##.....##......##......"],
    8: ["..####...##..##.##....##.##..##...####...##..##.##....####....##.##..##...####.."],
    9: ["#######.##......##......##.###..###..##.......##......####....##.##..##...####.."],
}

def _decode_png(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not png')
    pos, width, height, idat = 8, None, None, b''
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos+4])[0]
        typ = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+ln]
        pos += 12 + ln
        if typ == b'IHDR':
            width, height, bit_depth, color_type = struct.unpack('>IIBB', chunk[:10])
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
    if color_type not in (0, 2, 3, 4, 6):
        raise ValueError('color type')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bpp = channels
    stride = width * channels
    raw = zlib.decompress(idat)
    prev = bytearray(stride)
    gray, p = [], 0
    for y in range(height):
        ft = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i-bpp]) & 0xff
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xff
        elif ft == 3:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xff
        elif ft == 4:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i-bpp] if i >= bpp else 0
                pp = a + b - c
                pa, pb, pc = abs(pp-a), abs(pp-b), abs(pp-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xff
        elif ft != 0:
            raise ValueError('filter')
        if color_type == 2:
            rows = [int(line[x*3]*0.299 + line[x*3+1]*0.587 + line[x*3+2]*0.114) for x in range(width)]
        elif color_type == 6:
            rows = [int(line[x*4]*0.299 + line[x*4+1]*0.587 + line[x*4+2]*0.114) for x in range(width)]
        elif color_type == 4:
            rows = [line[x*2] for x in range(width)]
        else:
            rows = list(line[:width])
        gray.append(rows)
        prev = line
    return width, height, gray

def _recognize_captcha(data):
    try:
        W, H, gray = _decode_png(data)
    except Exception:
        return None
    bw = [[1 if gray[y][x] < 128 else 0 for x in range(W)] for y in range(H)]
    cols = [any(bw[y][x] for y in range(H)) for x in range(W)]
    segs, inseg = [], False
    for x in range(W):
        if cols[x] and not inseg:
            start = x; inseg = True
        elif not cols[x] and inseg:
            segs.append((start, x-1)); inseg = False
    if inseg:
        segs.append((start, W-1))
    if len(segs) != 4:
        return None
    result = ''
    for s, e in segs:
        rows = [y for y in range(H) if any(bw[y][x] for x in range(s, e+1))]
        if not rows:
            return None
        top, bot = rows[0], rows[-1]
        ch = [bw[y][s:e+1] for y in range(top, bot+1)]
        h = len(ch); w = len(ch[0])
        norm = [[0]*8 for _ in range(10)]
        for ty in range(10):
            sy = min(h-1, int(ty*h/10))
            for tx in range(8):
                sx = min(w-1, int(tx*w/8))
                norm[ty][tx] = ch[sy][sx]
        flat = ''.join(''.join('#' if v else '.' for v in row) for row in norm)
        best_d, best_score = None, 10**9
        for d, variants in TPL.items():
            for v in variants:
                score = sum(1 for i in range(80) if (flat[i] == '#') != (v[i] == '#'))
                if score < best_score:
                    best_score, best_d = score, d
        if best_score > 12:
            return None
        result += str(best_d)
    return result

def _verify_once(sess):
    """单次验证码尝试（低频）。返回True=通过"""
    try:
        cap = sess.get(SITE + "/captcha.php?type=code&r=0.12345", headers={"User-Agent": UA,
                    "Referer": SITE + "/cupfox-list/2-----------.html"}, timeout=20).content
        code = _recognize_captcha(cap)
        if not code:
            return False
        resp = sess.post(SITE + "/captcha.php?type=verify", data={"check": code},
                         headers={"User-Agent": UA, "Referer": SITE + "/cupfox-list/2-----------.html",
                                  "Content-Type": "application/x-www-form-urlencoded"}, timeout=20)
        return '"code":1' in resp.text
    except Exception:
        return False

def _auto_verify(sess):
    """自动过验证码：预热 session + 最多4次尝试（间隔3秒防限流）。
    成功返回 True；失败返回 False（多为 IP 被限流，等 5-10 分钟或换网后重试）"""
    try:
        r = sess.get(SITE + "/cupfox-list/2-----------.html", headers=HDRS, timeout=20)
    except Exception:
        return False
    if "系统安全验证" not in r.text:
        return True
    if not sess.cookies.get("PHPSESSID"):
        try:
            sess.post(SITE + "/captcha.php?type=verify", data={"check": ""},
                      headers={"User-Agent": UA, "Referer": SITE + "/cupfox-list/2-----------.html",
                               "Content-Type": "application/x-www-form-urlencoded"}, timeout=20)
        except Exception:
            pass
    for i in range(4):
        if _verify_once(sess):
            time.sleep(2)
            try:
                r2 = sess.get(SITE + "/cupfox-list/2-----------.html", headers=HDRS, timeout=20)
                if "系统安全验证" not in r2.text:
                    return True
            except Exception:
                return True
        time.sleep(3)
    return False

PLAYER_MAP = None
_DEFAULT_SERVERS = {
    "co": "https://zsmyyrv.hzqingshan.com", "BBA": "https://zsmyyrv.hzqingshan.com",
    "vwnet": "https://zsmyyrv.hzqingshan.com", "YYNB": "https://zsmyyrv.hzqingshan.com",
    "JD4K": "https://fgsrg.hzqingshan.com", "JD2K": "https://fgsrg.hzqingshan.com",
    "qiyi": "https://zzrs.mfdyvip.com", "bilibili": "https://zzrs.mfdyvip.com",
    "qq": "https://zzrs.mfdyvip.com", "youku": "https://zzrs.mfdyvip.com",
}
def _player_servers(sess):
    global PLAYER_MAP
    if PLAYER_MAP is not None:
        return PLAYER_MAP
    m = dict(_DEFAULT_SERVERS)
    for _ in range(3):
        try:
            js = sess.get(SITE + "/static/js/playerconfig.js?t=20260813",
                          headers={"User-Agent": UA, "Referer": SITE + "/"}, timeout=20).text
            pm = re.search(r'player_list=(\{.*\})', js)
            if pm:
                for k, v in re.findall(r'"(\w+)":\{"show":"[^"]*","des":"[^"]*","ps":"(\d)","parse":"([^"]*)"', pm.group(1)):
                    if v == "1" and k != "parse":
                        m[k] = re.sub(r'/player/\?url=$', '', re.sub(r'/$', '', v.replace('\\/', '/')))
                break
        except Exception:
            pass
    PLAYER_MAP = m
    return m

def _resolve_play(sess, pid, sid, nid):
    r = sess.get(f"{SITE}/play/{pid}-{sid}-{nid}.html", headers=HDRS, timeout=20)
    m = re.search(r'player_\w+\s*=\s*(\{.*?\})\s*;?\s*$', r.text, re.S)
    if not m:
        m = re.search(r'player_\w+\s*=\s*(\{.*?\})</script>', r.text, re.S)
    if not m:
        m = re.search(r'player_\w+\s*=\s*(\{.*?\})', r.text, re.S)
    if not m:
        return None
    try:
        pd = json.loads(m.group(1))
    except Exception:
        return None
    url = pd.get("url", "")
    if not url:
        return None
    if re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I):
        return url
    servers = _player_servers(sess)
    fr = pd.get("from", "")
    base = servers.get(fr, "https://fgsrg.hzqingshan.com")
    try:
        pg = sess.get(base + "/player/?url=" + requests.utils.quote(url, safe=''),
                      headers={"User-Agent": UA, "Referer": SITE + "/"}, timeout=20).text
        token = re.search(r'data-te="([^"]*)"', pg)
        if not token:
            return None
        resp = sess.post(base + "/player/mplayer.php",
                         data={"url": url, "token": token.group(1)},
                         headers={"User-Agent": UA, "Referer": SITE + "/",
                                  "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                                  "X-Requested-With": "XMLHttpRequest"}, timeout=20)
        j = json.loads(resp.text)
        if j.get("code") == 200 and j.get("url"):
            return j["url"]
    except Exception:
        pass
    return None

def _parse_list_html(t):
    vods, seen = [], set()
    for m in re.finditer(r'<a[^>]*href="/detail/(\d+)\.html"[^>]*title="([^"]+)"[^>]*>(?:(?!</a>).)*?<img[^>]*(?:data-src|src)="([^"]+)"', t, re.S):
        vid, name, pic = m.group(1), m.group(2), m.group(3)
        if vid in seen:
            continue
        seen.add(vid)
        vods.append({"vod_id": vid, "vod_name": name, "vod_pic": html.unescape(pic)})
    for m in re.finditer(r'<a[^>]*href="/detail/(\d+)\.html"[^>]*>(?:(?!</a>).)*?<img[^>]*alt="([^"]+)"[^>]*(?:data-src|src)="([^"]+)"', t, re.S):
        vid, name, pic = m.group(1), m.group(2), m.group(3)
        if vid in seen:
            continue
        seen.add(vid)
        vods.append({"vod_id": vid, "vod_name": name, "vod_pic": html.unescape(pic)})
    return vods

RSS_CACHE = {"t": 0, "items": []}

def _rss_items(sess):
    now = time.time()
    if now - RSS_CACHE["t"] < 600 and RSS_CACHE["items"]:
        return RSS_CACHE["items"]
    items = []
    try:
        r = sess.get(SITE + "/rss/baidu.xml", headers=HDRS, timeout=20)
        items = [(m.group(1), m.group(2)) for m in
                 re.finditer(r'<loc>https://www\.cd-zj\.com/detail/(\d+)\.html</loc><lastmod>([^<]+)</lastmod>', r.text)]
    except Exception:
        pass
    RSS_CACHE["t"] = now
    RSS_CACHE["items"] = items
    return items

class Spider:
    def getName(self):
        return "枫叶4K影院"
    def getDependence(self):
        return []

    def init(self, extend):
        self.sess = requests.Session()
        self.sess.headers.update(HDRS)
        self.cookie_ok = False
        ck = ""
        if isinstance(extend, dict):
            ck = extend.get("cookie", "") or ""
        if not ck:
            ck = COOKIE
        if ck:
            try:
                self.sess.headers["Cookie"] = ck
                r = self.sess.get(SITE + "/cupfox-list/2-----------.html", headers=HDRS, timeout=20)
                self.cookie_ok = "系统安全验证" not in r.text
                if not self.cookie_ok:
                    self.sess.headers.pop("Cookie", None)
            except Exception:
                self.sess.headers.pop("Cookie", None)
        if not self.cookie_ok:
            self.cookie_ok = _auto_verify(self.sess)
        self._vstate = None

    def homeContent(self, filter):
        cats = [{"type_id": t, "type_name": n} for t, n in (CATS_FULL if self.cookie_ok else CATS_LABEL)]
        vods = []
        try:
            r = self.sess.get(SITE + "/", headers=HDRS, timeout=20)
            vods = _parse_list_html(r.text)[:20]
        except Exception:
            pass
        return {"class": cats, "filters": {}, "list": vods}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        if self.cookie_ok and str(tid).isdigit():
            url = f"{SITE}/cupfox-list/{tid}--------{page}---2.html"
            try:
                r = self.sess.get(url, headers=HDRS, timeout=20)
                if "系统安全验证" not in r.text:
                    vods = _parse_list_html(r.text)
                    total = re.search(r'当前\d+/(\d+)页', r.text)
                    totalpg = int(total.group(1)) if total else 1
                    return {"list": vods, "page": page, "pagecount": totalpg, "limit": 30, "total": totalpg * 30}
            except Exception:
                pass
            if _auto_verify(self.sess):
                self.cookie_ok = True
                try:
                    r = self.sess.get(url, headers=HDRS, timeout=20)
                    if "系统安全验证" not in r.text:
                        vods = _parse_list_html(r.text)
                        total = re.search(r'当前\d+/(\d+)页', r.text)
                        totalpg = int(total.group(1)) if total else 1
                        return {"list": vods, "page": page, "pagecount": totalpg, "limit": 30, "total": totalpg * 30}
                except Exception:
                    pass
            self.cookie_ok = False
        if tid == "rss":
            items = _rss_items(self.sess)
            totalpg = max(1, (len(items) + 39) // 40)
            page = min(page, totalpg)
            chunk = items[(page-1)*40: page*40]
            vods = [{"vod_id": vid, "vod_name": f"更新于 {d}", "vod_pic": ""} for vid, d in chunk]
            return {"list": vods, "page": page, "pagecount": totalpg, "limit": 40, "total": len(items)}
        url = f"{SITE}/label/{tid}/page/{page}.html"
        try:
            r = self.sess.get(url, headers=HDRS, timeout=20)
            vods = _parse_list_html(r.text)
        except Exception:
            vods = []
        total = 11 if re.search(r'/label/{}/page/\d+\.html'.format(tid), r.text) else 1
        return {"list": vods, "page": page, "pagecount": total, "limit": 30, "total": total * 30}

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0])
        else:
            vid = str(ids)
        vid = re.sub(r'\D', '', vid)
        if not vid:
            return {"list": []}
        r = self.sess.get(f"{SITE}/detail/{vid}.html", headers=HDRS, timeout=20)
        t = r.text
        name = re.search(r'<h1[^>]*>([^<]+)</h1>', t)
        name = name.group(1).strip() if name else ""
        if not name:
            name = re.search(r'<title>《([^》]+)》', t)
            name = name.group(1) if name else vid
        pic = ""
        m = re.search(r'class="slide-time-img2"[^>]*>\s*<img[^>]*src="([^"]+)"', t)
        if m:
            pic = html.unescape(m.group(1))
        actor = re.search(r'主演[：:]\s*</strong>\s*([^<]+)', t)
        actor = actor.group(1).strip() if actor else ""
        director = re.search(r'导演[：:]\s*</strong>\s*([^<]+)', t)
        director = director.group(1).strip() if director else ""
        year = ""
        m = re.search(r'年份[：:]\s*</strong>\s*([^<]+)', t)
        if m:
            year = m.group(1).strip()
        remark = re.search(r'连载\s*[：:]\s*</strong>\s*([^<]+)', t)
        remark = remark.group(1).strip() if remark else ""
        desc = re.search(r'简介[：:]?\s*([^<]{10,400})', t)
        desc = desc.group(1).strip() if desc else ""
        seg = t
        mseg = re.search(r'>(?:&nbsp;)?播放线路<', t)
        if mseg:
            seg = t[mseg.end():]
            mseg2 = re.search(r'(影片简评|追剧推荐|最新更新|热门推荐|copyright)', seg, re.I)
            if mseg2:
                seg = seg[:mseg2.start()]
        tabs = re.findall(r'<a class="swiper-slide"[^>]*aria-label="(\d+)[^"]*"[^>]*>(?:<i[^>]*></i>)?&nbsp;([^<]+)', seg)
        boxes = re.findall(r'<ul class="anthology-list-play[^"]*"[^>]*>(.*?)</ul>', seg, re.S)
        sources = []
        used_names = {}
        for i, sid in enumerate([x[0] for x in tabs]):
            if i >= len(boxes):
                break
            sname = tabs[i][1].strip()
            base = sname
            n = used_names.get(base, 0)
            used_names[base] = n + 1
            if n > 0:
                sname = f"{base}{n+1}"
            eps = re.findall(r'href="/play/\d+-(\d+)-(\d+)\.html"[^>]*>([^<]+)</a>', boxes[i])
            items = []
            for esid, enid, label in eps:
                if esid != sid:
                    continue
                num = re.sub(r'\D', '', label) or enid
                items.append(f"{num}${vid}-{sid}-{enid}")
            if items:
                items.reverse()
                sources.append({"source_name": sname, "source_url": "#".join(items), "sid": sid})
        PRIO = {"自营t": 0, "自营y": 1, "自营r": 2, "至臻4k": 3, "蓝光2k": 5, "蓝光2k2": 4}
        sources.sort(key=lambda s: PRIO.get(s.get("source_name", ""), 9))
        if not sources:
            eps = re.findall(r'href="/play/(\d+)-(\d+)-(\d+)\.html"[^>]*>([^<]+)</a>', t)
            if eps:
                items = [f"{l.strip()}${pid}-{sid}-{nid}" for pid, sid, nid, l in eps]
                items.reverse()
                sources.append({"source_name": "线路1", "source_url": "#".join(items)})
        return {"list": [{"vod_id": vid, "vod_name": name, "vod_pic": pic, "type_name": "",
                          "vod_year": year, "vod_area": "", "vod_remarks": remark,
                          "vod_actor": actor, "vod_director": director, "vod_content": desc,
                          "vod_play_from": "$$$".join(s["source_name"] for s in sources),
                          "vod_play_url": "$$$".join(s["source_url"] for s in sources)}]}

    def searchContent(self, key, quick):
        if self._vstate is None:
            try:
                r = self.sess.get(SITE + "/cupfox-list/2-----------.html", headers=HDRS, timeout=20)
                if "系统安全验证" in r.text:
                    if not self.sess.cookies.get("PHPSESSID"):
                        self.sess.post(SITE + "/captcha.php?type=verify", data={"check": ""},
                                       headers={"User-Agent": UA, "Referer": SITE + "/cupfox-list/2-----------.html",
                                                "Content-Type": "application/x-www-form-urlencoded"}, timeout=20)
                    self._vstate = False
                else:
                    self._vstate = True
            except Exception:
                pass
        url = f"{SITE}/cupfox-search/{requests.utils.quote(key)}-------------.html"
        try:
            r = self.sess.get(url, headers=HDRS, timeout=20)
        except Exception:
            return {"list": []}
        if "系统安全验证" in r.text:
            if not _auto_verify(self.sess):
                return {"list": []}
            self._vstate = True
            try:
                r = self.sess.get(url, headers=HDRS, timeout=20)
            except Exception:
                return {"list": []}
        return {"list": _parse_list_html(r.text)}

    def playerContent(self, flag, id, vipFlags):
        parts = str(id).split("-")
        if len(parts) != 3:
            return {}
        pid, sid, nid = parts
        url = _resolve_play(self.sess, pid, sid, nid)
        if not url:
            return {}
        if ".m3u8" in url:
            try:
                rr = self.sess.get(url, headers={"User-Agent": UA, "Referer": SITE + "/"},
                                   timeout=15, allow_redirects=True, stream=True)
                ct = (rr.headers.get("Content-Type", "") or "").lower()
                if rr.status_code == 200 and (".m3u8" in rr.url or "mpegurl" in ct or "m3u8" in ct):
                    url = rr.url
            except Exception:
                pass
        hdr = f"User-Agent: {UA}\r\nReferer: {SITE}/"
        return {"parse": 0, "url": url, "header": hdr}
