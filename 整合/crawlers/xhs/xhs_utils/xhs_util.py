import json
import math
import os
import random
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import execjs
from xhs_utils.cookie_util import trans_cookies

PROJECT_DIR = Path(__file__).resolve().parents[1]
NODE_MODULES_DIR = PROJECT_DIR / "node_modules"

if NODE_MODULES_DIR.exists():
    existing_node_path = os.environ.get("NODE_PATH", "")
    node_paths = [item for item in existing_node_path.split(os.pathsep) if item]
    if str(NODE_MODULES_DIR) not in node_paths:
        os.environ["NODE_PATH"] = os.pathsep.join([str(NODE_MODULES_DIR), *node_paths]) if node_paths else str(NODE_MODULES_DIR)


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def normalize_static_requires(source: str) -> str:
    replacements = {
        "require('./xhs_xray_pack1.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_xray_pack1.js').as_posix()}')",
        "require('../static/xhs_xray_pack1.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_xray_pack1.js').as_posix()}')",
        "require('./static/xhs_xray_pack1.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_xray_pack1.js').as_posix()}')",
        "require('./xhs_xray_pack2.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_xray_pack2.js').as_posix()}')",
        "require('../static/xhs_xray_pack2.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_xray_pack2.js').as_posix()}')",
        "require('./static/xhs_xray_pack2.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_xray_pack2.js').as_posix()}')",
        "require('./xhs_creator_sign_other.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_creator_sign_other.js').as_posix()}')",
        "require('../static/xhs_creator_sign_other.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_creator_sign_other.js').as_posix()}')",
        "require('./static/xhs_creator_sign_other.js')": f"require('{(PROJECT_DIR / 'static' / 'xhs_creator_sign_other.js').as_posix()}')",
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    return source


def compile_static_js(file_name):
    with working_directory(PROJECT_DIR):
        source = (PROJECT_DIR / "static" / file_name).read_text(encoding="utf-8")
        return execjs.compile(normalize_static_requires(source))


_js = None
_xray_js = None


def get_js_context():
    global _js
    if _js is None:
        _js = compile_static_js("xhs_main_260411.js")
    return _js


def get_xray_context():
    global _xray_js
    if _xray_js is None:
        _xray_js = compile_static_js("xhs_xray.js")
    return _xray_js


def reset_js_contexts():
    global _js, _xray_js
    _js = None
    _xray_js = None


def call_js_with_retry(context_getter, func_name, *args):
    try:
        return context_getter().call(func_name, *args)
    except Exception:
        reset_js_contexts()
        return context_getter().call(func_name, *args)

def generate_x_b3_traceid(len=16):
    x_b3_traceid = ""
    for t in range(len):
        x_b3_traceid += "abcdef0123456789"[math.floor(16 * random.random())]
    return x_b3_traceid

def generate_xs_xs_common(a1, api, data='', method='POST'):
    ret = call_js_with_retry(get_js_context, 'get_request_headers_params', api, data, a1, method)
    ret = ret or {}
    xs, xt, xs_common = str(ret.get('xs') or ''), ret.get('xt') or '', str(ret.get('xs_common') or '')
    return xs, xt, xs_common

def generate_xs(a1, api, data=''):
    ret = call_js_with_retry(get_js_context, 'get_xs', api, data, a1)
    ret = ret or {}
    xs, xt = str(ret.get('X-s') or ''), ret.get('X-t') or ''
    return xs, xt

def generate_xray_traceid():
    try:
        return str(call_js_with_retry(get_xray_context, 'traceId') or generate_x_b3_traceid())
    except Exception:
        return generate_x_b3_traceid()
def get_common_headers():
    user_agent = os.getenv(
        "XHS_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    )
    return {
        "authority": "www.xiaohongshu.com",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://www.xiaohongshu.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": user_agent,
    }
def get_request_headers_template():
    user_agent = os.getenv(
        "XHS_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    )
    return {
        "authority": "edith.xiaohongshu.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://www.xiaohongshu.com",
        "pragma": "no-cache",
        "referer": "https://www.xiaohongshu.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": user_agent,
        "x-b3-traceid": "",
        "x-mns": "unload",
        "x-s": "",
        "x-s-common": "",
        "x-t": "",
        "x-xray-traceid": generate_xray_traceid()
    }

def generate_headers(a1, api, data='', method='POST'):
    xs, xt, xs_common = generate_xs_xs_common(a1, api, data, method)
    x_b3_traceid = generate_x_b3_traceid()
    headers = get_request_headers_template()
    headers['x-s'] = xs
    headers['x-t'] = str(xt)
    headers['x-s-common'] = xs_common
    headers['x-b3-traceid'] = x_b3_traceid
    if data:
        data = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    return headers, data

def generate_request_params(cookies_str, api, data='', method='POST'):
    cookies = trans_cookies(cookies_str)
    cookies["xsecappid"] = os.getenv("XHS_XSECAPPID", "xhs-pc-web")
    a1 = cookies.get('a1') or ''
    if not a1:
        raise ValueError("missing xhs cookie field: a1")
    headers, data = generate_headers(a1, api, data, method)
    return headers, cookies, data

def splice_str(api, params):
    url = api + '?'
    for key, value in params.items():
        if value is None:
            value = ''
        url += key + '=' + value + '&'
    return url[:-1]
