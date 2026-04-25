# -*- coding: utf-8 -*-
import importlib.util
import sys
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, send_from_directory
from bson import ObjectId
from pymongo import DESCENDING, MongoClient
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "backend" / "uploads"
ENGINE_FILE = BASE_DIR / "多模态融合分析.py"
CRAWLER_DIR = BASE_DIR / "crawler"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

for path in (BASE_DIR, CRAWLER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import scrpy  # noqa: E402
import setting  # noqa: E402


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

        client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
        try:
            client.admin.command("ping")
        finally:
            client.close()

        analyzer_cls = load_analyzer_class()
        _engine = analyzer_cls(base_dir=str(BASE_DIR), strict_init=True)
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


def media_url(path):
    if not path:
        return ""
    return "/media/" + str(path).replace("\\", "/")


def pick_first_image(item):
    for path in item.get("pics", []) or []:
        candidate = Path(path)
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


def serialize_doc(doc):
    doc["_id"] = str(doc.get("_id", ""))
    doc["pics"] = [{"path": path, "url": media_url(path)} for path in doc.get("pics", [])]
    return doc


def analyzed_with_image_query():
    return {
        "analysis_status": "done",
        "text": {"$type": "string", "$ne": ""},
        "pics.0": {"$exists": True},
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

    def add_log(self, message):
        line = f"{datetime.now().strftime('%H:%M:%S')} {message}"
        with self.lock:
            self.logs.append(line)
            self.logs = self.logs[-160:]

    def start_or_resume(self):
        with self.lock:
            if self.running and self.controller:
                self.controller.resume()
                self.add_log("已继续爬取。")
                return "resumed"
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
            result = scrpy.run_crawler(
                controller=self.controller,
                log=self.add_log,
                progress=self.update_stats,
                item_callback=self._analyze_new_item,
            )
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

    def _analyze_new_item(self, item):
        self.add_log(f"开始多模态分析微博 {item.get('id', '')}。")
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

    def status(self):
        with self.lock:
            return {
                "running": self.running,
                "paused": bool(self.controller and self.controller.paused),
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
    action = task.start_or_resume()
    return jsonify({"ok": True, "action": action, "status": task.status()})


@app.post("/api/crawl/pause")
def pause_crawl():
    ok = task.pause()
    return jsonify({"ok": ok, "status": task.status()})


@app.get("/api/crawl/status")
def crawl_status():
    return jsonify(task.status())


@app.get("/api/weibos")
def list_weibos():
    client, collection = get_collection()
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 300))
        query = analyzed_with_image_query()
        docs = list(collection.find(query).sort("crawl_time", DESCENDING).limit(limit))
        total = collection.count_documents(query)
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
    finally:
        client.close()


@app.get("/api/weibos/<doc_id>")
def get_weibo(doc_id):
    client, collection = get_collection()
    try:
        query = analyzed_with_image_query()
        object_query = dict(query)
        try:
            object_query["_id"] = ObjectId(doc_id)
        except Exception:
            object_query["id"] = doc_id
        doc = collection.find_one(object_query)
        if not doc:
            return jsonify({"ok": False, "error": "没有找到已分析且带图片的微博。"}), 404
        return jsonify({"ok": True, "item": serialize_doc(doc)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        client.close()


@app.post("/api/analyze/unprocessed")
def analyze_unprocessed():
    client, collection = get_collection()
    processed = 0
    errors = []
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
        query = {
            "text": {"$type": "string", "$ne": ""},
            "pics.0": {"$exists": True},
            "$or": [{"analysis_status": {"$exists": False}}, {"analysis_status": {"$ne": "done"}}],
        }
        docs = list(collection.find(query).sort("crawl_time", DESCENDING).limit(limit))
        for doc in docs:
            try:
                item = dict(doc)
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
                errors.append(f"{doc.get('id', doc.get('_id'))}: {exc}")
        return jsonify({"ok": True, "processed": processed, "errors": errors})
    except Exception as exc:
        return jsonify({"ok": False, "processed": processed, "errors": errors + [str(exc)]}), 500
    finally:
        client.close()


@app.get("/media/<path:file_path>")
def serve_media(file_path):
    path = Path(file_path)
    if not path.is_absolute():
        path = CRAWLER_DIR / path
    if not path.exists() or not path.is_file():
        return jsonify({"ok": False, "error": "file not found"}), 404
    return send_file(path)


if __name__ == "__main__":
    initialize_runtime()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
