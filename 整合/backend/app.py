# -*- coding: utf-8 -*-
import copy
import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
PLATFORM_SETTINGS_FILE = BASE_DIR / "backend" / "platform_settings.json"
WATCHLIST_FILE = BASE_DIR / "backend" / "watchlist.json"
COLLECTION_SOURCES_FILE = BASE_DIR / "backend" / "collection_sources.json"
USERS_FILE = BASE_DIR / "backend" / "users.json"
USER_ACTIVITY_FILE = BASE_DIR / "backend" / "user_activity.json"
RUNTIME_CONFIG_FILE = BASE_DIR / "backend" / "runtime_config.json"
CRAWLER_DIR = BASE_DIR / "crawler"
CRAWLERS_DIR = BASE_DIR / "crawlers"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LOAD_WORD_VECTOR_MODEL_ENV = os.getenv("LOAD_WORD_VECTOR_MODEL")
LOAD_WORD_VECTOR_MODEL = (
    None
    if LOAD_WORD_VECTOR_MODEL_ENV is None
    else LOAD_WORD_VECTOR_MODEL_ENV.strip().lower() not in {"0", "false", "no", "off"}
)
STRICT_RUNTIME_ENV = os.getenv("STRICT_RUNTIME", "0")
STRICT_RUNTIME = STRICT_RUNTIME_ENV.strip().lower() in {"1", "true", "yes", "on"}
CRAWL_TOTAL_TARGET = max(1, int(os.getenv("CRAWL_TOTAL_TARGET", "200")))

KNOWN_EXTRA_PLATFORMS = {
    "bilibili": {"label": "Bilibili", "description": "视频社区，待接入爬虫"},
    "kuaishou": {"label": "快手", "description": "短视频平台，待接入爬虫"},
    "zhihu": {"label": "知乎", "description": "问答社区，待接入爬虫"},
    "xueqiu": {"label": "雪球", "description": "投资社区，待接入爬虫"},
    "eastmoney": {"label": "东方财富", "description": "财经社区，待接入爬虫"},
    "telegram": {"label": "Telegram", "description": "社群频道，待接入爬虫"},
}

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
_platform_defaults_cache = {}
_startup_analysis_started = False
_startup_analysis_lock = threading.Lock()


def _read_text_lines(value):
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _safe_int(value, default, minimum=0, maximum=None):
    try:
        result = int(value)
    except Exception:
        result = default
    result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_runtime_config():
    defaults = {
        "analysis_engine_file": "多模态融合分析_API.py",
        "analysis_max_workers": None,
        "auto_analyze_crawled_items": True,
        "load_word_vector_model": True,
        "strict_runtime": False,
        "crawl_total_target": 200,
        "platform_cookies": {},
    }
    if not RUNTIME_CONFIG_FILE.exists():
        return defaults
    try:
        data = json.loads(RUNTIME_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    if not isinstance(data, dict):
        return defaults
    cookies = data.get("platform_cookies")
    return {
        "analysis_engine_file": str(data.get("analysis_engine_file") or defaults["analysis_engine_file"]).strip(),
        "analysis_max_workers": data.get("analysis_max_workers"),
        "auto_analyze_crawled_items": _safe_bool(
            data.get("auto_analyze_crawled_items"),
            defaults["auto_analyze_crawled_items"],
        ),
        "load_word_vector_model": _safe_bool(data.get("load_word_vector_model"), defaults["load_word_vector_model"]),
        "strict_runtime": _safe_bool(data.get("strict_runtime"), defaults["strict_runtime"]),
        "crawl_total_target": _safe_int(data.get("crawl_total_target"), defaults["crawl_total_target"], minimum=1, maximum=10000),
        "platform_cookies": cookies if isinstance(cookies, dict) else {},
    }


def resolve_runtime_path(value, default_name):
    raw = str(value or default_name).strip() or default_name
    candidate = Path(os.getenv("RISK_ENGINE_FILE") or raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (BASE_DIR / candidate).resolve()


RUNTIME_CONFIG = load_runtime_config()
ENGINE_FILE = resolve_runtime_path(RUNTIME_CONFIG.get("analysis_engine_file"), "多模态融合分析_API.py")
DEFAULT_ANALYSIS_WORKERS = 4 if ENGINE_FILE.name.endswith("_API.py") else 1
ANALYSIS_MAX_WORKERS = max(
    1,
    int(os.getenv("ANALYSIS_MAX_WORKERS") or RUNTIME_CONFIG.get("analysis_max_workers") or DEFAULT_ANALYSIS_WORKERS),
)
AUTO_ANALYZE_CRAWLED_ITEMS = _safe_bool(
    os.getenv("AUTO_ANALYZE_CRAWLED_ITEMS"),
    bool(RUNTIME_CONFIG.get("auto_analyze_crawled_items", True)),
)
LOAD_WORD_VECTOR_MODEL = _safe_bool(
    os.getenv("LOAD_WORD_VECTOR_MODEL"),
    bool(RUNTIME_CONFIG.get("load_word_vector_model", True)),
)
STRICT_RUNTIME = _safe_bool(
    os.getenv("STRICT_RUNTIME"),
    bool(RUNTIME_CONFIG.get("strict_runtime", False)),
)
CRAWL_TOTAL_TARGET = _safe_int(
    os.getenv("CRAWL_TOTAL_TARGET") or RUNTIME_CONFIG.get("crawl_total_target"),
    200,
    minimum=1,
    maximum=10000,
)


def runtime_cookie(platform, default=""):
    cookies = RUNTIME_CONFIG.get("platform_cookies", {})
    value = cookies.get(platform) if isinstance(cookies, dict) else None
    value = str(value or "").strip()
    return value if value else default


def save_runtime_config(data):
    RUNTIME_CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def runtime_effective_config():
    return {
        "analysis_engine_file": str(RUNTIME_CONFIG.get("analysis_engine_file") or ENGINE_FILE.name),
        "analysis_engine_path": str(ENGINE_FILE),
        "analysis_max_workers": ANALYSIS_MAX_WORKERS,
        "auto_analyze_crawled_items": AUTO_ANALYZE_CRAWLED_ITEMS,
        "load_word_vector_model": LOAD_WORD_VECTOR_MODEL,
        "strict_runtime": STRICT_RUNTIME,
        "crawl_total_target": CRAWL_TOTAL_TARGET,
        "platform_cookies": {
            platform: runtime_cookie(platform, "")
            for platform in PLATFORMS
        },
    }


def available_engine_files():
    names = []
    for path in sorted(BASE_DIR.glob("多模态融合分析*.py")):
        if path.name not in names:
            names.append(path.name)
    current = ENGINE_FILE.name
    if current and current not in names:
        names.insert(0, current)
    return names


def apply_runtime_config(data, reset_engine=False):
    global RUNTIME_CONFIG, ENGINE_FILE, DEFAULT_ANALYSIS_WORKERS, ANALYSIS_MAX_WORKERS
    global AUTO_ANALYZE_CRAWLED_ITEMS, LOAD_WORD_VECTOR_MODEL, STRICT_RUNTIME, CRAWL_TOTAL_TARGET
    global _engine, _runtime_ready, _startup_analysis_started

    previous_engine_file = ENGINE_FILE
    previous_load_word_vector = LOAD_WORD_VECTOR_MODEL
    previous_strict_runtime = STRICT_RUNTIME

    RUNTIME_CONFIG = data
    ENGINE_FILE = resolve_runtime_path(data.get("analysis_engine_file"), "多模态融合分析_API.py")
    DEFAULT_ANALYSIS_WORKERS = 4 if ENGINE_FILE.name.endswith("_API.py") else 1
    ANALYSIS_MAX_WORKERS = max(1, _safe_int(data.get("analysis_max_workers"), DEFAULT_ANALYSIS_WORKERS, minimum=1, maximum=64))
    AUTO_ANALYZE_CRAWLED_ITEMS = _safe_bool(data.get("auto_analyze_crawled_items"), True)
    LOAD_WORD_VECTOR_MODEL = _safe_bool(data.get("load_word_vector_model"), True)
    STRICT_RUNTIME = _safe_bool(data.get("strict_runtime"), False)
    CRAWL_TOTAL_TARGET = _safe_int(data.get("crawl_total_target"), 200, minimum=1, maximum=10000)

    should_reset_engine = (
        reset_engine
        or previous_engine_file != ENGINE_FILE
        or previous_load_word_vector != LOAD_WORD_VECTOR_MODEL
        or previous_strict_runtime != STRICT_RUNTIME
    )
    if should_reset_engine:
        with _engine_lock:
            _engine = None
            _runtime_ready = False
            _startup_analysis_started = False


def sanitize_runtime_config_payload(payload):
    payload = payload or {}
    current = runtime_effective_config()
    engine_file = str(payload.get("analysis_engine_file") or current["analysis_engine_file"]).strip()
    if not engine_file:
        engine_file = "多模态融合分析_API.py"
    platform_cookies = payload.get("platform_cookies") if isinstance(payload.get("platform_cookies"), dict) else {}
    return {
        "analysis_engine_file": engine_file,
        "analysis_max_workers": _safe_int(payload.get("analysis_max_workers"), current["analysis_max_workers"], minimum=1, maximum=64),
        "auto_analyze_crawled_items": _safe_bool(payload.get("auto_analyze_crawled_items"), current["auto_analyze_crawled_items"]),
        "load_word_vector_model": _safe_bool(payload.get("load_word_vector_model"), current["load_word_vector_model"]),
        "strict_runtime": _safe_bool(payload.get("strict_runtime"), current["strict_runtime"]),
        "crawl_total_target": _safe_int(payload.get("crawl_total_target"), current["crawl_total_target"], minimum=1, maximum=10000),
        "platform_cookies": {
            platform: str(platform_cookies.get(platform) or "").strip()
            for platform in PLATFORMS
        },
    }


def load_platform_settings_store():
    if not PLATFORM_SETTINGS_FILE.exists():
        return {"added_platforms": [], "platforms": {}, "custom_platforms": {}}
    try:
        data = json.loads(PLATFORM_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"added_platforms": [], "platforms": {}, "custom_platforms": {}}
    return {
        "added_platforms": [str(item).strip() for item in data.get("added_platforms", []) if str(item).strip()],
        "platforms": data.get("platforms", {}) if isinstance(data.get("platforms"), dict) else {},
        "custom_platforms": data.get("custom_platforms", {}) if isinstance(data.get("custom_platforms"), dict) else {},
    }


def save_platform_settings_store(data):
    PLATFORM_SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_watchlist_store():
    if not WATCHLIST_FILE.exists():
        return []
    try:
        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    items = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        doc_id = str(entry.get("id", "")).strip()
        if not doc_id:
            continue
        items.append(
            {
                "id": doc_id,
                "owner": str(entry.get("owner") or "business-user").strip(),
                "added_at": str(entry.get("added_at", "")).strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def save_watchlist_store(items):
    WATCHLIST_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def request_role():
    role = (request.headers.get("X-User-Role") or request.args.get("role") or "user").strip().lower()
    return "admin" if role == "admin" else "user"


def request_user():
    name = (request.headers.get("X-User-Name") or request.args.get("user") or "").strip()
    return name or ("admin" if request_role() == "admin" else "business-user")


def require_admin():
    if request_role() != "admin":
        return jsonify({"ok": False, "error": "当前角色无权访问后台管理功能。"}), 403
    return None


def default_users():
    return [
        {"username": "user", "password": "user123", "role": "user", "display_name": "普通用户", "phone": "", "department": "舆情监测组", "enabled": True},
        {"username": "admin", "password": "admin123", "role": "admin", "display_name": "管理员", "phone": "", "department": "系统维护组", "enabled": True},
    ]


def load_users_store():
    if not USERS_FILE.exists():
        save_users_store(default_users())
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = default_users()
    if not isinstance(data, list):
        data = default_users()
    normalized = []
    changed = False
    for user in data:
        if not isinstance(user, dict) or not str(user.get("username") or "").strip():
            changed = True
            continue
        next_user = dict(user)
        next_user.setdefault("display_name", next_user.get("username", ""))
        next_user.setdefault("role", "user")
        next_user.setdefault("phone", "")
        next_user.setdefault("department", "")
        next_user.setdefault("enabled", True)
        normalized.append(next_user)
        changed = changed or next_user != user
    if changed:
        save_users_store(normalized)
    data = normalized
    return data


def save_users_store(users):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def load_user_activity_store():
    if not USER_ACTIVITY_FILE.exists():
        return []
    try:
        data = json.loads(USER_ACTIVITY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_user_activity_store(items):
    USER_ACTIVITY_FILE.write_text(json.dumps(items[:500], ensure_ascii=False, indent=2), encoding="utf-8")


def log_user_activity(action, detail="", username=None, role=None):
    try:
        items = load_user_activity_store()
        items.insert(
            0,
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "username": username or request_user(),
                "role": role or request_role(),
                "action": action,
                "detail": detail,
            },
        )
        save_user_activity_store(items)
    except Exception:
        pass


def find_user(username):
    username = str(username or "").strip()
    return next((user for user in load_users_store() if user.get("username") == username), None)


def public_user(user):
    return {
        "username": user.get("username", ""),
        "role": "admin" if user.get("role") == "admin" else "user",
        "display_name": user.get("display_name") or user.get("username", ""),
        "phone": user.get("phone", ""),
        "department": user.get("department", ""),
        "enabled": bool(user.get("enabled", True)),
    }


def sanitize_admin_user_payload(payload, existing=None):
    username = str(payload.get("username") or (existing or {}).get("username") or "").strip()
    display_name = str(payload.get("display_name") or payload.get("displayName") or username).strip()
    role = "admin" if str(payload.get("role") or (existing or {}).get("role") or "user").strip() == "admin" else "user"
    return {
        "username": username,
        "display_name": display_name or username,
        "role": role,
        "phone": str(payload.get("phone") or (existing or {}).get("phone") or "").strip(),
        "department": str(payload.get("department") or (existing or {}).get("department") or "").strip(),
        "enabled": _safe_bool(payload.get("enabled"), bool((existing or {}).get("enabled", True))),
        "password": str(payload.get("password") or (existing or {}).get("password") or "").strip(),
    }


ROLE_PERMISSION_PRESETS = {
    "user": {
        "label": "普通用户",
        "permissions": ["查看监测首页", "舆情监测与检索", "查看风险分析", "查看舆情详情报告", "个人追踪"],
        "denied": ["删除数据", "修改采集平台", "管理账号", "查看运行日志", "维护系统配置"],
        "scope": "只能查看业务结果和提交采集申请，不能进入后台管理功能。",
    },
    "admin": {
        "label": "管理员",
        "permissions": ["全部前台功能", "采集源与平台管理", "采集任务管理", "运行日志查看", "账号管理", "用户权限与操作范围管理", "系统设置维护"],
        "denied": [],
        "scope": "可进入后台管理端，维护平台、任务、规则、模型、日志、账号与系统配置。",
    },
}


def build_user_management_payload():
    users = [public_user(user) for user in load_users_store()]
    departments = {}
    roles = {}
    for user in users:
        departments[user.get("department") or "未分组"] = departments.get(user.get("department") or "未分组", 0) + 1
        role_label = ROLE_PERMISSION_PRESETS.get(user.get("role", "user"), {}).get("label", user.get("role", "user"))
        roles[role_label] = roles.get(role_label, 0) + 1
    return {
        "users": users,
        "role_permissions": ROLE_PERMISSION_PRESETS,
        "departments": departments,
        "roles": roles,
        "activities": load_user_activity_store()[:100],
    }


def crawler_attr(module, name, default=None):
    return getattr(module, name, default)


def build_crawl_rules_payload():
    categories = {
        "platform_adapters": {"title": "平台适配规则", "items": []},
        "keywords": {"title": "关键词规则", "items": []},
        "fields": {"title": "抓取字段", "items": []},
        "anti_crawler": {"title": "反爬策略参数", "items": []},
        "frequency": {"title": "采集频率", "items": []},
        "cleaning": {"title": "数据清洗规则", "items": []},
    }
    common_fields = ["id", "platform", "platform_name", "screen_name", "text", "pics", "created_at", "keyword", "matched_keywords", "crawl_time"]
    for platform, info in PLATFORMS.items():
        with crawler_import_context(info["dir"]):
            setting_module = load_module(f"rules_setting_{platform}", info["dir"] / "setting.py")
            keywords = _read_text_lines(crawler_attr(setting_module, "KEYWORD_LIST", []))
            discovery = _read_text_lines(crawler_attr(setting_module, "CRAWL_KEYWORD_LIST", [])) or _read_text_lines(crawler_attr(setting_module, "DOUYIN_SEARCH_KEYWORD_LIST", []))
            forums = _read_text_lines(crawler_attr(setting_module, "FORUM_LIST", []))
            headers = crawler_attr(setting_module, "DEFAULT_REQUEST_HEADERS", {}) or {}
            cookie_value = crawler_attr(setting_module, "COOKIES", "") or crawler_attr(setting_module, "DOUYIN_COOKIE", "") or headers.get("cookie", "")
            max_pages = (
                crawler_attr(setting_module, "MAX_PAGES", None)
                or crawler_attr(setting_module, "MAX_PAGES_PER_KEYWORD", None)
                or crawler_attr(setting_module, "MAX_PAGES_PER_FORUM", None)
            )
            categories["platform_adapters"]["items"].append(
                {
                    "platform": platform,
                    "label": info["label"],
                    "rules": [
                        f"入口文件：{info['entry']}",
                        f"写入集合：test.{info['collection']}",
                        "接入方式：关键词搜索" if not forums else "接入方式：贴吧主题帖发现",
                        f"平台状态：{'已接入' if platform in PLATFORMS else '待接入'}",
                    ],
                }
            )
            categories["keywords"]["items"].append(
                {
                    "platform": platform,
                    "label": info["label"],
                    "rules": [
                        f"正文筛选关键词：{len(keywords)} 个",
                        f"发现搜索词：{len(discovery) if discovery else len(keywords)} 个",
                        f"贴吧/分区发现源：{len(forums)} 个" if forums else "贴吧/分区发现源：无",
                        "要求正文命中关键词" if crawler_attr(setting_module, "REQUIRE_KEYWORD_MATCH", True) else "不强制正文命中关键词",
                    ],
                    "samples": (discovery or forums or keywords)[:8],
                }
            )
            categories["fields"]["items"].append(
                {
                    "platform": platform,
                    "label": info["label"],
                    "rules": [
                        "统一写入微博兼容字段结构",
                        "图片字段 pics 保存本地绝对路径并由 /media 预览",
                        "保留 matched_keywords 用于后续筛选与解释",
                        f"核心字段：{', '.join(common_fields)}",
                    ],
                }
            )
            categories["anti_crawler"]["items"].append(
                {
                    "platform": platform,
                    "label": info["label"],
                    "rules": [
                        f"请求间隔：{crawler_attr(setting_module, 'DOWNLOAD_DELAY', '未设置')} 秒",
                        f"请求超时：{crawler_attr(setting_module, 'REQUEST_TIMEOUT', '未设置')} 秒",
                        f"最大重试：{crawler_attr(setting_module, 'MAX_RETRY', '未设置')}",
                        f"Cookie：{'已配置' if str(cookie_value).strip() else '未配置'}",
                        f"系统代理：{'启用' if crawler_attr(setting_module, 'TRUST_ENV_PROXY', False) else '关闭'}",
                    ],
                }
            )
            categories["frequency"]["items"].append(
                {
                    "platform": platform,
                    "label": info["label"],
                    "rules": [
                        f"单轮最大页数：{max_pages if max_pages is not None else '未设置'}",
                        f"最近天数：{crawler_attr(setting_module, 'RECENT_DAYS', '按平台默认')}",
                        f"搜索结果数量：{crawler_attr(setting_module, 'SEARCH_COUNT', crawler_attr(setting_module, 'THREAD_PAGE_SIZE', crawler_attr(setting_module, 'LIMIT_PER_KEYWORD', '按平台默认')))}",
                        "随机交错采集：启用" if (crawler_attr(setting_module, "RANDOMIZE_CRAWL_ORDER", False) or crawler_attr(setting_module, "RANDOMIZE_FORUM_ORDER", False)) else "随机交错采集：未启用",
                    ],
                }
            )
            categories["cleaning"]["items"].append(
                {
                    "platform": platform,
                    "label": info["label"],
                    "rules": [
                        "要求有图片" if crawler_attr(setting_module, "REQUIRE_IMAGES", False) else "不强制图片",
                        "要求有文本" if crawler_attr(setting_module, "REQUIRE_TEXT", True) else "不强制文本",
                        f"去重文件：{crawler_attr(setting_module, 'SEEN_IDS_FILE', '未设置')}",
                        f"图片目录：{crawler_attr(setting_module, 'RESULT_DIR', 'result')}/{crawler_attr(setting_module, 'PIC_DIR', 'pic')}",
                        f"时间旧帖丢弃率：{crawler_attr(setting_module, 'MAX_OLD_DROP_RATE', '按平台默认')}",
                    ],
                }
            )
    return {"categories": list(categories.values())}


def load_collection_sources_store():
    if not COLLECTION_SOURCES_FILE.exists():
        seeds = [
            {
                "id": "seed-weibo-001",
                "owner": "business-user",
                "platform_name": "微博金融关键词",
                "platform_type": "社交媒体",
                "target_url": "https://s.weibo.com",
                "account_name": "",
                "keywords": "理财 爆雷 维权",
                "time_range": "近两个月",
                "status": "待采集",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result_count": 0,
            },
            {
                "id": "seed-forum-001",
                "owner": "admin",
                "platform_name": "金融论坛观察源",
                "platform_type": "论坛",
                "target_url": "https://example.com/forum",
                "account_name": "",
                "keywords": "非法集资 投诉",
                "time_range": "近一周",
                "status": "规则配置中",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result_count": 12,
            },
        ]
        save_collection_sources_store(seeds)
        return seeds
    try:
        data = json.loads(COLLECTION_SOURCES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_collection_sources_store(items):
    COLLECTION_SOURCES_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def visible_collection_sources():
    items = load_collection_sources_store()
    if request_role() == "admin":
        return items
    user = request_user()
    return [item for item in items if item.get("owner") == user]


def sanitize_collection_source(payload, existing=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": existing.get("id") if existing else uuid4().hex,
        "owner": existing.get("owner") if existing else request_user(),
        "platform_name": str(payload.get("platform_name") or payload.get("platformName") or "").strip(),
        "platform_type": str(payload.get("platform_type") or payload.get("platformType") or "新闻网站").strip(),
        "target_url": str(payload.get("target_url") or payload.get("targetUrl") or "").strip(),
        "account_name": str(payload.get("account_name") or payload.get("accountName") or "").strip(),
        "keywords": str(payload.get("keywords") or "").strip(),
        "time_range": str(payload.get("time_range") or payload.get("timeRange") or "近两个月").strip(),
        "status": existing.get("status") if existing else "待采集",
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
        "result_count": int(existing.get("result_count", 0)) if existing else 0,
    }


PLATFORM_SOURCE_META = {
    "weibo": {"platform_type": "社交媒体", "target_url": "https://s.weibo.com", "keywords": "按微博平台设置关键词"},
    "douyin": {"platform_type": "短视频平台", "target_url": "https://www.douyin.com", "keywords": "按抖音平台设置关键词"},
    "tieba": {"platform_type": "贴吧", "target_url": "https://tieba.baidu.com", "keywords": "按百度贴吧平台设置关键词"},
    "xhs": {"platform_type": "社区平台", "target_url": "https://www.xiaohongshu.com", "keywords": "按小红书平台设置关键词"},
}


def platform_collection_source(platform, info):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = PLATFORM_SOURCE_META.get(platform, {})
    return {
        "id": f"platform-{platform}",
        "owner": "admin",
        "platform_id": platform,
        "platform_name": info.get("label") or platform,
        "platform_type": meta.get("platform_type", "平台"),
        "target_url": meta.get("target_url", ""),
        "account_name": "",
        "keywords": meta.get("keywords", "按平台设置关键词"),
        "time_range": "按平台设置",
        "status": "已配置",
        "source_kind": "platform",
        "created_at": now,
        "updated_at": now,
        "result_count": 0,
    }


def normalize_collection_source_item(item):
    item = dict(item or {})
    source_id = str(item.get("id") or uuid4().hex)
    item["id"] = source_id
    item.setdefault("owner", "admin" if source_id.startswith("platform-") else "business-user")
    item.setdefault("source_kind", "platform" if source_id.startswith("platform-") else "application")
    item.setdefault("status", "已配置" if item.get("source_kind") == "platform" else "待审核")
    if item.get("source_kind") == "application" and item.get("status") in {"已配置", "待采集", "规则配置中"}:
        item["status"] = "待审核"
    if item.get("source_kind") == "application" and item.get("status") == "已通过":
        item["source_kind"] = "custom"
    item.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    item.setdefault("updated_at", item.get("created_at"))
    item.setdefault("result_count", 0)
    return item


def ensure_platform_collection_sources(items):
    source_items = items if isinstance(items, list) else []
    normalized = [normalize_collection_source_item(item) for item in source_items if isinstance(item, dict)]
    by_id = {item.get("id"): item for item in normalized}
    changed = len(normalized) != len(source_items)
    merged = []
    for platform, info in PLATFORMS.items():
        seed = platform_collection_source(platform, info)
        existing = by_id.pop(seed["id"], None)
        if existing:
            seed.update(existing)
            seed["source_kind"] = "platform"
            seed["platform_id"] = platform
            seed["owner"] = "admin"
            seed["platform_name"] = info.get("label") or seed.get("platform_name") or platform
        else:
            changed = True
        merged.append(seed)
    merged.extend(by_id.values())
    return merged, changed


def load_collection_sources_store():
    if COLLECTION_SOURCES_FILE.exists():
        try:
            data = json.loads(COLLECTION_SOURCES_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = []
    else:
        data = []
    items, changed = ensure_platform_collection_sources(data)
    if changed or not COLLECTION_SOURCES_FILE.exists():
        save_collection_sources_store(items)
    return items


def visible_collection_sources():
    items = load_collection_sources_store()
    user = request_user()
    return [
        item
        for item in items
        if item.get("source_kind") == "platform"
        or item.get("source_kind") == "custom"
    ]


def collection_source_applications():
    apps = []
    for item in load_collection_sources_store():
        if item.get("source_kind") == "platform":
            continue
        apps.append(dict(item))
    return sorted(apps, key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)


def sanitize_collection_source(payload, existing=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    role = request_role()
    source_kind = existing.get("source_kind") if existing else ("custom" if role == "admin" else "application")
    status = existing.get("status") if existing else ("已配置" if role == "admin" else "待审核")
    status = status or ("已配置" if source_kind == "platform" else "待审核")
    if role == "admin" and "status" in payload:
        status = str(payload.get("status") or status).strip() or status
    elif existing and source_kind != "platform" and status in {"已退回", "待审核"}:
        status = "待审核"
    return {
        "id": existing.get("id") if existing else uuid4().hex,
        "owner": existing.get("owner") if existing else request_user(),
        "source_kind": source_kind,
        "platform_id": existing.get("platform_id", "") if existing else "",
        "platform_name": str(payload.get("platform_name") or payload.get("platformName") or "").strip(),
        "platform_type": str(payload.get("platform_type") or payload.get("platformType") or "新闻网站").strip(),
        "target_url": str(payload.get("target_url") or payload.get("targetUrl") or "").strip(),
        "account_name": str(payload.get("account_name") or payload.get("accountName") or "").strip(),
        "keywords": str(payload.get("keywords") or "").strip(),
        "time_range": str(payload.get("time_range") or payload.get("timeRange") or "近两个月").strip(),
        "status": status,
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
        "result_count": int(existing.get("result_count", 0)) if existing else 0,
    }


def add_watchlist_item(doc_id):
    doc_id = str(doc_id or "").strip()
    if not doc_id:
        raise ValueError("missing id")
    owner = request_user()
    items = load_watchlist_store()
    if any(entry["id"] == doc_id and entry.get("owner") == owner for entry in items):
        return False
    items.insert(0, {"id": doc_id, "owner": owner, "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    save_watchlist_store(items)
    return True


def remove_watchlist_item(doc_id):
    doc_id = str(doc_id or "").strip()
    owner = request_user()
    items = load_watchlist_store()
    next_items = [entry for entry in items if not (entry["id"] == doc_id and entry.get("owner") == owner)]
    changed = len(next_items) != len(items)
    if changed:
        save_watchlist_store(next_items)
    return changed


def load_watchlist_items(limit=100):
    owner = request_user()
    watchlist = [entry for entry in load_watchlist_store() if entry.get("owner") == owner]
    items = []
    added_map = {entry["id"]: entry.get("added_at", "") for entry in watchlist}
    for entry in watchlist[:limit]:
        doc = find_analyzed_item(entry["id"])
        if not doc:
            continue
        serialized = serialize_doc(doc)
        serialized["watch_added_at"] = added_map.get(serialized["_id"], "") or added_map.get(serialized["id"], "") or entry.get("added_at", "")
        items.append(serialized)
    return items, len(watchlist)


def extract_platform_defaults(platform):
    if platform in _platform_defaults_cache:
        return copy.deepcopy(_platform_defaults_cache[platform])
    info = PLATFORMS[platform]
    with crawler_import_context(info["dir"]):
        setting_module = load_module(f"default_setting_{platform}", info["dir"] / "setting.py")
        if platform == "weibo":
            headers = copy.deepcopy(getattr(setting_module, "DEFAULT_REQUEST_HEADERS", {}) or {})
            defaults = {
                "id": platform,
                "label": platform_label(platform),
                "available": True,
                "added": False,
                "description": "已接入爬虫",
                "selected": platform == "weibo",
                "headers": headers,
                "cookie": str(headers.get("cookie", "")),
                "keywords": _read_text_lines(getattr(setting_module, "KEYWORD_LIST", [])),
                "discovery_keywords": _read_text_lines(getattr(setting_module, "CRAWL_KEYWORD_LIST", [])),
                "recent_days": _safe_int(getattr(setting_module, "RECENT_DAYS", 60), 60, minimum=1, maximum=3650),
                "max_pages": _safe_int(getattr(setting_module, "MAX_PAGES", 50), 50, minimum=1, maximum=500),
                "require_images": _safe_bool(getattr(setting_module, "REQUIRE_IMAGES", True), True),
            }
            _platform_defaults_cache[platform] = defaults
            return copy.deepcopy(defaults)
        if platform == "douyin":
            defaults = {
                "id": platform,
                "label": platform_label(platform),
                "available": True,
                "added": False,
                "description": "已接入爬虫",
                "selected": False,
                "cookie": str(getattr(setting_module, "DOUYIN_COOKIE", "")),
                "keywords": _read_text_lines(getattr(setting_module, "KEYWORD_LIST", [])),
                "discovery_keywords": _read_text_lines(getattr(setting_module, "DOUYIN_SEARCH_KEYWORD_LIST", [])),
                "max_pages": _safe_int(getattr(setting_module, "MAX_PAGES_PER_KEYWORD", 1), 1, minimum=1, maximum=100),
                "require_images": _safe_bool(getattr(setting_module, "REQUIRE_IMAGES", True), True),
            }
            _platform_defaults_cache[platform] = defaults
            return copy.deepcopy(defaults)
        if platform == "tieba":
            defaults = {
                "id": platform,
                "label": platform_label(platform),
                "available": True,
                "added": False,
                "description": "已接入爬虫",
                "selected": False,
                "cookie": "",
                "keywords": _read_text_lines(getattr(setting_module, "KEYWORD_LIST", [])),
                "forums": _read_text_lines(getattr(setting_module, "FORUM_LIST", [])),
                "max_pages": _safe_int(getattr(setting_module, "MAX_PAGES_PER_FORUM", 100), 100, minimum=1, maximum=1000),
                "require_images": _safe_bool(getattr(setting_module, "REQUIRE_IMAGES", True), True),
            }
            _platform_defaults_cache[platform] = defaults
            return copy.deepcopy(defaults)
        if platform == "xhs":
            defaults = {
                "id": platform,
                "label": platform_label(platform),
                "available": True,
                "added": False,
                "description": "已接入爬虫",
                "selected": False,
                "cookie": str(getattr(setting_module, "COOKIES", "")),
                "keywords": _read_text_lines(getattr(setting_module, "KEYWORD_LIST", [])),
                "max_pages": _safe_int(getattr(setting_module, "MAX_PAGES", 5), 5, minimum=1, maximum=100),
                "note_time": _safe_int(getattr(setting_module, "NOTE_TIME", 0), 0, minimum=0, maximum=4),
                "require_images": _safe_bool(getattr(setting_module, "REQUIRE_IMAGES", True), True),
            }
            _platform_defaults_cache[platform] = defaults
            return copy.deepcopy(defaults)
    raise KeyError(platform)


def placeholder_platform_defaults(platform, custom_platforms=None):
    custom_platforms = custom_platforms or {}
    info = KNOWN_EXTRA_PLATFORMS.get(platform, {}) or custom_platforms.get(platform, {})
    return {
        "id": platform,
        "label": info.get("label", platform),
        "available": False,
        "added": True,
        "description": info.get("description", "待接入爬虫"),
        "selected": False,
        "cookie": "",
        "keywords": [],
        "discovery_keywords": [],
        "forums": [],
        "recent_days": 60,
        "max_pages": 10,
        "note_time": 0,
        "require_images": True,
    }


def sanitize_platform_config(platform, payload, defaults):
    payload = payload or {}
    config = copy.deepcopy(defaults)
    config["selected"] = _safe_bool(payload.get("selected"), defaults.get("selected", False))
    config["cookie"] = str(payload.get("cookie", defaults.get("cookie", "")) or "").strip()
    config["keywords"] = _read_text_lines(payload.get("keywords", defaults.get("keywords", [])))
    config["discovery_keywords"] = _read_text_lines(payload.get("discovery_keywords", defaults.get("discovery_keywords", [])))
    config["forums"] = _read_text_lines(payload.get("forums", defaults.get("forums", [])))
    config["recent_days"] = _safe_int(payload.get("recent_days", defaults.get("recent_days", 60)), defaults.get("recent_days", 60), minimum=1, maximum=3650)
    config["max_pages"] = _safe_int(payload.get("max_pages", defaults.get("max_pages", 10)), defaults.get("max_pages", 10), minimum=1, maximum=1000)
    config["note_time"] = _safe_int(payload.get("note_time", defaults.get("note_time", 0)), defaults.get("note_time", 0), minimum=0, maximum=4)
    config["require_images"] = _safe_bool(payload.get("require_images"), defaults.get("require_images", True))
    config["description"] = str(payload.get("description", defaults.get("description", "")) or defaults.get("description", ""))
    config["label"] = str(payload.get("label", defaults.get("label", platform)) or defaults.get("label", platform))
    config["available"] = bool(defaults.get("available", False))
    config["added"] = bool(defaults.get("added", False))
    config["id"] = platform
    config.pop("headers", None)
    return config


def build_platform_settings_payload():
    store = load_platform_settings_store()
    custom_platforms = store.get("custom_platforms", {})
    settings = {}
    ordered_ids = list(PLATFORMS)
    for platform in store.get("added_platforms", []):
        if platform not in ordered_ids:
            ordered_ids.append(platform)

    for platform in ordered_ids:
        defaults = extract_platform_defaults(platform) if platform in PLATFORMS else placeholder_platform_defaults(platform, custom_platforms)
        saved = store.get("platforms", {}).get(platform, {})
        config = sanitize_platform_config(platform, saved, defaults)
        config["cookie"] = runtime_cookie(platform, config.get("cookie", ""))
        settings[platform] = config

    options = [
        {
            "id": platform,
            "label": config["label"],
            "available": config["available"],
            "added": config["added"],
            "selected": config["selected"],
            "description": config["description"],
        }
        for platform, config in settings.items()
    ]
    known_platforms = [
        {
            "id": platform,
            "label": info["label"],
            "description": info["description"],
            "added": platform in settings,
        }
        for platform, info in KNOWN_EXTRA_PLATFORMS.items()
    ]
    return {
        "platforms": settings,
        "options": options,
        "known_platforms": known_platforms,
        "source_applications": collection_source_applications(),
    }


def persist_platform_settings(payload):
    current = build_platform_settings_payload()
    settings = current["platforms"]
    store = load_platform_settings_store()
    custom_platforms = store.get("custom_platforms", {})
    added_platforms = []
    for platform in payload.get("added_platforms", []):
        key = str(platform).strip()
        if (key in KNOWN_EXTRA_PLATFORMS or key in custom_platforms) and key not in added_platforms:
            added_platforms.append(key)
    for platform in added_platforms:
        settings.setdefault(platform, placeholder_platform_defaults(platform, custom_platforms))

    platform_payload = payload.get("platforms", {}) if isinstance(payload.get("platforms"), dict) else {}
    for platform, defaults in list(settings.items()):
        saved = platform_payload.get(platform, {})
        settings[platform] = sanitize_platform_config(platform, saved, defaults)

    retained_ids = list(PLATFORMS) + added_platforms

    store = {
        "added_platforms": added_platforms,
        "custom_platforms": custom_platforms,
        "platforms": {
            platform: {
                "selected": config["selected"],
                "cookie": config["cookie"],
                "keywords": config["keywords"],
                "discovery_keywords": config["discovery_keywords"],
                "forums": config["forums"],
                "recent_days": config["recent_days"],
                "max_pages": config["max_pages"],
                "note_time": config["note_time"],
                "require_images": config["require_images"],
            }
            for platform, config in settings.items()
            if platform in retained_ids
        },
    }
    save_platform_settings_store(store)
    return build_platform_settings_payload()


def source_platform_key(source):
    existing = str(source.get("platform_id") or "").strip()
    if existing and existing not in PLATFORMS:
        return existing
    return f"source-{str(source.get('id') or uuid4().hex)[:12]}"


def update_source_application_review(source_id, payload):
    status = str(payload.get("status") or "").strip()
    if status in {"approve", "approved", "pass", "agree", "同意", "通过"}:
        status = "已通过"
    if status in {"reject", "rejected", "return", "退回", "驳回"}:
        status = "已退回"
    if status not in {"已通过", "已退回"}:
        raise ValueError("审核状态只能是已通过或已退回。")

    items = load_collection_sources_store()
    source = None
    source_index = -1
    for index, item in enumerate(items):
        if item.get("id") == source_id:
            source = dict(item)
            source_index = index
            break
    if source is None:
        raise KeyError("采集源申请不存在。")
    if source.get("source_kind") == "platform":
        raise ValueError("系统内置平台源不需要审核。")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source["status"] = status
    source["reviewed_by"] = request_user()
    source["reviewed_at"] = now
    source["review_comment"] = str(payload.get("review_comment") or payload.get("comment") or "").strip()

    platform_payload = payload.get("platform_config") if isinstance(payload.get("platform_config"), dict) else {}
    if status == "已通过":
        platform_key = source_platform_key(source)
        source["platform_id"] = platform_key
        source["source_kind"] = "custom"

        store = load_platform_settings_store()
        custom_platforms = store.get("custom_platforms", {})
        custom_platforms[platform_key] = {
            "label": source.get("platform_name") or platform_key,
            "description": f"由前台采集申请接入：{source.get('platform_type') or '未分类'}",
            "target_url": source.get("target_url", ""),
            "source_id": source.get("id", ""),
            "owner": source.get("owner", ""),
            "platform_type": source.get("platform_type", ""),
        }
        added_platforms = [item for item in store.get("added_platforms", []) if item != platform_key]
        added_platforms.append(platform_key)

        store["added_platforms"] = added_platforms
        store["custom_platforms"] = custom_platforms
        store.setdefault("platforms", {})[platform_key] = {
            "selected": _safe_bool(platform_payload.get("selected"), False),
            "cookie": str(platform_payload.get("cookie", "") or "").strip(),
            "keywords": _read_text_lines(platform_payload.get("keywords") or source.get("keywords", "")),
            "discovery_keywords": _read_text_lines(platform_payload.get("discovery_keywords", [])),
            "forums": _read_text_lines(platform_payload.get("forums", [])),
            "recent_days": _safe_int(platform_payload.get("recent_days", 60), 60, minimum=1, maximum=3650),
            "max_pages": _safe_int(platform_payload.get("max_pages", 10), 10, minimum=1, maximum=1000),
            "note_time": _safe_int(platform_payload.get("note_time", 0), 0, minimum=0, maximum=4),
            "require_images": _safe_bool(platform_payload.get("require_images"), True),
            "label": source.get("platform_name") or platform_key,
            "description": custom_platforms[platform_key]["description"],
        }
        save_platform_settings_store(store)
    elif source.get("source_kind") == "custom":
        source["source_kind"] = "application"

    source["updated_at"] = now
    items[source_index] = source
    save_collection_sources_store(items)
    return source


def get_platform_runtime_overrides(platform):
    payload = build_platform_settings_payload()
    config = copy.deepcopy(payload["platforms"].get(platform, {}))
    if not config:
        return {}
    if platform == "weibo":
        defaults = extract_platform_defaults(platform)
        headers = copy.deepcopy(defaults.get("headers", {}))
        headers["cookie"] = config.get("cookie", "")
        return {
            "DEFAULT_REQUEST_HEADERS": headers,
            "KEYWORD_LIST": config.get("keywords", []),
            "CRAWL_KEYWORD_LIST": config.get("discovery_keywords", []),
            "RECENT_DAYS": config.get("recent_days", 60),
            "MAX_PAGES": config.get("max_pages", 50),
            "REQUIRE_IMAGES": config.get("require_images", True),
        }
    if platform == "douyin":
        return {
            "DOUYIN_COOKIE": config.get("cookie", ""),
            "KEYWORD_LIST": config.get("keywords", []),
            "DOUYIN_SEARCH_KEYWORD_LIST": config.get("discovery_keywords", []),
            "MAX_PAGES_PER_KEYWORD": config.get("max_pages", 1),
            "REQUIRE_IMAGES": config.get("require_images", True),
        }
    if platform == "tieba":
        return {
            "KEYWORD_LIST": config.get("keywords", []),
            "FORUM_LIST": config.get("forums", []),
            "MAX_PAGES_PER_FORUM": config.get("max_pages", 100),
            "REQUIRE_IMAGES": config.get("require_images", True),
        }
    if platform == "xhs":
        return {
            "COOKIES": config.get("cookie", ""),
            "KEYWORD_LIST": config.get("keywords", []),
            "MAX_PAGES": config.get("max_pages", 5),
            "NOTE_TIME": config.get("note_time", 0),
            "REQUIRE_IMAGES": config.get("require_images", True),
        }
    return {}


def configured_platform_options():
    return build_platform_settings_payload()["options"]


def configured_available_platforms(values=None):
    options = {item["id"]: item for item in configured_platform_options()}
    selected = []
    if values:
        for value in values:
            key = str(value).strip()
            if options.get(key, {}).get("available") and key not in selected:
                selected.append(key)
    if selected:
        return selected
    defaults = [item["id"] for item in options.values() if item.get("available") and item.get("selected")]
    return defaults or ["weibo"]


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
        except Exception:
            if STRICT_RUNTIME:
                raise
        finally:
            client.close()

        analyzer_cls = load_analyzer_class()
        _engine = analyzer_cls(base_dir=str(BASE_DIR), strict_init=STRICT_RUNTIME, load_word_vector_model=LOAD_WORD_VECTOR_MODEL)
        _runtime_ready = True
        start_background_analysis_once()
        return _engine


def get_risk_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            return initialize_runtime()
        return _engine


def start_background_analysis_once(limit_per_round=20):
    global _startup_analysis_started
    if not AUTO_ANALYZE_CRAWLED_ITEMS:
        return
    with _startup_analysis_lock:
        if _startup_analysis_started:
            return
        _startup_analysis_started = True

    def worker():
        while True:
            try:
                processed, errors = analyze_unprocessed_documents(limit=limit_per_round)
            except Exception:
                break
            if processed <= 0:
                break

    threading.Thread(target=worker, name="startup-analysis-worker", daemon=True).start()


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


def analyze_doc_for_update(doc, log=None):
    item = dict(doc)
    if log:
        log(f"开始多模态分析 {item.get('platform_name', item.get('platform', ''))} {item.get('id', '')}。")
    analyze_weibo_item(item)
    return {
        "analysis": item.get("analysis"),
        "analysis_status": item.get("analysis_status"),
        "analysis_error": item.get("analysis_error", ""),
        "analysis_image": item.get("analysis_image", ""),
        "analysis_at": item.get("analysis_at"),
    }


def analyze_unprocessed_documents(limit=20, log=None):
    processed = 0
    errors = []
    platforms = list(PLATFORMS)
    per_platform_limit = max(1, (limit + len(platforms) - 1) // len(platforms))
    query = {
        "text": {"$type": "string", "$ne": ""},
        "pics.0": {"$exists": True},
        "$or": [{"analysis_status": {"$exists": False}}, {"analysis_status": {"$nin": ["done", "analyzing"]}}],
    }
    jobs = []
    client = MongoClient(setting.MONGO_URI, serverSelectionTimeoutMS=3000)
    try:
        db = client[setting.MONGO_DATABASE]
        for platform in platforms:
            collection = db[platform_collection(platform)]
            platform_query = {**query, "platform": platform}
            docs = list(collection.find(platform_query).sort([("crawl_time", DESCENDING), ("_id", DESCENDING)]).limit(per_platform_limit))
            for doc in docs:
                if len(jobs) >= limit:
                    break
                claimed = collection.update_one(
                    {**platform_query, "_id": doc["_id"]},
                    {"$set": {"analysis_status": "analyzing", "analysis_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}},
                )
                if not claimed.modified_count:
                    continue
                jobs.append((platform, collection, doc))
            if len(jobs) >= limit:
                break

        if not jobs:
            return processed, errors

        worker_count = min(ANALYSIS_MAX_WORKERS, len(jobs))
        if log and worker_count > 1:
            log(f"并行启动 {worker_count} 个多模态分析任务，待处理 {len(jobs)} 条。")

        def run_job(job):
            platform, collection, doc = job
            update = analyze_doc_for_update(doc, log=log)
            return platform, collection, doc, update

        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="analysis-worker") as executor:
            future_map = {executor.submit(run_job, job): job for job in jobs}
            for future in as_completed(future_map):
                platform, collection, doc = future_map[future]
                try:
                    _platform, _collection, _doc, update = future.result()
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": update},
                    )
                    processed += 1
                except Exception as exc:
                    message = f"{doc.get('id', doc.get('_id'))}: {exc}"
                    errors.append(message)
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                "analysis_status": "error",
                                "analysis_error": str(exc),
                                "analysis_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            }
                        },
                    )
                    if log:
                        log(f"多模态分析失败: {message}")
        return processed, errors
    finally:
        client.close()


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
        for key, value in get_platform_runtime_overrides("weibo").items():
            setattr(setting_module, key, value)
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
        for key, value in get_platform_runtime_overrides("xhs").items():
            setattr(setting_module, key, value)
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
        self.selected_platforms = configured_available_platforms()
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
            self.selected_platforms = configured_available_platforms(selected_platforms)
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
                if AUTO_ANALYZE_CRAWLED_ITEMS:
                    processed, errors = analyze_unprocessed_documents(limit=20, log=self.add_log)
                    if processed or errors:
                        self.add_log(f"周期补分析完成，处理 {processed} 条，错误 {len(errors)} 条。")
                for thread in threads:
                    thread.join(timeout=5)

            for thread in threads:
                thread.join()

            if AUTO_ANALYZE_CRAWLED_ITEMS:
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
                item_callback=self._analyze_new_item if AUTO_ANALYZE_CRAWLED_ITEMS and ANALYSIS_MAX_WORKERS <= 1 else None,
                mongo_uri=setting.MONGO_URI,
                mongo_database=setting.MONGO_DATABASE,
                mongo_collection=platform_collection(platform),
                max_items=self.platform_item_limit,
                setting_overrides=get_platform_runtime_overrides(platform),
            )
            self.update_platform_stats(platform, platform_result or {})
            self.add_log(f"{label} 爬取完成。")
        except Exception as exc:
            with self.lock:
                self.last_error = str(exc)
            self.add_log(f"{label} 爬取异常: {exc}")

    def _analyze_new_item(self, item):
        self.add_log(f"开始多模态分析 {item.get('platform_name', item.get('platform', '平台'))} {item.get('id', '')}。")
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
                "platform_options": configured_platform_options(),
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


@app.get("/platform-application")
def platform_application_page():
    return send_from_directory(FRONTEND_DIR, "platform_application.html")


@app.get("/account-editor")
def account_editor_page():
    return send_from_directory(FRONTEND_DIR, "account_editor.html")


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
                "engine_file": str(ENGINE_FILE),
                "analysis_max_workers": ANALYSIS_MAX_WORKERS,
                "auto_analyze_crawled_items": AUTO_ANALYZE_CRAWLED_ITEMS,
                "runtime_config_file": str(RUNTIME_CONFIG_FILE),
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
    blocked = require_admin()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    action = task.start_or_resume(payload.get("platforms"))
    return jsonify({"ok": True, "action": action, "status": task.status()})


@app.post("/api/crawl/pause")
def pause_crawl():
    blocked = require_admin()
    if blocked:
        return blocked
    ok = task.pause()
    return jsonify({"ok": ok, "status": task.status()})


@app.get("/api/crawl/status")
def crawl_status():
    return jsonify(task.status())


@app.get("/api/platform-settings")
def get_platform_settings():
    blocked = require_admin()
    if blocked:
        return blocked
    payload = build_platform_settings_payload()
    return jsonify({"ok": True, **payload})


@app.post("/api/platform-settings")
def save_platform_settings():
    blocked = require_admin()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    saved = persist_platform_settings(payload)
    return jsonify({"ok": True, **saved})


@app.post("/api/platform-settings/applications/<source_id>/review")
def review_platform_application(source_id):
    blocked = require_admin()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    try:
        item = update_source_application_review(source_id, payload)
        settings = build_platform_settings_payload()
        return jsonify({"ok": True, "item": item, **settings})
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/platform-settings/applications/<source_id>")
def get_platform_application(source_id):
    blocked = require_admin()
    if blocked:
        return blocked
    for item in collection_source_applications():
        if item.get("id") == source_id:
            return jsonify({"ok": True, "item": item})
    return jsonify({"ok": False, "error": "采集源申请不存在。"}), 404


@app.get("/api/session")
def session_info():
    role = request_role()
    return jsonify(
        {
            "ok": True,
            "user": request_user(),
            "role": role,
            "permissions": {
                "business": True,
                "admin": role == "admin",
                "own_sources_only": role != "admin",
            },
        }
    )


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    role = str(payload.get("role") or "").strip().lower()
    user = find_user(username)
    if not user or user.get("password") != password:
        return jsonify({"ok": False, "error": "用户名或密码错误。"}), 401
    if not user.get("enabled", True):
        return jsonify({"ok": False, "error": "账号已被禁用，请联系管理员。"}), 403
    if role in {"user", "admin"} and user.get("role") != role:
        return jsonify({"ok": False, "error": "账号角色与登录入口不匹配。"}), 403
    log_user_activity("登录系统", "登录成功", username=user.get("username"), role=user.get("role", "user"))
    return jsonify(
        {
            "ok": True,
            "user": public_user(user),
        }
    )


@app.post("/api/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    display_name = str(payload.get("display_name") or payload.get("displayName") or username).strip()
    if not username or not password:
        return jsonify({"ok": False, "error": "用户名和密码不能为空。"}), 400
    if username.lower() == "admin":
        return jsonify({"ok": False, "error": "注册账号只能是普通用户。"}), 400
    users = load_users_store()
    if any(user.get("username") == username for user in users):
        return jsonify({"ok": False, "error": "用户名已存在。"}), 409
    user = {
        "username": username,
        "password": password,
        "role": "user",
        "display_name": display_name or username,
        "phone": "",
        "department": "",
        "enabled": True,
    }
    users.append(user)
    save_users_store(users)
    return jsonify(
        {
            "ok": True,
            "user": public_user(user),
        }
    )


@app.put("/api/account/profile")
def update_profile():
    username = request_user()
    payload = request.get_json(silent=True) or {}
    display_name = str(payload.get("display_name") or payload.get("displayName") or "").strip()
    if not display_name:
        return jsonify({"ok": False, "error": "显示名称不能为空。"}), 400
    users = load_users_store()
    for user in users:
        if user.get("username") != username:
            continue
        user["display_name"] = display_name
        save_users_store(users)
        return jsonify(
            {
                "ok": True,
                "user": public_user(user),
            }
        )
    return jsonify({"ok": False, "error": "当前账号不存在。"}), 404


@app.put("/api/account/password")
def update_password():
    username = request_user()
    payload = request.get_json(silent=True) or {}
    old_password = str(payload.get("old_password") or payload.get("oldPassword") or "")
    new_password = str(payload.get("new_password") or payload.get("newPassword") or "")
    if not old_password or not new_password:
        return jsonify({"ok": False, "error": "原密码和新密码不能为空。"}), 400
    if len(new_password) < 6:
        return jsonify({"ok": False, "error": "新密码至少需要 6 位。"}), 400
    users = load_users_store()
    for user in users:
        if user.get("username") != username:
            continue
        if user.get("password") != old_password:
            return jsonify({"ok": False, "error": "原密码不正确。"}), 403
        user["password"] = new_password
        save_users_store(users)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "当前账号不存在。"}), 404


@app.get("/api/admin/accounts")
def list_accounts():
    blocked = require_admin()
    if blocked:
        return blocked
    return jsonify({"ok": True, "items": [public_user(user) for user in load_users_store()]})


@app.post("/api/admin/accounts")
def create_account():
    blocked = require_admin()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    item = sanitize_admin_user_payload(payload)
    if not item["username"] or not item["password"]:
        return jsonify({"ok": False, "error": "用户名和初始密码不能为空。"}), 400
    if len(item["password"]) < 6:
        return jsonify({"ok": False, "error": "密码至少 6 位。"}), 400
    users = load_users_store()
    if any(user.get("username") == item["username"] for user in users):
        return jsonify({"ok": False, "error": "用户名已存在。"}), 409
    users.append(item)
    save_users_store(users)
    log_user_activity("新增账号", f"创建账号 {item['username']}")
    return jsonify({"ok": True, "item": public_user(item), "items": [public_user(user) for user in users]})


@app.put("/api/admin/accounts/<username>")
def update_account(username):
    blocked = require_admin()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    users = load_users_store()
    for index, user in enumerate(users):
        if user.get("username") != username:
            continue
        next_user = sanitize_admin_user_payload(payload, existing=user)
        if not next_user["username"]:
            return jsonify({"ok": False, "error": "用户名不能为空。"}), 400
        if next_user["username"] != username and any(entry.get("username") == next_user["username"] for entry in users):
            return jsonify({"ok": False, "error": "新用户名已存在。"}), 409
        if not next_user["password"]:
            next_user["password"] = user.get("password", "")
        users[index] = next_user
        save_users_store(users)
        log_user_activity("修改账号", f"更新账号 {username}")
        return jsonify({"ok": True, "item": public_user(next_user), "items": [public_user(entry) for entry in users]})
    return jsonify({"ok": False, "error": "账号不存在。"}), 404


@app.post("/api/admin/accounts/<username>/reset-password")
def reset_account_password(username):
    blocked = require_admin()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    new_password = str(payload.get("password") or payload.get("new_password") or "").strip()
    if len(new_password) < 6:
        return jsonify({"ok": False, "error": "新密码至少 6 位。"}), 400
    users = load_users_store()
    for user in users:
        if user.get("username") != username:
            continue
        user["password"] = new_password
        save_users_store(users)
        log_user_activity("重置密码", f"重置账号 {username} 的密码")
        return jsonify({"ok": True, "item": public_user(user)})
    return jsonify({"ok": False, "error": "账号不存在。"}), 404


@app.get("/api/admin/user-management")
def get_user_management():
    blocked = require_admin()
    if blocked:
        return blocked
    return jsonify({"ok": True, **build_user_management_payload()})


@app.get("/api/admin/crawl-rules")
def get_crawl_rules():
    blocked = require_admin()
    if blocked:
        return blocked
    return jsonify({"ok": True, **build_crawl_rules_payload()})


@app.get("/api/admin/system-settings")
def get_system_settings():
    blocked = require_admin()
    if blocked:
        return blocked
    return jsonify(
        {
            "ok": True,
            "runtime": runtime_effective_config(),
            "engine_options": available_engine_files(),
            "paths": {
                "base_dir": str(BASE_DIR),
                "frontend_dir": str(FRONTEND_DIR),
                "crawler_dir": str(CRAWLERS_DIR),
                "runtime_config_file": str(RUNTIME_CONFIG_FILE),
                "platform_settings_file": str(PLATFORM_SETTINGS_FILE),
                "collection_sources_file": str(COLLECTION_SOURCES_FILE),
                "users_file": str(USERS_FILE),
            },
            "database": {
                "mongo_uri": getattr(setting, "MONGO_URI", ""),
                "collections": {
                    platform: info["collection"]
                    for platform, info in PLATFORMS.items()
                },
            },
            "platforms": platform_options(),
        }
    )


@app.put("/api/admin/system-settings")
def update_system_settings():
    blocked = require_admin()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    config = sanitize_runtime_config_payload(payload)
    save_runtime_config(config)
    apply_runtime_config(config)
    log_user_activity("修改系统设置", "更新运行参数与分析配置")
    return jsonify({"ok": True, "runtime": runtime_effective_config(), "engine_options": available_engine_files()})


@app.post("/api/admin/system-settings/reset-engine")
def reset_system_engine():
    blocked = require_admin()
    if blocked:
        return blocked
    apply_runtime_config(RUNTIME_CONFIG, reset_engine=True)
    log_user_activity("重置分析引擎", "已清空当前多模态分析引擎实例")
    return jsonify({"ok": True, "runtime": runtime_effective_config()})


@app.get("/api/collection-sources")
def list_collection_sources():
    return jsonify({"ok": True, "role": request_role(), "items": visible_collection_sources()})


@app.post("/api/collection-sources")
def create_collection_source():
    payload = request.get_json(silent=True) or {}
    item = sanitize_collection_source(payload)
    if not item["platform_name"] or not item["target_url"]:
        return jsonify({"ok": False, "error": "平台名称和目标网址不能为空。"}), 400
    items = load_collection_sources_store()
    items.insert(0, item)
    save_collection_sources_store(items)
    return jsonify({"ok": True, "item": item, "items": visible_collection_sources()})


@app.put("/api/collection-sources/<source_id>")
def update_collection_source(source_id):
    payload = request.get_json(silent=True) or {}
    items = load_collection_sources_store()
    for index, item in enumerate(items):
        if item.get("id") != source_id:
            continue
        if request_role() != "admin":
            if item.get("source_kind") == "platform":
                application = sanitize_collection_source(payload)
                if not application["platform_name"]:
                    application["platform_name"] = item.get("platform_name", "")
                if not application["target_url"]:
                    application["target_url"] = item.get("target_url", "")
                items.insert(0, application)
                save_collection_sources_store(items)
                return jsonify({"ok": True, "item": application, "items": visible_collection_sources()})
            if item.get("owner") != request_user():
                return jsonify({"ok": False, "error": "普通用户只能修改自己提交的采集申请。"}), 403
            if item.get("status") in {"已配置", "已通过"}:
                return jsonify({"ok": False, "error": "已通过的采集源不能由普通用户直接修改，请重新提交申请。"}), 403
        elif item.get("source_kind") != "platform" and str(payload.get("status") or "").strip() in {"已通过", "已退回"}:
            reviewed = update_source_application_review(source_id, payload)
            return jsonify({"ok": True, "item": reviewed, "items": visible_collection_sources()})
        next_item = sanitize_collection_source(payload, existing=item)
        if request_role() == "admin" and "status" in payload:
            next_item["status"] = str(payload.get("status") or item.get("status") or "待审核")
        items[index] = next_item
        save_collection_sources_store(items)
        return jsonify({"ok": True, "item": next_item, "items": visible_collection_sources()})
    return jsonify({"ok": False, "error": "采集源不存在。"}), 404


@app.delete("/api/collection-sources/<source_id>")
def delete_collection_source(source_id):
    items = load_collection_sources_store()
    for item in items:
        if item.get("id") != source_id:
            continue
        if request_role() != "admin":
            return jsonify({"ok": False, "error": "普通用户没有删减采集源列表的权限。"}), 403
        if item.get("source_kind") == "platform":
            return jsonify({"ok": False, "error": "系统内置平台源需要与任务控制栏保持一致，不能删除。"}), 400
        next_items = [entry for entry in items if entry.get("id") != source_id]
        save_collection_sources_store(next_items)
        return jsonify({"ok": True, "items": visible_collection_sources()})
    return jsonify({"ok": False, "error": "采集源不存在。"}), 404


@app.get("/api/watchlist")
def get_watchlist():
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 300))
        items, total = load_watchlist_items(limit)
        return jsonify({"ok": True, "total": total, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "total": 0, "items": [], "error": str(exc)}), 500


@app.post("/api/watchlist")
def add_watchlist():
    payload = request.get_json(silent=True) or {}
    doc_id = payload.get("id")
    try:
        created = add_watchlist_item(doc_id)
        items, total = load_watchlist_items(100)
        return jsonify({"ok": True, "created": created, "total": total, "items": items})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.delete("/api/watchlist/<doc_id>")
def delete_watchlist_item(doc_id):
    try:
        removed = remove_watchlist_item(doc_id)
        items, total = load_watchlist_items(100)
        return jsonify({"ok": True, "removed": removed, "total": total, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/items")
@app.get("/api/weibos")
def list_weibos():
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 2000))
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
    blocked = require_admin()
    if blocked:
        return blocked
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
