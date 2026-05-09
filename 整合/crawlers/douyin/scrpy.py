# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from pymongo import MongoClient
from pymongo.errors import OperationFailure

import setting


PROJECT_DIR = Path(__file__).resolve().parent
DETAIL_API = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
SEARCH_API = "https://www.douyin.com/aweme/v1/web/general/search/single/"


def ensure_index(collection, *args, **kwargs):
    try:
        return collection.create_index(*args, **kwargs)
    except OperationFailure as exc:
        if getattr(exc, "code", None) in {85, 86}:
            return None
        raise


def resolve_project_path(value: Any) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


class VerifyCheckError(RuntimeError):
    pass


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", "").split()).strip()


def read_plain_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    path = resolve_project_path(value)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig") as file:
        return [line.strip() for line in file if line.strip() and not line.lstrip().startswith("#")]


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = bool(getattr(setting, "TRUST_ENV_PROXY", False))
    session.headers.update(setting.DEFAULT_REQUEST_HEADERS)
    cookie = clean_text(getattr(setting, "DOUYIN_COOKIE", ""))
    if cookie:
        session.headers["Cookie"] = cookie
    return session


def fetch(session: requests.Session, url: str, **kwargs) -> requests.Response:
    last_error = None
    for index in range(1, int(getattr(setting, "MAX_RETRY", 3)) + 1):
        try:
            response = session.get(url, timeout=getattr(setting, "REQUEST_TIMEOUT", 15), **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            print(f"请求失败，第 {index}/{setting.MAX_RETRY} 次: {exc}")
            time.sleep(float(getattr(setting, "DOWNLOAD_DELAY", 1)))
    raise RuntimeError(last_error)


def resolve_share_url(session: requests.Session, value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    match = re.search(r"https?://[^\s]+", text)
    if match:
        text = match.group(0)
    if "v.douyin.com" in text:
        response = session.get(text, allow_redirects=True, timeout=getattr(setting, "REQUEST_TIMEOUT", 15))
        return response.url
    return text


def extract_aweme_id(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"\d{8,}", text):
        return text

    parsed = urlparse(text)
    query = parse_qs(parsed.query)
    for key in ("modal_id", "aweme_id", "item_id"):
        if query.get(key):
            return query[key][0]

    patterns = [
        r"/video/(\d+)",
        r"/note/(\d+)",
        r"/discover\?modal_id=(\d+)",
        r"modal_id=(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def parse_json_from_html(text: str, aweme_id: str) -> Optional[Dict[str, Any]]:
    markers = [
        r'<script id="RENDER_DATA" type="application/json">(.*?)</script>',
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>',
    ]
    for pattern in markers:
        match = re.search(pattern, text, flags=re.S)
        if not match:
            continue
        raw = match.group(1)
        try:
            if "%" in raw:
                from urllib.parse import unquote

                raw = unquote(raw)
            data = json.loads(raw)
        except Exception:
            continue
        found = find_aweme_dict(data, aweme_id)
        if found:
            return found
    return None


def find_aweme_dict(value: Any, aweme_id: str) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        if str(value.get("aweme_id") or value.get("awemeId") or "") == aweme_id:
            return value
        for child in value.values():
            result = find_aweme_dict(child, aweme_id)
            if result:
                return result
    elif isinstance(value, list):
        for child in value:
            result = find_aweme_dict(child, aweme_id)
            if result:
                return result
    return None


def fetch_aweme(session: requests.Session, source: str) -> Dict[str, Any]:
    resolved = resolve_share_url(session, source)
    aweme_id = extract_aweme_id(resolved)
    if not aweme_id:
        raise ValueError(f"无法识别作品 id: {source}")

    params = {
        "aweme_id": aweme_id,
        "aid": "6383",
        "device_platform": "webapp",
    }
    response = fetch(session, DETAIL_API, params=params)
    try:
        data = response.json()
    except ValueError:
        data = {}

    aweme = data.get("aweme_detail") or data.get("aweme") or {}
    if aweme:
        return aweme

    # 某些环境接口返回空时，退回作品页 HTML 解析。
    page_url = resolved if resolved.startswith("http") else f"https://www.douyin.com/video/{aweme_id}"
    page = fetch(session, page_url).text
    aweme = parse_json_from_html(page, aweme_id)
    if not aweme:
        raise RuntimeError(f"未获取到作品详情，可能需要在 setting.py 配置 DOUYIN_COOKIE: {aweme_id}")
    return aweme


def build_search_filter() -> str:
    payload = {
        "sort_type": str(getattr(setting, "SORT_TYPE", "0")),
        "publish_time": str(getattr(setting, "PUBLISH_TIME", "0")),
        "filter_duration": str(getattr(setting, "FILTER_DURATION", "0")),
        "content_type": str(getattr(setting, "CONTENT_TYPE", "2")),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def find_aweme_dicts(value: Any) -> List[Dict[str, Any]]:
    results = []
    if isinstance(value, dict):
        nested = value.get("aweme_info") or value.get("awemeInfo") or value.get("aweme_detail")
        if isinstance(nested, dict):
            results.extend(find_aweme_dicts(nested))
        if value.get("aweme_id") or value.get("awemeId"):
            results.append(value)
        for child in value.values():
            if child is not nested:
                results.extend(find_aweme_dicts(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(find_aweme_dicts(child))
    return results


def unique_awemes(values: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    seen = set()
    for aweme in values:
        aweme_id = str(aweme.get("aweme_id") or aweme.get("awemeId") or "")
        if aweme_id and aweme_id not in seen:
            result.append(aweme)
            seen.add(aweme_id)
    return result


def search_awemes(session: requests.Session, keyword: str, page: int, cursor: int = 0) -> tuple[List[Dict[str, Any]], bool, int]:
    count = int(getattr(setting, "SEARCH_COUNT", 20))
    params = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "search_channel": "aweme_general",
        "keyword": keyword,
        "search_source": "normal_search",
        "query_correct_type": "1",
        "is_filter_search": "1",
        "filter_selected": build_search_filter(),
        "sort_type": str(getattr(setting, "SORT_TYPE", "0")),
        "publish_time": str(getattr(setting, "PUBLISH_TIME", "0")),
        "filter_duration": str(getattr(setting, "FILTER_DURATION", "0")),
        "content_type": str(getattr(setting, "CONTENT_TYPE", "2")),
        "offset": str(cursor),
        "count": str(count),
    }
    response = fetch(session, SEARCH_API, params=params)
    data = response.json()
    nil_info = data.get("search_nil_info") or {}
    nil_type = nil_info.get("search_nil_type") or nil_info.get("search_nil_item")
    if nil_type == "verify_check":
        ua = session.headers.get("User-Agent", "")
        raise VerifyCheckError(
            "抖音返回 verify_check。当前 Cookie 已被风控或浏览器指纹不匹配，"
            "请确认 setting.py 里的 User-Agent 和复制 Cookie 的浏览器一致，"
            f"当前 UA: {ua}"
        )
    if data.get("status_code") not in (None, 0):
        raise RuntimeError(f"抖音搜索接口返回异常: {data.get('status_code')} {data.get('status_msg') or data.get('message')}")
    awemes = unique_awemes(find_aweme_dicts(data.get("data") or data))
    has_more = bool(data.get("has_more") or data.get("hasMore"))
    next_cursor = int(data.get("cursor") or (cursor + count))
    return awemes, has_more, next_cursor


def get_nested(value: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def url_list_from_obj(obj: Dict[str, Any]) -> List[str]:
    urls = obj.get("url_list") or obj.get("urlList") or []
    if isinstance(urls, list):
        return [str(url) for url in urls if url]
    return []


def image_urls_from_aweme(aweme: Dict[str, Any]) -> List[str]:
    images = []
    seen = set()
    candidates = []
    candidates.extend(aweme.get("images") or [])
    image_album = aweme.get("image_album_music_info") or {}
    candidates.extend(image_album.get("image_list") or [])

    for image in candidates:
        if not isinstance(image, dict):
            continue
        url_sets = [
            image.get("url_list"),
            get_nested(image, "download_url", "url_list", default=[]),
            get_nested(image, "origin_cover", "url_list", default=[]),
            get_nested(image, "display_image", "url_list", default=[]),
        ]
        for urls in url_sets:
            if isinstance(urls, list):
                for url in urls:
                    if url and url not in seen:
                        images.append(str(url))
                        seen.add(url)
                        break
            if images and images[-1] in seen:
                break

    return images


def is_image_text_aweme(aweme: Dict[str, Any], item: Dict[str, Any]) -> bool:
    """True means the work behaves like Douyin's content-form filter: 图文."""
    if not clean_text(item.get("text")):
        return False
    if not item.get("pics"):
        return False

    # Douyin image-text works expose an image list. Video-only works usually
    # expose only video covers, which image_urls_from_aweme deliberately ignores.
    has_image_list = bool(aweme.get("images"))
    image_album = aweme.get("image_album_music_info") or {}
    has_album_images = bool(image_album.get("image_list"))
    return has_image_list or has_album_images


def format_time(timestamp: Any) -> str:
    try:
        value = int(timestamp or 0)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


def stats_count(value: Any) -> str:
    try:
        return str(int(value or 0))
    except (TypeError, ValueError):
        return "0"


def make_item(aweme: Dict[str, Any], source_url: str, crawl_keyword: str = "") -> Dict[str, Any]:
    aweme_id = str(aweme.get("aweme_id") or aweme.get("awemeId") or "")
    author = aweme.get("author") or {}
    statistics = aweme.get("statistics") or {}
    desc = clean_text(aweme.get("desc") or aweme.get("caption") or "")
    images = image_urls_from_aweme(aweme)
    nickname = author.get("nickname") or author.get("name") or "未知用户"
    sec_uid = author.get("sec_uid") or author.get("secUid") or ""
    uid = str(author.get("uid") or author.get("user_id") or "")

    return {
        "_key": f"douyin:{aweme_id}" if aweme_id else "",
        "note_id": f"douyin:{aweme_id}" if aweme_id else "",
        "id": f"douyin_{aweme_id}" if aweme_id else "",
        "original_id": aweme_id,
        "platform": "douyin",
        "platform_name": "抖音",
        "bid": aweme_id,
        "user_id": uid or sec_uid,
        "screen_name": nickname,
        "text": desc,
        "article_url": source_url or f"https://www.douyin.com/note/{aweme_id}",
        "location": clean_text(aweme.get("poi_name") or get_nested(aweme, "poi_info", "poi_name", default="")),
        "at_users": "",
        "topics": "",
        "reposts_count": stats_count(statistics.get("share_count")),
        "comments_count": stats_count(statistics.get("comment_count")),
        "attitudes_count": stats_count(statistics.get("digg_count")),
        "created_at": format_time(aweme.get("create_time")),
        "source": "抖音图文",
        "pics": images,
        "video_url": "",
        "retweet_id": "",
        "crawl_keyword": crawl_keyword,
        "keyword": "",
        "matched_keywords": [],
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "douyin": {
            "aweme_id": aweme_id,
            "aweme_type": aweme.get("aweme_type"),
            "content_form": "图文" if images else "",
            "sec_uid": sec_uid,
            "raw": aweme,
        },
    }


def match_filter_keywords(item: Dict[str, Any], filter_keywords: List[str]) -> List[str]:
    text = item.get("text", "")
    return [keyword for keyword in filter_keywords if keyword and keyword in text]


def get_pic_dir() -> Path:
    result_dir = resolve_project_path(getattr(setting, "RESULT_DIR", "result"))
    pic_dir = Path(getattr(setting, "PIC_DIR", "pic"))
    if not pic_dir.is_absolute():
        pic_dir = result_dir / pic_dir
    pic_dir.mkdir(parents=True, exist_ok=True)
    return pic_dir


def image_extension(url: str, content_type: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return suffix
    content_type = (content_type or "").lower()
    if "png" in content_type:
        return ".png"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def download_pics(session: requests.Session, item: Dict[str, Any]) -> List[str]:
    urls = item.get("pics") or []
    local_paths = []
    for index, url in enumerate(urls, start=1):
        try:
            response = session.get(url, timeout=getattr(setting, "IMAGE_TIMEOUT", 30))
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type.lower():
                raise ValueError(f"返回内容不是图片: {content_type}")
            local_path = get_pic_dir() / f"{item['id']}_{index}{image_extension(url, content_type)}"
            if not local_path.exists():
                local_path.write_bytes(response.content)
            local_paths.append(str(local_path.resolve()))
        except Exception as exc:
            print(f"图片下载失败，保留跳过: {url}，原因: {exc}")
    return local_paths


class SeenStore:
    def __init__(self, file_name: str):
        self.path = resolve_project_path(file_name)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ids = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as file:
                self.ids = {line.strip() for line in file if line.strip()}

    def has(self, item_id: str) -> bool:
        return item_id in self.ids

    def add(self, item_id: str) -> None:
        if not item_id or item_id in self.ids:
            return
        self.ids.add(item_id)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(item_id + "\n")


def load_sources() -> List[str]:
    sources = []
    sources.extend(read_plain_list(getattr(setting, "DOUYIN_URL_LIST", [])))
    source_file = clean_text(getattr(setting, "DOUYIN_URL_FILE", ""))
    if source_file:
        sources.extend(read_plain_list(source_file))
    result = []
    seen = set()
    for source in sources:
        if source not in seen:
            result.append(source)
            seen.add(source)
    return result


def load_search_keywords() -> List[str]:
    keywords = read_plain_list(getattr(setting, "DOUYIN_SEARCH_KEYWORD_LIST", []))
    if not keywords:
        keywords = read_plain_list(getattr(setting, "KEYWORD_LIST", []))
    result = []
    seen = set()
    for keyword in keywords:
        if keyword not in seen:
            result.append(keyword)
            seen.add(keyword)
    return result


def write_analysis_fields(collection, item):
    collection.update_one(
        {"id": item["id"]},
        {
            "$set": {
                "analysis": item.get("analysis"),
                "analysis_status": item.get("analysis_status"),
                "analysis_error": item.get("analysis_error", ""),
                "analysis_image": item.get("analysis_image", ""),
                "analysis_at": item.get("analysis_at"),
            }
        },
    )


def run_crawler(controller=None, log=print, progress=None, item_callback=None) -> Dict[str, int]:
    session = build_session()
    sources = load_sources()
    search_keywords = load_search_keywords()
    filter_keywords = read_plain_list(getattr(setting, "KEYWORD_LIST", []))
    seen = SeenStore(setting.SEEN_IDS_FILE)

    client = MongoClient(setting.MONGO_URI)
    collection = client[setting.MONGO_DATABASE][setting.MONGO_COLLECTION]
    ensure_index(collection, "id", unique=True)

    inserted = 0
    skipped = 0
    unmatched = 0
    discarded = 0
    max_items = int(getattr(setting, "MAX_ITEMS_PER_RUN", 50) or 0)

    def report_progress() -> None:
        if progress:
            progress(
                {
                    "inserted": inserted,
                    "skipped": skipped,
                    "unmatched": unmatched,
                    "discarded": discarded,
                }
            )

    if controller is None:
        controller = NullController()

    log(f"发现抖音搜索关键词 {len(search_keywords)} 个，指定作品来源 {len(sources)} 个。")
    if not search_keywords and not sources:
        log("没有配置抖音搜索关键词，请在 setting.py 的 DOUYIN_SEARCH_KEYWORD_LIST 或 KEYWORD_LIST 中填入关键词。")
        return {"inserted": inserted, "skipped": skipped, "unmatched": unmatched, "discarded": discarded}
    log("开始搜索并爬取抖音图文。")
    report_progress()

    try:
        def handle_aweme(aweme: Dict[str, Any], source_url: str = "", crawl_keyword: str = "") -> None:
            nonlocal inserted, skipped, unmatched, discarded
            if max_items > 0 and inserted >= max_items:
                return
            item = make_item(aweme, source_url, crawl_keyword=crawl_keyword)

            if not item.get("id") or seen.has(item["id"]):
                skipped += 1
                report_progress()
                return
            if getattr(setting, "REQUIRE_IMAGE_TEXT", True) and not is_image_text_aweme(aweme, item):
                discarded += 1
                log(f"跳过非有图有文的图文作品: {item.get('id')}")
                report_progress()
                return
            if getattr(setting, "REQUIRE_TEXT", True) and not clean_text(item.get("text")):
                discarded += 1
                log(f"跳过无正文作品: {item.get('id')}")
                report_progress()
                return
            if getattr(setting, "REQUIRE_IMAGES", True) and not item.get("pics"):
                discarded += 1
                log(f"跳过无图片作品: {item.get('id')}")
                report_progress()
                return

            matched = match_filter_keywords(item, filter_keywords)
            if getattr(setting, "REQUIRE_KEYWORD_MATCH", True) and not matched:
                unmatched += 1
                report_progress()
                return
            item["matched_keywords"] = matched
            item["keyword"] = ",".join(matched)
            local_pics = download_pics(session, item)
            if getattr(setting, "REQUIRE_IMAGES", True) and not local_pics:
                discarded += 1
                log(f"跳过，图片下载后无可用本地图片: {item.get('id')}")
                report_progress()
                return
            item["pics"] = local_pics
            collection.update_one({"id": item["id"]}, {"$set": item}, upsert=True)
            inserted += 1
            seen.add(item["id"])
            log(f"已写入: {item.get('screen_name')} / {item.get('id')}")
            report_progress()
            if item_callback:
                try:
                    item_callback(item)
                except Exception as exc:
                    item["analysis_status"] = "error"
                    item["analysis_error"] = str(exc)
                    log(f"多模态分析失败，抖音 {item['id']}: {exc}")
                write_analysis_fields(collection, item)

        for keyword in search_keywords:
            if max_items > 0 and inserted >= max_items:
                break
            cursor = 0
            for page in range(1, int(getattr(setting, "MAX_PAGES_PER_KEYWORD", 5)) + 1):
                if max_items > 0 and inserted >= max_items:
                    break
                controller.poll()
                controller.wait_if_paused()
                if controller.stopped:
                    raise KeyboardInterrupt

                try:
                    log(f"搜索关键词: {keyword}，第 {page} 页，内容形式=图文")
                    awemes, has_more, cursor = search_awemes(session, keyword, page, cursor=cursor)
                except VerifyCheckError as exc:
                    discarded += 1
                    log(f"搜索验证失败: {keyword} 第 {page} 页，原因: {exc}")
                    log("已停止本轮搜索，避免继续高频触发验证。请刷新抖音网页、复制最新 Cookie 后重启后端再试。")
                    report_progress()
                    raise KeyboardInterrupt
                except Exception as exc:
                    discarded += 1
                    log(f"搜索失败: {keyword} 第 {page} 页，原因: {exc}")
                    report_progress()
                    time.sleep(float(getattr(setting, "DOWNLOAD_DELAY", 2)))
                    break

                if not awemes:
                    log(f"关键词 {keyword} 第 {page} 页没有解析到作品。若浏览器里有结果，请更新 DOUYIN_COOKIE 后重试。")
                    break
                for aweme in awemes:
                    if max_items > 0 and inserted >= max_items:
                        break
                    controller.poll()
                    controller.wait_if_paused()
                    if controller.stopped:
                        raise KeyboardInterrupt
                    handle_aweme(aweme, crawl_keyword=keyword)
                if not has_more:
                    break
                delay = float(getattr(setting, "DOWNLOAD_DELAY", 2)) + random.uniform(0.5, 2.5)
                time.sleep(delay)

        for source in sources:
            if max_items > 0 and inserted >= max_items:
                break
            controller.poll()
            controller.wait_if_paused()
            if controller.stopped:
                raise KeyboardInterrupt

            try:
                resolved = resolve_share_url(session, source)
                log(f"抓取作品: {resolved or source}")
                aweme = fetch_aweme(session, resolved or source)
            except Exception as exc:
                discarded += 1
                log(f"跳过，抓取失败: {source}，原因: {exc}")
                report_progress()
                continue
            handle_aweme(aweme, resolved or source)
            delay = float(getattr(setting, "DOWNLOAD_DELAY", 2)) + random.uniform(0.5, 2.5)
            time.sleep(delay)

        if max_items > 0 and inserted >= max_items:
            log(f"已达到本平台本轮上限 {max_items} 条，停止抖音爬取。")

        if inserted:
            log(f"本轮写入/更新 {inserted} 条。")
        else:
            log("本轮没有可写入数据。")
    except KeyboardInterrupt:
        log("已退出。")
    finally:
        client.close()
        report_progress()
        log(
            f"完成。写入/更新 {inserted} 条，跳过重复 {skipped} 条，"
            f"未命中关键词 {unmatched} 条，丢弃 {discarded} 条。"
        )

    return {"inserted": inserted, "skipped": skipped, "unmatched": unmatched, "discarded": discarded}


class NullController:
    paused = False
    stopped = False

    def poll(self) -> None:
        return None

    def wait_if_paused(self) -> None:
        return None


if __name__ == "__main__":
    run_crawler()
