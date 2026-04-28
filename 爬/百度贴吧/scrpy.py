# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import enum
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

import requests
from pymongo import MongoClient, UpdateOne

import setting


PROJECT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = PROJECT_DIR.parent / "百度贴吧爬虫"
try:
    import aiotieba as tb  # noqa: E402
except ImportError:
    for extra_path in (
        PROJECT_DIR / ".tmp_aiotieba_pkg",
        PROJECT_DIR / "src",
        CRAWLER_DIR / ".tmp_aiotieba_pkg",
        CRAWLER_DIR / "src",
    ):
        if extra_path.exists() and str(extra_path) not in sys.path:
            sys.path.insert(0, str(extra_path))
    import aiotieba as tb  # noqa: E402


def resolve_project_path(value: Any) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def to_plain(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if hasattr(value, "value") and hasattr(value, "name"):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain(v) for v in value]
    return str(value)


def thread_sort_type(sort_name: str) -> Any:
    sort_map = {
        "create": tb.ThreadSortType.CREATE,
        "reply": tb.ThreadSortType.REPLY,
        "hot": tb.ThreadSortType.HOT,
        "follow": tb.ThreadSortType.FOLLOW,
    }
    return sort_map.get(str(sort_name).lower(), tb.ThreadSortType.CREATE)


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", "").split()).strip()


def contents_text(contents: Any, fallback: str = "") -> str:
    text = clean_text(getattr(contents, "text", "") or "")
    return text or clean_text(fallback)


def image_docs_from_contents(contents: Any) -> List[Dict[str, Any]]:
    images = []
    for image in list(getattr(contents, "imgs", []) or []):
        doc = {
            "src": getattr(image, "src", None),
            "big_src": getattr(image, "big_src", None),
            "origin_src": getattr(image, "origin_src", None),
            "hash": getattr(image, "hash", None),
        }
        images.append({key: to_plain(value) for key, value in doc.items() if value})
    return images


def best_image_urls(images: Iterable[Dict[str, Any]]) -> List[str]:
    urls = []
    seen = set()
    for image in images:
        for key in ("origin_src", "big_src", "src"):
            url = image.get(key)
            if url and url not in seen:
                urls.append(str(url))
                seen.add(url)
                break
    return urls


def read_plain_keywords(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    path = resolve_project_path(value)
    with path.open("r", encoding="utf-8-sig") as file:
        return [line.strip() for line in file if line.strip()]


def match_filter_keywords(item: Dict[str, Any], filter_keywords: List[str]) -> List[str]:
    haystack = f"{item.get('text', '')} {item.get('title', '')}"
    return [keyword for keyword in filter_keywords if keyword and keyword in haystack]


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
    pic_urls = item.get("pics") or []
    if not pic_urls:
        return []

    local_paths = []
    for index, url in enumerate(pic_urls, start=1):
        try:
            response = session.get(url, timeout=getattr(setting, "IMAGE_TIMEOUT", 30))
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type.lower():
                raise ValueError(f"返回内容不是图片: {content_type}")
            ext = image_extension(url, content_type)
            local_path = get_pic_dir() / f"{item['id']}_{index}{ext}"
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


def format_time(timestamp: Any) -> str:
    try:
        value = int(timestamp or 0)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


def make_weibo_shape(thread: Any, forum: str, page: int) -> Dict[str, Any]:
    tid = str(getattr(thread, "tid", "") or "")
    thread_key = f"thread:{tid}" if tid else ""
    contents = getattr(thread, "contents", None)
    images = image_docs_from_contents(contents)
    user = getattr(thread, "user", None)
    user_id = str(getattr(thread, "author_id", "") or getattr(user, "user_id", "") or "")
    screen_name = (
        getattr(user, "nick_name", None)
        or getattr(user, "nick_name_new", None)
        or getattr(user, "user_name", None)
        or "未知用户"
    )
    title = clean_text(getattr(thread, "title", ""))
    text = contents_text(contents, getattr(thread, "text", ""))
    body = f"{title}\n{text}".strip() if title and title not in text else text or title

    return {
        "_key": thread_key,
        "_doc_type": "thread",
        "note_id": thread_key,
        "id": tid,
        "bid": tid,
        "user_id": user_id,
        "screen_name": screen_name,
        "text": body,
        "title": title,
        "article_url": f"https://tieba.baidu.com/p/{tid}" if tid else "",
        "location": "",
        "at_users": "",
        "topics": forum,
        "reposts_count": "0",
        "comments_count": str(getattr(thread, "reply_num", 0) or 0),
        "attitudes_count": str(getattr(thread, "agree", 0) or 0),
        "created_at": format_time(getattr(thread, "create_time", None)),
        "source": f"百度贴吧/{forum}吧",
        "pics": best_image_urls(images),
        "video_url": "",
        "retweet_id": "",
        "crawl_keyword": forum,
        "keyword": "",
        "matched_keywords": [],
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tieba": {
            "tid": getattr(thread, "tid", None),
            "pid": getattr(thread, "pid", None),
            "fid": getattr(thread, "fid", None),
            "fname": forum,
            "forum_page": page,
            "view_num": getattr(thread, "view_num", None),
            "reply_num": getattr(thread, "reply_num", None),
            "images": images,
            "raw_thread": to_plain(thread),
        },
    }


def passes_basic_filters(item: Dict[str, Any]) -> bool:
    if getattr(setting, "REQUIRE_TEXT", True) and not clean_text(item.get("text")):
        return False
    if getattr(setting, "REQUIRE_IMAGES", True) and not item.get("pics"):
        return False
    return True


async def fetch_forum_page(client: tb.Client, forum: str, page: int) -> List[Any]:
    threads = await client.get_threads(
        forum,
        pn=page,
        rn=int(getattr(setting, "THREAD_PAGE_SIZE", 30)),
        sort=thread_sort_type(getattr(setting, "THREAD_SORT", "create")),
    )
    if getattr(threads, "err", None):
        raise RuntimeError(f"{forum}吧第 {page} 页抓取失败: {threads.err}")
    thread_objs = list(getattr(threads, "objs", []) or [])
    max_threads = int(getattr(setting, "MAX_THREADS_PER_PAGE", 30))
    if max_threads > 0:
        thread_objs = thread_objs[:max_threads]
    return thread_objs


def build_forum_states(forums: List[str]) -> List[Dict[str, Any]]:
    states = [{"forum": forum, "next_page": 1} for forum in forums]
    if getattr(setting, "RANDOMIZE_FORUM_ORDER", True):
        random.shuffle(states)
    return states


def pick_forum_state(states: List[Dict[str, Any]]) -> Dict[str, Any]:
    if getattr(setting, "RANDOMIZE_FORUM_ORDER", True):
        return random.choice(states)
    return states[0]


async def run_async_crawler(controller, log, progress) -> Dict[str, int]:
    filter_keywords = read_plain_keywords(setting.KEYWORD_LIST)
    forums = read_plain_keywords(setting.FORUM_LIST)
    seen = SeenStore(setting.SEEN_IDS_FILE)

    session = requests.Session()
    session.trust_env = bool(getattr(setting, "TRUST_ENV_PROXY", False))
    session.headers.update(setting.DEFAULT_REQUEST_HEADERS)

    mongo_client = MongoClient(setting.MONGO_URI)
    collection = mongo_client[setting.MONGO_DATABASE][setting.MONGO_COLLECTION]
    collection.create_index("id", unique=True)
    collection.create_index("_key", unique=True)

    inserted = 0
    skipped = 0
    unmatched = 0
    discarded = 0

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

    log(f"发现贴吧: {len(forums)} 个，正文筛选关键词: {len(filter_keywords)} 个。")
    log("开始爬取百度贴吧主题帖。")
    report_progress()

    try:
        async with tb.Client() as tieba_client:
            max_pages = int(getattr(setting, "MAX_PAGES_PER_FORUM", 5))
            forum_states = build_forum_states(forums)
            while forum_states:
                controller.poll()
                controller.wait_if_paused()
                if controller.stopped:
                    raise KeyboardInterrupt

                state = pick_forum_state(forum_states)
                forum = state["forum"]
                page = state["next_page"]
                state["next_page"] += 1

                log(f"抓取 {forum}吧，第 {page} 页")
                try:
                    threads = await fetch_forum_page(tieba_client, forum, page)
                except Exception as exc:
                    forum_states.remove(state)
                    log(f"{forum}吧第 {page} 页抓取失败，已跳过该吧: {exc}")
                    await asyncio.sleep(float(getattr(setting, "DOWNLOAD_DELAY", 0.5)))
                    continue
                if not threads:
                    forum_states.remove(state)
                    log(f"{forum}吧第 {page} 页没有更多主题帖，移出随机池。")
                    continue
                if state["next_page"] > max_pages:
                    forum_states.remove(state)

                operations = []
                for thread in threads:
                    controller.poll()
                    controller.wait_if_paused()
                    if controller.stopped:
                        raise KeyboardInterrupt

                    item = make_weibo_shape(thread, forum, page)
                    if not item.get("id") or seen.has(item["id"]):
                        skipped += 1
                        report_progress()
                        continue
                    if not passes_basic_filters(item):
                        discarded += 1
                        report_progress()
                        continue
                    matched_keywords = match_filter_keywords(item, filter_keywords)
                    if not matched_keywords:
                        unmatched += 1
                        report_progress()
                        continue
                    item["matched_keywords"] = matched_keywords
                    item["keyword"] = ",".join(matched_keywords)
                    item["pics"] = download_pics(session, item)
                    operations.append(
                        UpdateOne(
                            {
                                "$or": [
                                    {"id": item["id"]},
                                    {"_key": item["_key"]},
                                    {"note_id": item["note_id"]},
                                ]
                            },
                            {"$set": item},
                            upsert=True,
                        )
                    )
                    seen.add(item["id"])
                    inserted += 1
                    report_progress()

                if operations:
                    collection.bulk_write(operations, ordered=False)
                log(
                    f"本页写入 {len(operations)} 条，累计写入 {inserted} 条，"
                    f"跳过重复 {skipped} 条，未命中关键词 {unmatched} 条，丢弃 {discarded} 条。"
                )
                await asyncio.sleep(float(getattr(setting, "DOWNLOAD_DELAY", 0.5)))
    except KeyboardInterrupt:
        log("已退出。")
    finally:
        mongo_client.close()
        report_progress()
        log(
            f"完成。写入/更新 {inserted} 条，跳过重复 {skipped} 条，"
            f"未命中关键词 {unmatched} 条，丢弃 {discarded} 条。"
        )

    return {"inserted": inserted, "skipped": skipped, "unmatched": unmatched, "discarded": discarded}


def run_crawler(controller=None, log=print, progress=None) -> Dict[str, int]:
    if controller is None:
        controller = NullController()
    return asyncio.run(run_async_crawler(controller, log, progress))


class NullController:
    paused = False
    stopped = False

    def poll(self) -> None:
        return None

    def wait_if_paused(self) -> None:
        return None


def main() -> None:
    run_crawler()


if __name__ == "__main__":
    main()
