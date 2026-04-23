# -*- coding: utf-8 -*-
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, send_file
from pymongo import MongoClient, DESCENDING

import scrpy
import setting


app = Flask(__name__)
PROJECT_DIR = Path(__file__).resolve().parent


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

    def stop(self):
        with self._condition:
            self.stopped = True
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
            self.logs = self.logs[-120:]

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
            result = scrpy.run_crawler(controller=self.controller, log=self.add_log, progress=self.update_stats)
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


def get_collection():
    client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
    return client, client[setting.MONGO_DATABASE][setting.MONGO_COLLECTION]


def media_url(path):
    if not path:
        return ""
    return "/media/" + str(path).replace("\\", "/")


def serialize_doc(doc):
    doc["_id"] = str(doc.get("_id", ""))
    doc["pics"] = [{"path": path, "url": media_url(path)} for path in doc.get("pics", [])]
    return doc


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/crawl/start", methods=["POST"])
def start_crawl():
    action = task.start_or_resume()
    return jsonify({"ok": True, "action": action, "status": task.status()})


@app.route("/api/crawl/pause", methods=["POST"])
def pause_crawl():
    ok = task.pause()
    return jsonify({"ok": ok, "status": task.status()})


@app.route("/api/crawl/status")
def crawl_status():
    return jsonify(task.status())


@app.route("/api/weibos")
def list_weibos():
    client, collection = get_collection()
    try:
        docs = list(collection.find().sort("crawl_time", DESCENDING).limit(100))
        total = collection.count_documents({})
        return jsonify({"ok": True, "total": total, "items": [serialize_doc(doc) for doc in docs]})
    except Exception as exc:
        return jsonify({"ok": False, "total": 0, "items": [], "error": str(exc)}), 500
    finally:
        client.close()


@app.route("/media/<path:file_path>")
def serve_media(file_path):
    path = Path(file_path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    if not path.exists() or not path.is_file():
        return jsonify({"ok": False, "error": "file not found"}), 404
    return send_file(path)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
