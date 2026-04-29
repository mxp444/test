# -*- coding: utf-8 -*-
import importlib.util
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
from uuid import uuid4

import requests
from flask import Flask, jsonify, request, send_file, send_from_directory
from bson import ObjectId
from pymongo import DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "backend" / "uploads"
ENGINE_FILE = BASE_DIR / "多模态融合分析.py"
CRAWLER_DIR = BASE_DIR / "crawler"
CRAWLERS_DIR = BASE_DIR / "crawlers"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LOAD_WORD_VECTOR_MODEL_ENV = os.getenv("LOAD_WORD_VECTOR_MODEL")
LOAD_WORD_VECTOR_MODEL = (
    None
    if LOAD_WORD_VECTOR_MODEL_ENV is None
    else LOAD_WORD_VECTOR_MODEL_ENV.strip().lower() not in {"0", "false", "no", "off"}
)
CRAWL_TOTAL_TARGET = max(1, int(os.getenv("CRAWL_TOTAL_TARGET", "200")))

for path in (BASE_DIR, CRAWLER_DIR, CRAWLERS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import setting  # noqa: E402
from crawlers.runner import (  # noqa: E402
    PLATFORMS,
    crawler_import_context,
    load_module,
    normalize_platforms,
    platform_collection,
    platform_options,
    run_platform,
)


UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

_engine = None
_engine_lock = threading.RLock()
_runtime_ready = False


def load_analyzer_class():
    if not ENGINE_FILE.exists():
        raise RuntimeError(f"没有找到多模态融合分析文件: {ENGINE_FILE}")

    spec = importlib.util.spec_from_file_location("local_multimodal_fusion", ENGINE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载多模态融合分析模块。")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    analyzer_cls = getattr(module, "MultimodalRiskFusion", None)
    if analyzer_cls is None:
        raise RuntimeError("多模态融合分析.py 中没有 MultimodalRiskFusion 类。")
    return analyzer_cls


def initialize_runtime():
    global _engine, _runtime_ready
    with _engine_lock:
        if _runtime_ready:
            return _engine

        if not FRONTEND_DIR.exists():
            raise RuntimeError(f"前端目录不存在: {FRONTEND_DIR}")
        if not (FRONTEND_DIR / "index.html").exists():
            raise RuntimeError(f"前端入口不存在: {FRONTEND_DIR / 'index.html'}")
        if not CRAWLER_DIR.exists():
            raise RuntimeError(f"爬虫目录不存在: {CRAWLER_DIR}")
        if not CRAWLERS_DIR.exists():
            raise RuntimeError(f"多平台爬虫目录不存在: {CRAWLERS_DIR}")

        client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
        try:
            client.admin.command("ping")
        finally:
            client.close()

        analyzer_cls = load_analyzer_class()
        _engine = analyzer_cls(base_dir=str(BASE_DIR), strict_init=True, load_word_vector_model=LOAD_WORD_VECTOR_MODEL)
        _runtime_ready = True
        return _engine


def get_risk_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            return initialize_runtime()
        return _engine


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage) -> Path:
    if not file_storage or not file_storage.filename:
        raise ValueError("请上传一张图片。")
    if not allowed_file(file_storage.filename):
        raise ValueError("图片格式仅支持 jpg、jpeg、png、bmp、webp。")

    safe_name = secure_filename(file_storage.filename)
    suffix = Path(safe_name).suffix.lower()
    target_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    file_storage.save(target_path)
    return target_path


def compact_result(result):
    final = result.get("final_multimodal_analysis", {})
    fusion = result.get("multimodal_feature_fusion", {})
    network = result.get("fusion_network_analysis", {})
    return {
        "input": result.get("input", {}),
        "runtime": result.get("runtime", {}),
        "text_feature_extraction": result.get("text_feature_extraction", {}),
        "image_feature_extraction": result.get("image_feature_extraction", {}),
        "ocr_text_feature_extraction": result.get("ocr_text_feature_extraction", {}),
        "multimodal_feature_fusion": fusion,
        "fusion_network_analysis": network,
        "final_multimodal_analysis": final,
        "summary": {
            "total_score": final.get("total_score"),
            "risk_level": final.get("risk_level"),
            "conclusion": final.get("conclusion"),
            "suggestion": final.get("suggestion"),
            "reasons": final.get("reasons", []),
            "modality_breakdown": fusion.get("modality_breakdown", {}),
            "cross_modal_features": fusion.get("cross_modal_features", {}),
            "network_output": network.get("output_layer", {}),
        },
    }


def public_error_message(exc: Exception) -> str:
    raw = str(exc)
    if "No module named" in raw:
        return f"本地模型依赖或模块缺失: {raw}"
    if "CUDA" in raw or "torch" in raw:
        return f"本地深度学习模型加载失败: {raw}"
    return raw or "分析失败，请稍后重试。"


def get_collection():
    client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
    return client, client[setting.MONGO_DATABASE][setting.MONGO_COLLECTION]


def get_platform_collection(platform, client=None):
    owned_client = client is None
    if client is None:
        client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
    collection = client[setting.MONGO_DATABASE][platform_collection(platform)]
    return client, collection, owned_client


def iter_platform_collections(platforms=None):
    client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
    try:
        for platform in normalize_platforms(platforms or PLATFORMS.keys()):
            yield platform, client[setting.MONGO_DATABASE][platform_collection(platform)]
    finally:
        client.close()


def doc_key(doc):
    platform = doc.get("platform") or "legacy"
    identifier = doc.get("id") or doc.get("note_id") or doc.get("_id")
    return f"{platform}:{identifier}"


def normalize_collection_indexes():
    dropped = 0
    for _platform, collection in iter_platform_collections():
        for index in collection.list_indexes():
            name = index.get("name")
            if name in {"note_id_1", "_key_1"}:
                try:
                    collection.drop_index(name)
                    dropped += 1
                except OperationFailure:
                    continue
                continue

            if name != "id_1":
                continue
            try:
                if index.get("key") == {"id": 1} and index.get("sparse"):
                    collection.drop_index(name)
                    dropped += 1
            except OperationFailure:
                continue
    return dropped


def backfill_missing_unique_fields():
    updated = 0
    for _platform, collection in iter_platform_collections():
        query = {
            "$or": [
                {"_key": {"$exists": False}},
                {"_key": None},
                {"_key": ""},
                {"note_id": {"$exists": False}},
                {"note_id": None},
                {"note_id": ""},
            ]
        }
        projection = {"platform": 1, "id": 1, "note_id": 1, "_key": 1}
        for doc in collection.find(query, projection).limit(1000):
            key = doc.get("_key") or doc_key(doc)
            updates = {}
            if not doc.get("_key"):
                updates["_key"] = key
            if not doc.get("note_id"):
                updates["note_id"] = key
            if not updates:
                continue
            try:
                collection.update_one({"_id": doc["_id"]}, {"$set": updates})
            except DuplicateKeyError:
                fallback_key = f"{doc.get('platform') or 'legacy'}:{doc['_id']}"
                fallback_updates = {}
                if not doc.get("_key"):
                    fallback_updates["_key"] = fallback_key
                if not doc.get("note_id"):
                    fallback_updates["note_id"] = fallback_key
                collection.update_one({"_id": doc["_id"]}, {"$set": fallback_updates})
            updated += 1
    return updated


def normalize_documents_collections(limit=2000):
    client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
    moved = 0
    try:
        db = client[setting.MONGO_DATABASE]
        for source_platform, source_collection in (
            (platform, db[platform_collection(platform)]) for platform in PLATFORMS
        ):
            query = {"platform": {"$exists": True, "$ne": source_platform}}
            for doc in source_collection.find(query).limit(limit):
                target_platform = doc.get("platform")
                if target_platform not in PLATFORMS:
                    continue
                target_collection = db[platform_collection(target_platform)]
                doc_id = doc.get("id")
                if not doc_id:
                    continue
                source_id = doc["_id"]
                doc.pop("_id", None)
                target_collection.update_one({"id": doc_id}, {"$set": doc}, upsert=True)
                source_collection.delete_one({"_id": source_id})
                moved += 1
        return moved
    finally:
        client.close()


def media_url(path):
    if not path:
        return ""
    if str(path).startswith(("http://", "https://")):
        return str(path)
    media_path = resolve_media_path(path)
    try:
        media_path = media_path.relative_to(CRAWLER_DIR)
    except ValueError:
        pass
    return "/media/" + quote(str(media_path).replace("\\", "/"), safe="/:")


def platform_label(value):
    return {
        "weibo": "微博",
        "douyin": "抖音",
        "tieba": "百度贴吧",
        "xhs": "小红书",
    }.get(value or "", value or "未知平台")


def resolve_media_path(path):
    if str(path).startswith(("http://", "https://")):
        return Path("")
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    for base_dir in (CRAWLER_DIR, CRAWLERS_DIR, BASE_DIR):
        resolved = base_dir / candidate
        if resolved.exists():
            return resolved
    return CRAWLER_DIR / candidate


def normalize_pic_path(pic):
    if isinstance(pic, dict):
        pic = pic.get("path") or pic.get("url") or pic.get("src") or ""
    return str(pic or "").strip()


def pick_first_image(item):
    for raw_path in item.get("pics", []) or []:
        path = normalize_pic_path(raw_path)
        if not path:
            continue
        candidate = resolve_media_path(path)
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in ALLOWED_EXTENSIONS:
            return candidate
    return None


def analyze_weibo_item(item):
    image_path = pick_first_image(item)
    if image_path is None:
        item["analysis_status"] = "no_image"
        item["analysis_error"] = "没有可用配图，已跳过多模态分析。"
        item["analysis_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return item

    result = get_risk_engine().analyze(post_text=item.get("text", ""), image_path=str(image_path))
    item["analysis"] = compact_result(result)
    item["analysis_status"] = "done"
    item["analysis_error"] = ""
    item["analysis_image"] = str(image_path)
    item["analysis_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return item


def analyze_unprocessed_documents(limit=20, log=None):
    client, collection = get_collection()
    processed = 0
    errors = []
    try:
        query = {
            "text": {"$type": "string", "$ne": ""},
            "pics.0": {"$exists": True},
            "$or": [{"analysis_status": {"$exists": False}}, {"analysis_status": {"$ne": "done"}}],
        }
        docs = list(collection.find(query).sort([("crawl_time", DESCENDING), ("_id", DESCENDING)]).limit(limit))
        for doc in docs:
            try:
                item = dict(doc)
                if log:
                    log(f"开始多模态分析 {item.get('platform_name', item.get('platform', ''))} {item.get('id', '')}。")
                with _engine_lock:
                    analyze_weibo_item(item)
                collection.update_one(
                    {"_id": doc["_id"]},
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
                processed += 1
            except Exception as exc:
                message = f"{doc.get('id', doc.get('_id'))}: {exc}"
                errors.append(message)
                if log:
                    log(f"多模态分析失败: {message}")
        return processed, errors
    finally:
        client.close()


def analyze_unprocessed_documents(limit=20, log=None):
    processed = 0
    errors = []
    platforms = list(PLATFORMS)
    per_platform_limit = max(1, (limit + len(platforms) - 1) // len(platforms))
    query = {
        "text": {"$type": "string", "$ne": ""},
        "pics.0": {"$exists": True},
        "$or": [{"analysis_status": {"$exists": False}}, {"analysis_status": {"$ne": "done"}}],
    }
    for platform, collection in iter_platform_collections(platforms):
        platform_query = {**query, "platform": platform}
        docs = list(collection.find(platform_query).sort([("crawl_time", DESCENDING), ("_id", DESCENDING)]).limit(per_platform_limit))
        for doc in docs:
            if processed >= limit:
                return processed, errors
            try:
                item = dict(doc)
                if log:
                    log(f"开始多模态分析 {item.get('platform_name', item.get('platform', ''))} {item.get('id', '')}。")
                with _engine_lock:
                    analyze_weibo_item(item)
                collection.update_one(
                    {"_id": doc["_id"]},
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
                processed += 1
            except Exception as exc:
                message = f"{doc.get('id', doc.get('_id'))}: {exc}"
                errors.append(message)
                if log:
                    log(f"多模态分析失败: {message}")
    return processed, errors


def serialize_doc(doc):
    doc["_id"] = str(doc.get("_id", ""))
    doc["id"] = str(doc.get("id") or doc.get("note_id") or doc["_id"])
    doc["platform"] = str(doc.get("platform") or "legacy")
    doc["platform_name"] = str(doc.get("platform_name") or platform_label(doc.get("platform")))
    doc["screen_name"] = str(doc.get("screen_name") or doc.get("nickname") or doc.get("author") or "未知用户")
    doc["text"] = str(doc.get("text") or doc.get("desc") or doc.get("title") or "")
    doc["created_at"] = str(doc.get("created_at") or doc.get("upload_time") or doc.get("crawl_time") or "")
    doc["source"] = str(doc.get("source") or doc["platform_name"])
    doc["keyword"] = str(doc.get("keyword") or doc.get("crawl_keyword") or "")
    if not isinstance(doc.get("matched_keywords"), list):
        doc["matched_keywords"] = [doc["keyword"]] if doc["keyword"] else []

    pics = []
    for raw_path in doc.get("pics", []) or []:
        path = normalize_pic_path(raw_path)
        if path:
            pics.append({"path": path, "url": media_url(path)})
    doc["pics"] = pics
    return doc


def analyzed_with_image_query():
    return {
        "text": {"$type": "string", "$ne": ""},
        "pics.0": {"$exists": True},
        "analysis_status": "done",
    }


def load_analyzed_items(limit):
    platforms = list(PLATFORMS)
    per_platform_limit = max(1, (limit + len(platforms) - 1) // len(platforms))
    query = analyzed_with_image_query()
    docs = []
    total = 0
    for platform, collection in iter_platform_collections(platforms):
        platform_query = {**query, "platform": platform}
        total += collection.count_documents(platform_query)
        for doc in collection.find(platform_query).sort([("crawl_time", DESCENDING), ("_id", DESCENDING)]).limit(per_platform_limit):
            doc["_collection_platform"] = platform
            docs.append(doc)
    docs.sort(key=lambda doc: (str(doc.get("crawl_time", "")), str(doc.get("_id", ""))), reverse=True)
    return docs[:limit], total


def find_analyzed_item(doc_id):
    query = analyzed_with_image_query()
    for platform, collection in iter_platform_collections():
        object_query = {**query, "platform": platform}
        try:
            object_query["_id"] = ObjectId(doc_id)
        except Exception:
            object_query["id"] = doc_id
        doc = collection.find_one(object_query)
        if doc:
            return doc
    return None


def run_startup_diagnostics(platforms=None):
    platforms = normalize_platforms(platforms or ["weibo", "xhs"])
    results = []
    for platform in platforms:
        if platform == "weibo":
            results.append(run_weibo_diagnostic())
        elif platform == "xhs":
            results.append(run_xhs_diagnostic())
    return results


def run_weibo_diagnostic():
    info = PLATFORMS["weibo"]
    with crawler_import_context(info["dir"]):
        setting_module = load_module("setting", info["dir"] / "setting.py")
        scrpy_module = load_module("diagnostic_weibo_scrpy", info["dir"] / info["entry"])

        crawl_source = getattr(setting_module, "CRAWL_KEYWORD_LIST", []) or setting_module.KEYWORD_LIST
        plain_keywords = scrpy_module.read_plain_keywords(crawl_source)
        encoded_keywords = scrpy_module.read_keywords(crawl_source)
        if not encoded_keywords:
            return {
                "platform": "weibo",
                "ok": False,
                "summary": "no keywords configured",
            }

        keyword = plain_keywords[0] if plain_keywords else ""
        encoded_keyword = encoded_keywords[0]
        start_date, end_date = scrpy_module.get_date_range()
        url = scrpy_module.build_url(encoded_keyword, 1, start_date, end_date)
        session = requests.Session()
        session.trust_env = bool(getattr(setting_module, "TRUST_ENV_PROXY", False))
        session.headers.update(setting_module.DEFAULT_REQUEST_HEADERS)
        try:
            page_text = scrpy_module.fetch(session, url)
            items = list(scrpy_module.parse_weibos(page_text, encoded_keyword))
            summary = scrpy_module.summarize_search_page(page_text)
            days = int(getattr(setting_module, "RECENT_DAYS", 60) or 60)
            return {
                "platform": "weibo",
                "ok": bool(items),
                "summary": f"keyword={keyword or '-'}; days={days}; parsed={len(items)}; {summary}",
            }
        except Exception as exc:
            return {
                "platform": "weibo",
                "ok": False,
                "summary": f"keyword={keyword or '-'}; error={exc}",
            }


def run_xhs_diagnostic():
    info = PLATFORMS["xhs"]
    with crawler_import_context(info["dir"]):
        setting_module = load_module("setting", info["dir"] / "setting.py")
        main_module = load_module("diagnostic_xhs_main", info["dir"] / info["entry"])

        keywords = getattr(setting_module, "KEYWORD_LIST", []) or []
        keyword = str(keywords[0]).strip() if keywords else ""
        if not keyword:
            return {
                "platform": "xhs",
                "ok": False,
                "summary": "no keywords configured",
            }

        try:
            api = main_module.XHS_Apis()
            success, msg, res_json = api.search_note(
                keyword,
                setting_module.COOKIES,
                page=1,
                sort_type_choice=getattr(setting_module, "SORT_TYPE", 0),
                note_type=getattr(setting_module, "NOTE_TYPE", 0),
                note_time=getattr(setting_module, "NOTE_TIME", 0),
                note_range=getattr(setting_module, "NOTE_RANGE", 0),
                proxies=getattr(setting_module, "PROXY", None),
            )
            data = (res_json or {}).get("data") or {}
            items = data.get("items", []) if isinstance(data, dict) else []
            body_summary = msg or ""
            return {
                "platform": "xhs",
                "ok": bool(success and items),
                "summary": f"keyword={keyword}; success={success}; items={len(items)}; msg={body_summary}",
            }
        except Exception as exc:
            return {
                "platform": "xhs",
                "ok": False,
                "summary": f"keyword={keyword}; error={exc}",
            }


class WebCrawlController:
    def __init__(self):
        self.paused = False
        self.stopped = False
        self._condition = threading.Condition()

    def poll(self):
        return None

    def wait_if_paused(self):
        with self._condition:
            while self.paused and not self.stopped:
                self._condition.wait(timeout=0.5)

    def pause(self):
        with self._condition:
            self.paused = True
            self._condition.notify_all()

    def resume(self):
        with self._condition:
            self.paused = False
            self._condition.notify_all()


class CrawlTask:
    def __init__(self):
        self.lock = threading.RLock()
        self.thread = None
        self.controller = None
        self.running = False
        self.logs = []
        self.last_result = None
        self.current_stats = {"inserted": 0, "skipped": 0, "unmatched": 0, "discarded": 0}
        self.last_error = ""
        self.selected_platforms = ["weibo"]
        self.platform_item_limit = CRAWL_TOTAL_TARGET
        self.current_platform = ""
        self.platform_results = {}

    def add_log(self, message):
        line = f"{datetime.now().strftime('%H:%M:%S')} {message}"
        with self.lock:
            self.logs.append(line)
            self.logs = self.logs[-160:]

    def start_or_resume(self, selected_platforms=None):
        with self.lock:
            if self.running and self.controller:
                self.controller.resume()
                self.add_log("已继续爬取。")
                return "resumed"
            self.selected_platforms = normalize_platforms(selected_platforms)
            self.platform_item_limit = max(1, (CRAWL_TOTAL_TARGET + len(self.selected_platforms) - 1) // len(self.selected_platforms))
            self.current_platform = ""
            self.platform_results = {}
            self.controller = WebCrawlController()
            self.running = True
            self.last_error = ""
            self.last_result = None
            self.current_stats = {"inserted": 0, "skipped": 0, "unmatched": 0, "discarded": 0}
            self.logs = []
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            return "started"

    def pause(self):
        with self.lock:
            if not self.running or not self.controller:
                return False
            self.controller.pause()
            self.add_log("已请求暂停，当前请求处理完后会停住。")
            return True

    def _run(self):
        try:
            for diagnostic in run_startup_diagnostics(self.selected_platforms):
                label = platform_label(diagnostic.get("platform"))
                status = "通过" if diagnostic.get("ok") else "失败"
                self.add_log(f"[{label}自检] {status}: {diagnostic.get('summary', '')}")
            dropped_indexes = normalize_collection_indexes()
            if dropped_indexes:
                self.add_log(f"已移除 {dropped_indexes} 个历史非主去重索引。")
            fixed_keys = backfill_missing_unique_fields()
            if fixed_keys:
                self.add_log(f"已修复 {fixed_keys} 条历史数据的唯一键。")
            moved_docs = normalize_documents_collections()
            if moved_docs:
                self.add_log(f"已将 {moved_docs} 条错集合数据迁移回对应平台集合。")
            threads = []
            for platform in self.selected_platforms:
                thread = threading.Thread(target=self._run_platform_worker, args=(platform,), daemon=True)
                threads.append(thread)
                thread.start()

            self.add_log(f"已并行启动 {len(threads)} 个平台爬虫。")
            while any(thread.is_alive() for thread in threads):
                if self.controller and self.controller.stopped:
                    break
                processed, errors = analyze_unprocessed_documents(limit=20, log=self.add_log)
                if processed or errors:
                    self.add_log(f"周期补分析完成，处理 {processed} 条，错误 {len(errors)} 条。")
                for thread in threads:
                    thread.join(timeout=5)

            for thread in threads:
                thread.join()

            processed, errors = analyze_unprocessed_documents(limit=200, log=self.add_log)
            self.add_log(f"收尾补分析完成，处理 {processed} 条，错误 {len(errors)} 条。")
            result = self.aggregate_platform_results()
            with self.lock:
                self.last_result = result
                self.current_stats = dict(result)
        except Exception as exc:
            with self.lock:
                self.last_error = str(exc)
            self.add_log(f"爬取异常: {exc}")
        finally:
            with self.lock:
                self.running = False
                if self.controller:
                    self.controller.resume()
                self.current_platform = ""

    def _run_platform_worker(self, platform):
        label = PLATFORMS[platform]["label"]
        try:
            self.add_log(f"开始爬取 {label}。")
            platform_result = run_platform(
                platform,
                controller=self.controller,
                log=lambda message, label=label: self.add_log(f"[{label}] {message}"),
                progress=lambda stats, platform=platform: self.update_platform_stats(platform, stats),
                item_callback=self._analyze_new_item,
                mongo_uri=setting.MONGO_URI,
                mongo_database=setting.MONGO_DATABASE,
                mongo_collection=platform_collection(platform),
                max_items=self.platform_item_limit,
            )
            self.update_platform_stats(platform, platform_result or {})
            self.add_log(f"{label} 爬取完成。")
        except Exception as exc:
            with self.lock:
                self.last_error = str(exc)
            self.add_log(f"{label} 爬取异常: {exc}")

    def _analyze_new_item(self, item):
        self.add_log(f"开始多模态分析 {item.get('platform_name', item.get('platform', '平台'))} {item.get('id', '')}。")
        with _engine_lock:
            analyze_weibo_item(item)
        status = item.get("analysis_status")
        score = item.get("analysis", {}).get("summary", {}).get("total_score")
        if status == "done":
            self.add_log(f"分析完成，综合风险分 {score}。")
        else:
            self.add_log(item.get("analysis_error", "分析跳过。"))

    def update_stats(self, stats):
        with self.lock:
            self.current_stats = dict(stats)

    def update_platform_stats(self, platform, stats):
        with self.lock:
            self.platform_results[platform] = dict(stats)
            self.current_stats = self.aggregate_platform_results()

    def aggregate_platform_results(self):
        aggregate = {"inserted": 0, "skipped": 0, "unmatched": 0, "discarded": 0}
        for platform_stats in self.platform_results.values():
            for key in aggregate:
                aggregate[key] += int(platform_stats.get(key, 0))
        return aggregate

    def status(self):
        with self.lock:
            return {
                "running": self.running,
                "paused": bool(self.controller and self.controller.paused),
                "selected_platforms": list(self.selected_platforms),
                "platform_item_limit": self.platform_item_limit,
                "current_platform": self.current_platform,
                "platform_results": dict(self.platform_results),
                "platform_options": platform_options(),
                "last_result": self.last_result,
                "current_stats": dict(self.current_stats),
                "last_error": self.last_error,
                "logs": list(self.logs),
            }


task = CrawlTask()


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/report")
def report_page():
    return send_from_directory(FRONTEND_DIR, "report.html")


@app.get("/health")
def health():
    try:
        engine = get_risk_engine()
        return jsonify(
            {
                "success": True,
                "status": "running",
                "model_ready": _runtime_ready,
                "engine": "MultimodalRiskFusion",
                "component_status": getattr(engine, "component_status", {}),
                "init_errors": getattr(engine, "init_errors", []),
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "status": "error", "error": public_error_message(exc)}), 500


@app.post("/analyze")
def analyze():
    try:
        post_text = request.form.get("post_text", "").strip()
        image = request.files.get("image")

        if not post_text:
            return jsonify({"success": False, "error": "请输入待检测文本。"}), 400

        image_path = save_upload(image)
        with _engine_lock:
            result = get_risk_engine().analyze(post_text=post_text, image_path=str(image_path))
        return jsonify({"success": True, "data": compact_result(result)})
    except Exception as exc:
        if isinstance(exc, ValueError):
            return jsonify({"success": False, "error": public_error_message(exc)}), 400
        raise


@app.post("/api/crawl/start")
def start_crawl():
    payload = request.get_json(silent=True) or {}
    action = task.start_or_resume(payload.get("platforms"))
    return jsonify({"ok": True, "action": action, "status": task.status()})


@app.post("/api/crawl/pause")
def pause_crawl():
    ok = task.pause()
    return jsonify({"ok": ok, "status": task.status()})


@app.get("/api/crawl/status")
def crawl_status():
    return jsonify(task.status())


@app.get("/api/items")
@app.get("/api/weibos")
def list_weibos():
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 300))
        docs, total = load_analyzed_items(limit)
        analyzed = total
        return jsonify(
            {
                "ok": True,
                "total": total,
                "analyzed": analyzed,
                "items": [serialize_doc(doc) for doc in docs],
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "total": 0, "analyzed": 0, "items": [], "error": str(exc)}), 500


@app.get("/api/items/<doc_id>")
@app.get("/api/weibos/<doc_id>")
def get_weibo(doc_id):
    try:
        doc = find_analyzed_item(doc_id)
        if not doc:
            return jsonify({"ok": False, "error": "没有找到已分析且带图片的平台内容。"}), 404
        return jsonify({"ok": True, "item": serialize_doc(doc)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/analyze/unprocessed")
def analyze_unprocessed():
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
        processed, errors = analyze_unprocessed_documents(limit=limit)
        return jsonify({"ok": True, "processed": processed, "errors": errors})
    except Exception as exc:
        return jsonify({"ok": False, "processed": 0, "errors": [str(exc)]}), 500


@app.get("/media/<path:file_path>")
def serve_media(file_path):
    path = resolve_media_path(unquote(file_path))
    if not path.exists() or not path.is_file():
        return jsonify({"ok": False, "error": "file not found"}), 404
    return send_file(path)


if __name__ == "__main__":
    initialize_runtime()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
