#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
from urllib.parse import quote, unquote, urljoin, urlparse, parse_qs

try:
    from base.spider import Spider as BaseSpider
except Exception:
    import requests
    class BaseSpider(object):
        def fetch(self, url, headers=None, timeout=15, **kwargs):
            return requests.get(url, headers=headers, timeout=timeout, **kwargs)

from lxml import etree


class Spider(BaseSpider):
    def getName(self):
        return "厂长资源4K"

    def init(self, extend=""):
        self.host = "https://www.4kcz.com"
        self.name = "厂长资源4K"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/movie_bt",
            "Connection": "keep-alive",
        }

    def homeContent(self, filter):
        self.init()
        classes = [
            {"type_name": "全部", "type_id": "movie_bt"},
            {"type_name": "电影", "type_id": "movie_bt_series/dyy"},
            {"type_name": "电视剧", "type_id": "movie_bt_series/dianshiju"},
            {"type_name": "国产剧", "type_id": "movie_bt_series/guochanju"},
            {"type_name": "美剧", "type_id": "movie_bt_series/mj"},
            {"type_name": "韩剧", "type_id": "movie_bt_series/hj"},
            {"type_name": "日剧", "type_id": "movie_bt_series/rj"},
            {"type_name": "番剧", "type_id": "fanju"},
            {"type_name": "动漫", "type_id": "movie_bt_series/dohua"},
        ]
        filters = {
            "movie_bt": [
                {"key": "tag", "name": "类型", "value": self._opts([("全部", ""), ("剧情", "movie_bt_tags/juqing"), ("动作", "movie_bt_tags/dozuo"), ("喜剧", "movie_bt_tags/xiju"), ("爱情", "movie_bt_tags/aiqing"), ("科幻", "movie_bt_tags/kh"), ("悬疑", "movie_bt_tags/xuanyi"), ("恐怖", "movie_bt_tags/kongbu"), ("纪录片", "movie_bt_tags/jilupian")])},
                {"key": "area", "name": "地区", "value": self._opts([("全部", ""), ("大陆", "movie_bt_cat/zh"), ("香港", "movie_bt_cat/hk"), ("台湾", "movie_bt_cat/tw"), ("美国", "movie_bt_cat/mg"), ("韩国", "movie_bt_cat/hanguo"), ("日本", "movie_bt_cat/rb"), ("英国", "movie_bt_cat/yg")])},
                {"key": "year", "name": "年份", "value": self._opts([("全部", "")] + [(str(i), "year/" + str(i)) for i in range(2028, 2010, -1)])},
            ]
        }
        for c in classes:
            filters.setdefault(c["type_id"], filters["movie_bt"])
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        self.init()
        try:
            root = self._html(self.host + "/movie_bt")
            return {"list": self._parse_vods(root)[:24]}
        except Exception as e:
            print(f"[{self.name}] 错误: 首页爬取失败 - {e}")
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        self.init()
        try:
            pg = str(pg or "1")
            path = self._pick_path(str(tid), extend or {})
            url = self._page_url(path, pg)
            root = self._html(url)
            vods = self._parse_vods(root)
            pagecount, total = self._page_info(root, pg, len(vods))
            print(f"[{self.name}] 分类列表匹配到 {len(vods)} 个视频")
            return {"list": vods, "page": int(pg), "pagecount": pagecount, "limit": 20, "total": total}
        except Exception as e:
            print(f"[{self.name}] 错误: 分类爬取失败 - {e}")
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 20, "total": 0}

    def detailContent(self, ids):
        self.init()
        try:
            vid = ids[0] if isinstance(ids, list) else ids
            url = self._detail_url(str(vid))
            vid = self._id_from_url(url) or str(vid)
            root = self._html(url)
            html_text = etree.tostring(root, encoding="unicode")
            name = self._clean(self._first(root.xpath('//meta[@property="og:title"]/@content'))) or self._clean(root.xpath('string(//div[contains(@class,"moviedteail_tt")]//h1)'))
            pic = self._fix(self._first(root.xpath('//meta[@property="og:image"]/@content | //div[contains(@class,"dyimg")]//img/@src')))
            desc = self._clean(root.xpath('string(//div[contains(@class,"yp_context")])') or self._first(root.xpath('//meta[@name="description"]/@content')))
            info = self._detail_info(root)
            play_from, play_url = self._parse_play(root)
            vod = {
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "type_name": info.get("类型", ""),
                "vod_year": info.get("年份", ""),
                "vod_area": info.get("地区", ""),
                "vod_remarks": "",
                "vod_actor": info.get("主演", ""),
                "vod_director": info.get("导演", ""),
                "vod_content": desc,
                "vod_play_from": play_from,
                "vod_play_url": play_url,
            }
            if not vod["vod_year"]:
                m = re.search(r"/year/(\d{4})", html_text)
                vod["vod_year"] = m.group(1) if m else ""
            print(f"[{self.name}] 详情页提取到 {len(play_url.split('#')) if play_url else 0} 集")
            return {"list": [vod]}
        except Exception as e:
            print(f"[{self.name}] 错误: 详情解析失败 - {e}")
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        self.init()
        try:
            url = self.host + "/boss1O1?q=" + quote(str(key))
            if str(pg) != "1":
                url += "&page=" + str(pg)
            root = self._html(url)
            vods = self._parse_vods(root)
            print(f"[{self.name}] 搜索结果匹配到 {len(vods)} 个视频")
            return {"list": vods, "page": int(pg or 1), "pagecount": 1, "limit": 20, "total": len(vods)}
        except Exception as e:
            print(f"[{self.name}] 错误: 搜索失败 - {e}")
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        self.init()
        try:
            url = self._fix(str(id))
            if self.isVideoFormat(url):
                return {"parse": 0, "playUrl": "", "url": url, "header": self.header}
            text = self._text(url)
            iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', text, re.I)
            src = unquote(iframe.group(1)).replace("&amp;", "&") if iframe else ""
            play = ""
            if src:
                qs = parse_qs(urlparse(src).query)
                play = unquote((qs.get("url") or [""])[0])
                if not play and self.isVideoFormat(src):
                    play = src
            if not play:
                m = re.search(r'(https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)', text, re.I)
                play = unquote(m.group(1)) if m else src or url
            print(f"[{self.name}] 播放解析: {flag} -> {play[:60]}...")
            return {"parse": 0 if self.isVideoFormat(play) else 1, "playUrl": "", "url": play, "header": self.header}
        except Exception as e:
            print(f"[{self.name}] 错误: 播放解析失败 - {e}")
            return {"parse": 1, "playUrl": "", "url": id, "header": self.header}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|avi|mkv|mov)(\?|$)", str(url), re.I))

    def manualVideoCheck(self):
        return True

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]

    def destroy(self):
        pass

    def _opts(self, pairs):
        return [{"n": n, "v": v} for n, v in pairs]

    def _pick_path(self, tid, ext):
        for k in ["year", "area", "tag"]:
            if ext.get(k):
                return str(ext.get(k)).strip("/")
        return tid.strip("/") or "movie_bt"

    def _page_url(self, path, pg):
        path = path.strip("/")
        if pg and str(pg) != "1":
            path += "/page/" + str(pg)
        return self.host + "/" + path

    def _detail_url(self, vid):
        if vid.startswith("http"):
            return vid
        m = re.search(r"(\d+)", vid)
        return self.host + "/movie/" + (m.group(1) if m else vid) + ".html"

    def _text(self, url):
        rsp = self.fetch(url, headers=self.header, timeout=15)
        text = rsp.text if hasattr(rsp, "text") else (rsp.get("content") if isinstance(rsp, dict) else str(rsp))
        if "safeline" in text.lower() or "Access Forbidden" in text:
            h = dict(self.header)
            h["Referer"] = self.host + "/movie_bt"
            rsp = self.fetch(url, headers=h, timeout=15)
            text = rsp.text if hasattr(rsp, "text") else (rsp.get("content") if isinstance(rsp, dict) else str(rsp))
        return text

    def _html(self, url):
        return etree.HTML(self._text(url))

    def _parse_vods(self, root):
        vods, seen = [], set()
        items = root.xpath('//ul[.//h3[contains(@class,"dytit")]]/li[.//a[contains(@href,"/movie/")]]')
        if not items:
            items = root.xpath('//li[.//a[contains(@href,"/movie/")] and .//img]')
        for it in items:
            try:
                href = self._first(it.xpath('.//h3[contains(@class,"dytit")]//a[contains(@href,"/movie/")]/@href | .//a[contains(@href,"/movie/")]/@href'))
                vid = self._id_from_url(href)
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                name = self._clean(self._first(it.xpath('.//h3[contains(@class,"dytit")]//a/text() | .//img/@alt')))
                pic = self._first(it.xpath('.//img/@data-original')) or self._first(it.xpath('.//img/@data-src')) or self._first(it.xpath('.//img/@src'))
                if "blank.gif" in pic:
                    pic = self._first(it.xpath('.//img/@data-original')) or pic
                pic = self._fix(pic)
                remarks = self._clean(" ".join(it.xpath('.//div[contains(@class,"hdinfo")]//text()')))
                vods.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": remarks})
            except Exception as e:
                print(f"[{self.name}] 单条列表解析跳过: {e}")
        return vods

    def _detail_info(self, root):
        data = {}
        for li in root.xpath('//ul[contains(@class,"moviedteail_list")]/li'):
            txt = self._clean(" ".join(li.xpath(".//text()")))
            if "：" in txt:
                k, v = txt.split("：", 1)
                data[self._clean(k)] = self._clean(v)
        return data

    def _parse_play(self, root):
        eps = []
        links = root.xpath('//div[contains(@class,"paly_list_btn")]//a[contains(@href,"/v_play/")]')
        if not links:
            links = root.xpath('//a[contains(@href,"/v_play/")]')
        seen = set()
        for a in links:
            href = self._fix(self._first(a.xpath("./@href")))
            name = self._clean(a.xpath("string(.)")) or "播放"
            if href and href not in seen:
                seen.add(href)
                eps.append(name + "$" + href)
        return ("在线播放", "#".join(eps)) if eps else ("", "")

    def _page_info(self, root, pg, count):
        html = etree.tostring(root, encoding="unicode")
        pages = [int(x) for x in re.findall(r"/page/(\d+)", html)]
        pagecount = max(pages) if pages else max(int(pg), 1)
        total = pagecount * max(count, 1)
        return pagecount, total

    def _id_from_url(self, url):
        m = re.search(r"/movie/(\d+)\.html", str(url))
        return m.group(1) if m else ""

    def _fix(self, url):
        url = (url or "").strip()
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        return urljoin(self.host + "/", url)

    def _clean(self, text):
        return re.sub(r"\s+", " ", str(text or "")).strip(" /　\t\r\n")

    def _first(self, arr):
        return arr[0] if arr else ""
