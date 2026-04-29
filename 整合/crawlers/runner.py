# -*- coding: utf-8 -*-
import importlib.util
import inspect
import sys
import threading
from contextlib import contextmanager
from pathlib import Path


CRAWLERS_DIR = Path(__file__).resolve().parent
_IMPORT_LOCK = threading.RLock()

PLATFORMS = {
    "weibo": {"label": "微博", "dir": CRAWLERS_DIR / "weibo", "entry": "scrpy.py", "collection": "test_weibo"},
    "douyin": {"label": "抖音", "dir": CRAWLERS_DIR / "douyin", "entry": "scrpy.py", "collection": "test_douyin"},
    "tieba": {"label": "百度贴吧", "dir": CRAWLERS_DIR / "tieba", "entry": "scrpy.py", "collection": "test_baidu"},
    "xhs": {"label": "小红书", "dir": CRAWLERS_DIR / "xhs", "entry": "main.py", "collection": "test_xhs"},
}

MODULE_PREFIXES = ("apis", "xhs_utils")
MODULE_NAMES = {"setting", "scrpy", "main"}


def platform_options():
    return [{"id": key, "label": value["label"]} for key, value in PLATFORMS.items()]


def normalize_platforms(values):
    if not values:
        return ["weibo"]
    selected = []
    for value in values:
        key = str(value).strip()
        if key in PLATFORMS and key not in selected:
            selected.append(key)
    return selected or ["weibo"]


def platform_collection(platform):
    return PLATFORMS[platform]["collection"]


def purge_crawler_modules():
    for name in list(sys.modules):
        if name in MODULE_NAMES or any(name == prefix or name.startswith(prefix + ".") for prefix in MODULE_PREFIXES):
            sys.modules.pop(name, None)


@contextmanager
def crawler_import_context(crawler_dir):
    purge_crawler_modules()
    crawler_path = str(crawler_dir)
    sys.path.insert(0, crawler_path)
    try:
        yield
    finally:
        if crawler_path in sys.path:
            sys.path.remove(crawler_path)
        purge_crawler_modules()


def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载爬虫模块: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_platform(platform, *, controller, log, progress, item_callback, mongo_uri, mongo_database, mongo_collection=None, max_items=None):
    info = PLATFORMS[platform]
    crawler_dir = info["dir"]
    entry_file = crawler_dir / info["entry"]
    if not entry_file.exists():
        raise RuntimeError(f"{info['label']} 爬虫入口不存在: {entry_file}")

    with _IMPORT_LOCK:
        with crawler_import_context(crawler_dir):
            setting = load_module("setting", crawler_dir / "setting.py")
            setting.MONGO_URI = mongo_uri
            setting.MONGO_DATABASE = mongo_database
            setting.MONGO_COLLECTION = mongo_collection or info["collection"]
            if max_items is not None:
                setting.MAX_ITEMS_PER_RUN = max(0, int(max_items))

            module = load_module(f"integrated_{platform}_crawler", entry_file)
            run_crawler = getattr(module, "run_crawler", None)
            if run_crawler is None:
                raise RuntimeError(f"{info['label']} 爬虫没有 run_crawler 入口")

            kwargs = {"controller": controller, "log": log, "progress": progress}
            if "item_callback" in inspect.signature(run_crawler).parameters:
                kwargs["item_callback"] = item_callback

    return run_crawler(**kwargs)
