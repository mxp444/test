# -*- coding: utf-8 -*-
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from loguru import logger
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError, OperationFailure


PROJECT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROJECT_DIR
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import setting  # noqa: E402
from apis.xhs_pc_apis import XHS_Apis  # noqa: E402
from xhs_utils.cookie_util import trans_cookies  # noqa: E402
from xhs_utils.data_util import handle_note_info, timestamp_to_str  # noqa: E402
from xhs_utils.xhs_util import get_common_headers  # noqa: E402


def resolve_project_path(value) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def clean_count(value) -> str:
    if value is None:
        return "0"
    return str(value).replace(",", "").strip() or "0"


def note_text(note: Dict) -> str:
    title = (note.get("title") or "").strip()
    desc = (note.get("desc") or "").strip()
    if title and desc:
        return f"{title}\n{desc}"
    return title or desc


def is_video_note(note: Dict) -> bool:
    note_type = str(note.get("note_type") or "").lower()
    return note_type in {"video", "视频", "瑙嗛"} or bool(note.get("video_addr"))


def media_extension(url: str, content_type: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return suffix
    content_type = content_type.lower()
    if "png" in content_type:
        return ".png"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def image_dir(path: Optional[str] = None) -> Path:
    target = resolve_project_path(path) if path else PROJECT_DIR / "result" / "pic"
    target.mkdir(parents=True, exist_ok=True)
    return target


def configured_image_dir() -> Path:
    result_dir = resolve_project_path(getattr(setting, "RESULT_DIR", "result"))
    pic_dir = Path(getattr(setting, "PIC_DIR", "pic"))
    if not pic_dir.is_absolute():
        pic_dir = result_dir / pic_dir
    return image_dir(str(pic_dir))


def download_note_images(note: Dict, cookies_str: str, proxies=None, target_dir: Optional[str] = None) -> List[str]:
    urls = note.get("image_list") or []
    if not urls:
        return []

    headers = get_common_headers()
    headers["referer"] = note.get("note_url") or "https://www.xiaohongshu.com/"
    cookies = trans_cookies(cookies_str)
    session = requests.Session()
    session.trust_env = False
    local_paths = []

    for index, url in enumerate(urls, start=1):
        if not url:
            continue
        try:
            response = session.get(url, headers=headers, cookies=cookies, proxies=proxies, timeout=30)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type.lower():
                raise ValueError(f"response is not an image: {content_type}")
            path = image_dir(target_dir) / f"{note['note_id']}_{index}{media_extension(url, content_type)}"
            if not path.exists():
                path.write_bytes(response.content)
            local_paths.append(str(path.resolve()))
        except Exception as exc:
            logger.warning(f"download image failed, note_id={note.get('note_id')}, msg={exc}")
    return local_paths


def weibo_like_doc(note: Dict, keyword: str, pics: Optional[List[str]] = None) -> Dict:
    tags = note.get("tags") or []
    return {
        **note,
        "_key": f"xhs:{note.get('note_id', '')}" if note.get("note_id") else "",
        "note_id": f"xhs:{note.get('note_id', '')}" if note.get("note_id") else "",
        "id": f"xhs_{note.get('note_id', '')}" if note.get("note_id") else "",
        "original_id": note.get("note_id", ""),
        "platform": "xhs",
        "platform_name": "小红书",
        "bid": note.get("note_id", ""),
        "user_id": note.get("user_id", ""),
        "screen_name": note.get("nickname", ""),
        "text": note_text(note),
        "article_url": note.get("note_url", ""),
        "location": note.get("ip_location", ""),
        "at_users": "",
        "topics": ",".join(tags),
        "reposts_count": clean_count(note.get("share_count")),
        "comments_count": clean_count(note.get("comment_count")),
        "attitudes_count": clean_count(note.get("liked_count")),
        "created_at": note.get("upload_time", ""),
        "source": "小红书",
        "pics": pics or [],
        "video_url": note.get("video_addr") or "",
        "retweet_id": "",
        "crawl_keyword": keyword,
        "keyword": keyword,
        "matched_keywords": [keyword] if keyword else [],
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


class KeywordMongoSpider:
    def __init__(
        self,
        cookies_str: str,
        mongo_uri: str = "mongodb://localhost:27017/",
        db_name: str = "test",
        collection_name: str = "test_xhs",
        proxies: Optional[Dict[str, str]] = None,
        download_images: bool = True,
        image_path: Optional[str] = None,
    ):
        if not cookies_str:
            raise ValueError("cookies_str is empty. Set COOKIES in .env or pass --cookies.")

        self.cookies_str = cookies_str
        self.proxies = proxies
        self.download_images = download_images
        self.image_path = image_path
        self.xhs_apis = XHS_Apis()
        self.mongo_client = MongoClient(mongo_uri)
        self.collection: Collection = self.mongo_client[db_name][collection_name]
        self.ensure_indexes()

    def ensure_indexes(self):
        self.ensure_index("id", unique=True)
        self.ensure_index("keywords")
        self.ensure_index("crawl_time")

    def ensure_index(self, *args, **kwargs):
        try:
            return self.collection.create_index(*args, **kwargs)
        except OperationFailure as exc:
            if getattr(exc, "code", None) in {85, 86}:
                logger.warning(f"skip existing incompatible index: {exc.details.get('errmsg', exc)}")
                return None
            raise

    def search_notes(
        self,
        keyword: str,
        limit: int,
        sort_type_choice: int = 0,
        note_type: int = 0,
        note_time: int = 0,
        note_range: int = 0,
        pos_distance: int = 0,
        geo: Optional[Dict] = None,
    ) -> List[Dict]:
        success, msg, notes = self.xhs_apis.search_some_note(
            keyword,
            limit,
            self.cookies_str,
            sort_type_choice,
            note_type,
            note_time,
            note_range,
            pos_distance,
            geo or "",
            self.proxies,
        )
        if not success:
            raise RuntimeError(f"search failed: {msg}")
        return [note for note in notes if note.get("model_type") == "note"][:limit]

    def search_notes_page(
        self,
        keyword: str,
        page: int,
        sort_type_choice: int = 0,
        note_type: int = 0,
        note_time: int = 0,
        note_range: int = 0,
        pos_distance: int = 0,
        geo: Optional[Dict] = None,
    ) -> tuple[List[Dict], bool]:
        success, msg, res_json = self.xhs_apis.search_note(
            keyword,
            self.cookies_str,
            page,
            sort_type_choice,
            note_type,
            note_time,
            note_range,
            pos_distance,
            geo or "",
            self.proxies,
        )
        if not success:
            raise RuntimeError(f"search failed: {msg}")
        data = (res_json or {}).get("data") or {}
        items = [note for note in data.get("items", []) if note.get("model_type") == "note"]
        return items, bool(data.get("has_more"))

    def fetch_note_detail(self, search_note: Dict) -> Optional[Dict]:
        note_id = search_note.get("id")
        xsec_token = search_note.get("xsec_token")
        if not note_id or not xsec_token:
            return None

        note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"
        success, msg, note_info = self.xhs_apis.get_note_info(note_url, self.cookies_str, self.proxies)
        items = note_info.get("data", {}).get("items") or [] if note_info else []
        if success and items:
            item = items[0]
            item["url"] = note_url
            parsed = handle_note_info(item)
            parsed["detail_source"] = "feed"
            parsed["raw_search_note"] = search_note
            return parsed

        page_detail = self.fetch_note_from_page(note_id, xsec_token, search_note, note_url)
        if page_detail:
            return page_detail

        logger.warning(f"detail unavailable, note_id={note_id}, msg={msg}, use search card fallback")
        return self.build_note_from_search(search_note, note_url)

    def fetch_note_from_page(self, note_id: str, xsec_token: str, search_note: Dict, note_url: str) -> Optional[Dict]:
        headers = get_common_headers()
        headers["referer"] = "https://www.xiaohongshu.com/search_result"
        try:
            response = requests.get(
                note_url,
                headers=headers,
                cookies=trans_cookies(self.cookies_str),
                proxies=self.proxies,
                timeout=15,
            )
            response.raise_for_status()
            match = re.search(r"window\.__INITIAL_STATE__=(.*?)</script>", response.text, re.S)
            if not match:
                return None
            state = json.loads(match.group(1).strip().rstrip(";").replace(":undefined", ":null"))
            note_map = state.get("note", {}).get("noteDetailMap", {})
            wrapper = note_map.get(note_id) or next(iter(note_map.values()), {})
            note = wrapper.get("note", {})
            return self.build_note_from_page(note, search_note, note_url) if note else None
        except Exception as exc:
            logger.warning(f"fetch page detail failed, note_id={note_id}, msg={exc}")
            return None

    def build_note_from_page(self, note: Dict, search_note: Dict, note_url: str) -> Dict:
        note_id = note.get("noteId") or search_note.get("id")
        note_type = "视频" if note.get("type") == "video" else "图集"
        user = note.get("user", {})
        interact = note.get("interactInfo", {})
        images = []
        for image in note.get("imageList", []):
            url = image.get("urlDefault") or image.get("url")
            if not url:
                for item in image.get("infoList", []):
                    if item.get("imageScene") == "WB_DFT":
                        url = item.get("url")
                        break
            if url:
                images.append(url)

        video_addr = None
        if note_type == "视频":
            for image in note.get("imageList", []):
                h264 = (image.get("stream") or {}).get("h264") or []
                if h264:
                    video_addr = h264[0].get("masterUrl") or h264[0].get("url")
                    break

        upload_timestamp = note.get("time") or note.get("lastUpdateTime")
        user_id = user.get("userId", "")
        return {
            "note_id": note_id,
            "note_url": note_url,
            "note_type": note_type,
            "user_id": user_id,
            "home_url": f"https://www.xiaohongshu.com/user/profile/{user_id}" if user_id else "",
            "nickname": user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
            "title": note.get("title", ""),
            "desc": note.get("desc", ""),
            "liked_count": interact.get("likedCount", ""),
            "collected_count": interact.get("collectedCount", ""),
            "comment_count": interact.get("commentCount", ""),
            "share_count": interact.get("shareCount", ""),
            "video_cover": images[0] if images else None,
            "video_addr": video_addr,
            "image_list": images,
            "tags": [tag.get("name") for tag in note.get("tagList", []) if tag.get("name")],
            "upload_time": timestamp_to_str(upload_timestamp) if upload_timestamp else "",
            "upload_timestamp": upload_timestamp,
            "ip_location": note.get("ipLocation", ""),
            "detail_source": "page_initial_state",
            "raw_search_note": search_note,
        }

    def build_note_from_search(self, search_note: Dict, note_url: str) -> Dict:
        card = search_note.get("note_card", {})
        user = card.get("user", {})
        interact = card.get("interact_info", {})
        images = []
        for image in card.get("image_list", []):
            info_list = image.get("info_list") or []
            if info_list and (info_list[-1] or {}).get("url"):
                images.append(info_list[-1]["url"])
        note_type = "视频" if card.get("type") == "video" else "图集"
        user_id = user.get("user_id", "")
        return {
            "note_id": search_note["id"],
            "note_url": note_url,
            "note_type": note_type,
            "user_id": user_id,
            "home_url": f"https://www.xiaohongshu.com/user/profile/{user_id}" if user_id else "",
            "nickname": user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
            "title": card.get("title", ""),
            "desc": card.get("desc", ""),
            "liked_count": interact.get("liked_count", ""),
            "collected_count": interact.get("collected_count", ""),
            "comment_count": interact.get("comment_count", ""),
            "share_count": interact.get("share_count", ""),
            "video_cover": images[0] if note_type == "视频" and images else None,
            "video_addr": None,
            "image_list": images,
            "tags": [],
            "upload_time": "",
            "ip_location": "",
            "detail_source": "search_note_card",
            "raw_search_note": search_note,
        }

    @staticmethod
    def should_save_note(note: Dict) -> bool:
        text = note_text(note)
        return bool(text.strip()) and (bool(note.get("image_list")) or not getattr(setting, "REQUIRE_IMAGES", True)) and (
            getattr(setting, "SAVE_VIDEO_NOTES", False) or not is_video_note(note)
        )

    def process_search_notes(
        self,
        keyword: str,
        notes: List[Dict],
        sleep_seconds: float = 1.0,
        batch_size: int = 1,
        controller=None,
        log=None,
        progress=None,
        seen_store=None,
        item_callback=None,
    ) -> Dict[str, int]:
        log = log or logger.info
        stats = {"searched": len(notes), "fetched": 0, "saved": 0, "failed": 0, "inserted": 0, "skipped": 0, "unmatched": 0, "discarded": 0}
        batch = []
        batch_ids = []
        page_seen = set()

        def report():
            if progress:
                progress(dict(stats))

        report()
        for index, search_note in enumerate(notes, start=1):
            if controller:
                controller.poll()
                controller.wait_if_paused()
                if controller.stopped:
                    raise KeyboardInterrupt

            note_id = search_note.get("id")
            if not note_id:
                stats["discarded"] += 1
                report()
                continue
            if note_id in page_seen:
                stats["skipped"] += 1
                report()
                continue
            store_note_id = f"xhs:{note_id}" if note_id else ""
            if note_id and (
                (seen_store and seen_store.has(note_id))
                or self.collection.find_one(
                    {"$or": [{"note_id": store_note_id}, {"original_id": note_id}, {"id": f"xhs_{note_id}"}]},
                    {"_id": 1},
                )
            ):
                if seen_store:
                    seen_store.add(note_id)
                stats["skipped"] += 1
                report()
                continue
            if note_id:
                page_seen.add(note_id)

            log(f"抓取关键词 {keyword}: {index}/{len(notes)} note_id={note_id}")
            detail = self.fetch_note_detail(search_note)
            if detail is None:
                stats["failed"] += 1
                stats["unmatched"] += 1
                report()
                continue
            if not self.should_save_note(detail):
                if seen_store:
                    seen_store.add(note_id)
                stats["skipped"] += 1
                stats["discarded"] += 1
                report()
                continue

            stats["fetched"] += 1
            batch.append(detail)
            batch_ids.append(note_id)
            if len(batch) >= batch_size:
                saved = self.save_notes(keyword, batch, item_callback=item_callback, log=log)
                if seen_store:
                    for saved_id in batch_ids:
                        seen_store.add(saved_id)
                stats["saved"] += saved
                stats["inserted"] += saved
                batch.clear()
                batch_ids.clear()
                report()

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if batch:
            saved = self.save_notes(keyword, batch, item_callback=item_callback, log=log)
            if seen_store:
                for saved_id in batch_ids:
                    seen_store.add(saved_id)
            stats["saved"] += saved
            stats["inserted"] += saved
            report()
        return stats

    def crawl_keyword(
        self,
        keyword: str,
        limit: int,
        sort_type_choice: int = 0,
        note_type: int = 0,
        note_time: int = 0,
        note_range: int = 0,
        pos_distance: int = 0,
        geo: Optional[Dict] = None,
        sleep_seconds: float = 1.0,
        batch_size: int = 1,
        fetch_detail: bool = False,
        controller=None,
        log=None,
        progress=None,
        seen_store=None,
        item_callback=None,
    ) -> Dict[str, int]:
        notes = self.search_notes(keyword, limit, sort_type_choice, note_type, note_time, note_range, pos_distance, geo)
        return self.process_search_notes(
            keyword,
            notes,
            sleep_seconds=sleep_seconds,
            batch_size=batch_size,
            controller=controller,
            log=log,
            progress=progress,
            seen_store=seen_store,
            item_callback=item_callback,
        )

    def write_analysis_fields(self, doc: Dict):
        self.collection.update_one(
            {"id": doc["id"]},
            {
                "$set": {
                    "analysis": doc.get("analysis"),
                    "analysis_status": doc.get("analysis_status"),
                    "analysis_error": doc.get("analysis_error", ""),
                    "analysis_image": doc.get("analysis_image", ""),
                    "analysis_at": doc.get("analysis_at"),
                }
            },
        )

    def save_notes(self, keyword: str, notes: Iterable[Dict], item_callback=None, log=None) -> int:
        now = datetime.now(timezone.utc)
        operations = []
        docs = []
        for note in notes:
            local_pics = download_note_images(note, self.cookies_str, self.proxies, self.image_path) if self.download_images else []
            doc = {
                **weibo_like_doc(note, keyword, local_pics),
                "crawled_at": now,
                "updated_at": now,
            }
            docs.append(doc)
            operations.append(
                UpdateOne(
                    {"id": doc["id"]},
                    {"$set": doc, "$setOnInsert": {"inserted_at": now}, "$addToSet": {"keywords": keyword}},
                    upsert=True,
                )
            )
        if not operations:
            return 0
        try:
            result = self.collection.bulk_write(operations, ordered=False)
        except BulkWriteError as exc:
            logger.error(f"mongo bulk write error: {exc.details}")
            raise
        if item_callback:
            for doc in docs:
                try:
                    item_callback(doc)
                except Exception as exc:
                    doc["analysis_status"] = "error"
                    doc["analysis_error"] = str(exc)
                    if log:
                        log(f"多模态分析失败，小红书 {doc['id']}: {exc}")
                self.write_analysis_fields(doc)
        return result.upserted_count + result.modified_count

    def close(self):
        self.mongo_client.close()


def parse_proxy(proxy: Optional[str]) -> Optional[Dict[str, str]]:
    return {"http": proxy, "https": proxy} if proxy else None


class SeenStore:
    def __init__(self, file_name: str):
        self.path = resolve_project_path(file_name)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.ids = {line.strip() for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()}
        else:
            self.ids = set()

    def has(self, note_id: str) -> bool:
        return bool(note_id) and note_id in self.ids

    def add(self, note_id: str):
        if not note_id or note_id in self.ids:
            return
        self.ids.add(note_id)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(note_id + "\n")


def read_keywords(value) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    path = resolve_project_path(value)
    if not path.exists():
        return [str(value).strip()] if str(value).strip() else []
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def run_crawler(controller=None, log=print, progress=None, item_callback=None) -> Dict[str, int]:
    load_dotenv(PROJECT_ROOT / ".env")
    keywords = read_keywords(getattr(setting, "KEYWORD_LIST", []))
    cookies = getattr(setting, "COOKIES", None) or os.getenv("COOKIES")
    spider = KeywordMongoSpider(
        cookies_str=cookies,
        mongo_uri=getattr(setting, "MONGO_URI", "mongodb://localhost:27017/"),
        db_name=getattr(setting, "MONGO_DATABASE", "test"),
        collection_name=getattr(setting, "MONGO_COLLECTION", "test_xhs"),
        proxies=parse_proxy(getattr(setting, "PROXY", None)),
        download_images=getattr(setting, "DOWNLOAD_IMAGES", True),
        image_path=str(configured_image_dir()),
    )
    seen = SeenStore(getattr(setting, "SEEN_IDS_FILE", "seen_ids.txt"))
    total = {"inserted": 0, "skipped": 0, "unmatched": 0, "discarded": 0, "searched": 0, "fetched": 0, "saved": 0, "failed": 0}
    max_items = int(getattr(setting, "MAX_ITEMS_PER_RUN", 50) or 0)

    def merge(stats: Dict[str, int]):
        for key in total:
            total[key] = total.get(key, 0) + int(stats.get(key, 0))
        if progress:
            progress({k: total.get(k, 0) for k in ("inserted", "skipped", "unmatched", "discarded")})

    try:
        limit_per_keyword = getattr(setting, "LIMIT_PER_KEYWORD", 50)
        page_size = 20
        max_pages = getattr(setting, "MAX_PAGES", None) or max(1, (limit_per_keyword + page_size - 1) // page_size)
        states = [{"keyword": keyword, "next_page": 1, "seen": 0} for keyword in keywords]
        if getattr(setting, "RANDOMIZE_CRAWL_ORDER", True):
            random.shuffle(states)

        log(f"开始抓取小红书关键词 {len(keywords)} 个，随机交错搜索，每词最多 {max_pages} 页")
        while states and (max_items <= 0 or total["inserted"] < max_items):
            if controller:
                controller.poll()
                controller.wait_if_paused()
                if controller.stopped:
                    raise KeyboardInterrupt

            state = random.choice(states) if getattr(setting, "RANDOMIZE_CRAWL_ORDER", True) else states[0]
            keyword = state["keyword"]
            page = state["next_page"]
            state["next_page"] += 1

            log(f"发现搜索词 {keyword}，第 {page} 页")
            try:
                search_notes, has_more = spider.search_notes_page(
                    keyword=keyword,
                    page=page,
                    sort_type_choice=getattr(setting, "SORT_TYPE", 0),
                    note_type=getattr(setting, "NOTE_TYPE", 2),
                    note_time=getattr(setting, "NOTE_TIME", 0),
                    note_range=getattr(setting, "NOTE_RANGE", 0),
                )
            except Exception as exc:
                total["discarded"] += 1
                states.remove(state)
                log(f"小红书搜索失败，已跳过搜索词 {keyword}: {exc}")
                if progress:
                    progress({k: total.get(k, 0) for k in ("inserted", "skipped", "unmatched", "discarded")})
                continue
            if not search_notes:
                states.remove(state)
                log(f"搜索词 {keyword} 没有更多结果，移出随机池。")
                continue

            remaining = max(0, limit_per_keyword - state["seen"])
            if max_items > 0:
                remaining = min(remaining, max(0, max_items - total["inserted"]))
            if remaining <= 0:
                states.remove(state)
                continue
            search_notes = search_notes[:remaining]
            state["seen"] += len(search_notes)
            stats = spider.process_search_notes(
                keyword=keyword,
                notes=search_notes,
                sleep_seconds=getattr(setting, "DOWNLOAD_DELAY", 1.0),
                batch_size=getattr(setting, "BATCH_SIZE", 1),
                controller=controller,
                log=log,
                seen_store=seen,
                item_callback=item_callback,
            )
            merge(stats)
            log(f"搜索词 {keyword} 第 {page} 页完成：写入 {stats.get('inserted', 0)}，重复/跳过 {stats.get('skipped', 0)}")
            if state["next_page"] > max_pages or state["seen"] >= limit_per_keyword or not has_more:
                states.remove(state)
                log(f"搜索词 {keyword} 达到结束条件，移出随机池。")
        if max_items > 0 and total["inserted"] >= max_items:
            log(f"已达到本平台本轮上限 {max_items} 条，停止小红书爬取。")
    except KeyboardInterrupt:
        log("已退出。")
    finally:
        spider.close()
        log(f"完成。写入 {total['inserted']}，重复/跳过 {total['skipped']}，失败 {total['unmatched']}，丢弃 {total['discarded']}")
        if progress:
            progress({k: total.get(k, 0) for k in ("inserted", "skipped", "unmatched", "discarded")})
    return {k: total.get(k, 0) for k in ("inserted", "skipped", "unmatched", "discarded")}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search Xiaohongshu notes and save them to MongoDB.")
    parser.add_argument("--keyword", default="榴莲", help="search keyword")
    parser.add_argument("--limit", type=int, default=50, help="max notes to crawl")
    parser.add_argument("--cookies", default=None, help="Xiaohongshu cookies string")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017/", help="MongoDB URI")
    parser.add_argument("--db", default="test", help="MongoDB database")
    parser.add_argument("--collection", default="test_xhs", help="MongoDB collection")
    parser.add_argument("--sort", type=int, default=0, help="0 general, 1 latest, 2 like, 3 comment, 4 collect")
    parser.add_argument("--note-type", type=int, default=2, help="0 all, 1 video, 2 normal")
    parser.add_argument("--note-time", type=int, default=0, help="0 all, 1 day, 2 week, 3 half year")
    parser.add_argument("--note-range", type=int, default=0, help="0 all, 1 viewed, 2 not viewed, 3 followed")
    parser.add_argument("--sleep", type=float, default=1.0, help="sleep seconds")
    parser.add_argument("--batch-size", type=int, default=1, help="MongoDB batch size")
    parser.add_argument("--proxy", default=None, help="proxy URL, for example http://127.0.0.1:7890")
    parser.add_argument("--no-download-images", action="store_true", help="do not download images locally")
    return parser


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args()
    spider = KeywordMongoSpider(
        cookies_str=args.cookies or os.getenv("COOKIES"),
        mongo_uri=args.mongo_uri,
        db_name=args.db,
        collection_name=args.collection,
        proxies=parse_proxy(args.proxy),
        download_images=not args.no_download_images,
    )
    seen = SeenStore("seen_ids.txt")
    try:
        stats = spider.crawl_keyword(
            keyword=args.keyword,
            limit=args.limit,
            sort_type_choice=args.sort,
            note_type=args.note_type,
            note_time=args.note_time,
            note_range=args.note_range,
            sleep_seconds=args.sleep,
            batch_size=args.batch_size,
            seen_store=seen,
        )
        logger.info(f"done: {stats}")
    finally:
        spider.close()


if __name__ == "__main__":
    main()
