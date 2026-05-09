# -*- coding: utf-8 -*-
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse

import requests
from lxml import html
from pymongo import MongoClient, UpdateOne
from pymongo.errors import OperationFailure

import setting


BASE_URL = "https://s.weibo.com"
PROJECT_DIR = Path(__file__).resolve().parent


def ensure_index(collection, *args, **kwargs):
    try:
        return collection.create_index(*args, **kwargs)
    except OperationFailure as exc:
        if getattr(exc, "code", None) in {85, 86}:
            return None
        raise


def resolve_crawler_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def convert_weibo_type(value):
    return {
        0: "&typeall=1",
        1: "&scope=ori",
        2: "&xsort=hot",
        3: "&atten=1",
        4: "&vip=1",
        5: "&category=4",
        6: "&viewpoint=1",
    }.get(value, "&typeall=1")


def convert_contain_type(value):
    return {
        0: "&suball=1",
        1: "&haspic=1",
        2: "&hasvideo=1",
        3: "&hasmusic=1",
        4: "&haslink=1",
    }.get(value, "&suball=1")


def read_keywords(value):
    if isinstance(value, (list, tuple)):
        keywords = [str(item).strip() for item in value if str(item).strip()]
    else:
        path = resolve_crawler_path(value)
        with path.open("r", encoding="utf-8-sig") as file:
            keywords = [line.strip() for line in file if line.strip()]

    result = []
    for keyword in keywords:
        if len(keyword) > 2 and keyword.startswith("#") and keyword.endswith("#"):
            result.append("%23" + quote(keyword[1:-1]) + "%23")
        else:
            result.append(quote(keyword))
    return result


def read_plain_keywords(value):
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]

    path = resolve_crawler_path(value)
    with path.open("r", encoding="utf-8-sig") as file:
        return [line.strip() for line in file if line.strip()]


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\u200b", "").replace("\ue627", "")).strip()


def first_text(node, xpath):
    result = node.xpath(xpath)
    if not result:
        return ""
    if hasattr(result[0], "xpath"):
        return clean_text(result[0].xpath("string(.)"))
    return clean_text(str(result[0]))


def first_attr(node, xpath):
    result = node.xpath(xpath)
    return str(result[0]).strip() if result else ""


def parse_count(text):
    match = re.search(r"(\d+)", text or "")
    return match.group(1) if match else "0"


def standardize_date(text):
    text = clean_text(text).split("前")[0]
    now = datetime.now()
    try:
        if "刚刚" in text:
            return now.strftime("%Y-%m-%d %H:%M")
        if "秒" in text:
            seconds = int(re.search(r"\d+", text).group())
            return (now - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M")
        if "分钟" in text:
            minutes = int(re.search(r"\d+", text).group())
            return (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")
        if "小时" in text:
            hours = int(re.search(r"\d+", text).group())
            return (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
        if text.startswith("今天"):
            return now.strftime("%Y-%m-%d") + " " + text.replace("今天", "").strip()
        if "年" in text:
            return datetime.strptime(text, "%Y年%m月%d日 %H:%M").strftime("%Y-%m-%d %H:%M")
        return datetime.strptime(str(now.year) + "-" + text, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return text


def get_article_url(text_node):
    text = clean_text(text_node.xpath("string(.)"))
    if not text.startswith("发布了头条文章"):
        return ""
    for link in text_node.xpath(".//a"):
        href = first_attr(link, "./@href")
        icon = first_text(link, './i[@class="wbicon"]/text()')
        if icon == "O" and href.startswith("http://t.cn"):
            return href
    return ""


def get_location(text_node):
    for link in text_node.xpath(".//a"):
        icon = first_text(link, './i[@class="wbicon"]/text()')
        if icon == "2":
            return clean_text(link.xpath("string(.)"))[1:]
    return ""


def get_at_users(text_node):
    users = []
    for link in text_node.xpath(".//a"):
        href = unquote(first_attr(link, "./@href"))
        text = clean_text(link.xpath("string(.)"))
        if text.startswith("@") and len(text) > 1 and text[1:] not in users:
            if len(href) <= 14 or href[14:] == text[1:]:
                users.append(text[1:])
    return ",".join(users)


def get_topics(text_node):
    topics = []
    for link in text_node.xpath(".//a"):
        text = clean_text(link.xpath("string(.)"))
        if len(text) > 2 and text.startswith("#") and text.endswith("#"):
            topic = text[1:-1]
            if topic not in topics:
                topics.append(topic)
    return ",".join(topics)


def normalize_pic_url(src):
    pic = str(src).strip()
    if not pic:
        return ""
    if pic.startswith("//"):
        pic = "https:" + pic
    parsed = urlparse(pic)
    if not parsed.scheme or not parsed.netloc:
        return pic

    path_parts = parsed.path.lstrip("/").split("/")
    if len(path_parts) >= 2:
        path_parts[0] = "large"
        parsed = parsed._replace(path="/" + "/".join(path_parts))
    return urlunparse(parsed)


def get_date_range():
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=getattr(setting, "RECENT_DAYS", 60))
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def build_url(keyword, page, start_date, end_date):
    start = start_date + "-0"
    end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d-0")
    region = f"&region=custom:{setting.REGION_CODE}:1000" if getattr(setting, "REGION_CODE", "") else ""
    url = f"{BASE_URL}/weibo?q={keyword}{region}"
    url += convert_weibo_type(setting.WEIBO_TYPE)
    url += convert_contain_type(setting.CONTAIN_TYPE)
    url += f"&timescope=custom:{start}:{end}&page={page}"
    return url


def parse_created_datetime(value):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def match_filter_keywords(item, filter_keywords):
    text = item.get("text", "")
    matched = [keyword for keyword in filter_keywords if keyword and keyword in text]
    return matched


def get_pic_dir():
    result_dir = resolve_crawler_path(getattr(setting, "RESULT_DIR", "result"))
    pic_dir = Path(getattr(setting, "PIC_DIR", "pic"))
    if not pic_dir.is_absolute():
        pic_dir = result_dir / pic_dir
    pic_dir.mkdir(parents=True, exist_ok=True)
    return pic_dir


def image_extension(url, content_type=""):
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


def download_pics(session, item):
    pic_urls = item.get("pics") or []
    if not pic_urls:
        return []

    pic_dir = get_pic_dir()
    image_headers = {
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://s.weibo.com/",
        "User-Agent": setting.DEFAULT_REQUEST_HEADERS.get("User-Agent", ""),
    }
    local_paths = []
    for index, url in enumerate(pic_urls, start=1):
        try:
            response = session.get(url, headers=image_headers, timeout=getattr(setting, "IMAGE_TIMEOUT", 30))
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type.lower():
                raise ValueError(f"返回内容不是图片: {content_type}")
            ext = image_extension(url, content_type)
            local_path = pic_dir / f"{item['id']}_{index}{ext}"
            if not local_path.exists():
                local_path.write_bytes(response.content)
            local_paths.append(str(local_path.resolve()))
        except Exception as exc:
            print(f"图片下载失败，保留跳过: {url}，原因: {exc}")
    return local_paths


def should_keep_by_age(item):
    created_at = parse_created_datetime(item.get("created_at", ""))
    if not created_at:
        return True

    recent_days = max(1, int(getattr(setting, "RECENT_DAYS", 60)))
    max_drop_rate = max(0.0, min(1.0, float(getattr(setting, "MAX_OLD_DROP_RATE", 0.8))))
    age_days = max(0.0, (datetime.now() - created_at).total_seconds() / 86400)
    if age_days > recent_days:
        return False

    drop_rate = (age_days / recent_days) * max_drop_rate
    return random.random() >= drop_rate


def parse_weibos(page_text, crawl_keyword):
    document = html.fromstring(page_text)
    for card in document.xpath("//div[contains(concat(' ', @class, ' '), ' card-wrap ')]"):
        if not first_attr(card, "./@mid"):
            continue
        try:
            item = parse_one_weibo(card, crawl_keyword)
        except Exception as exc:
            print(f"跳过一条解析失败的微博: {exc}")
            continue
        if item:
            yield item


def parse_one_weibo(card, crawl_keyword):
    info = card.xpath(".//div[contains(@class,'card-feed')]//div[contains(@class,'content')]/div[contains(@class,'info')]")
    if not info:
        return None
    info = info[0]

    from_href = first_attr(card, './/div[contains(@class,"from")]/a[1]/@href')
    user_href = first_attr(info, ".//a[1]/@href")
    text_nodes = card.xpath('.//p[contains(concat(" ", @class, " "), " txt ")]')
    if not text_nodes:
        return None

    full_nodes = card.xpath('.//p[@node-type="feed_list_content_full"]')
    text_node = full_nodes[0] if full_nodes else text_nodes[0]
    text = clean_text(text_node.xpath("string(.)"))
    location = get_location(text_node)
    if location:
        text = text.replace("2" + location, "")
    if text.startswith("展开"):
        text = text[2:]
    if text.endswith("收起全文"):
        text = text[:-4]

    pics = []
    for src in card.xpath('.//div[contains(@class,"media-piclist")]//img/@src'):
        pic = normalize_pic_url(src)
        if pic:
            pics.append(pic)

    video_url = ""
    video_player = first_text(card, './/div[contains(@class,"thumbnail")]//video-player')
    match = re.search(r"src:'(.*?)'", video_player)
    if match:
        video_url = "http:" + match.group(1).replace("&amp;", "&")

    raw_id = first_attr(card, "./@mid")
    item = {
        "_key": f"weibo:{raw_id}" if raw_id else "",
        "note_id": f"weibo:{raw_id}" if raw_id else "",
        "id": f"weibo_{raw_id}" if raw_id else "",
        "original_id": raw_id,
        "platform": "weibo",
        "platform_name": "微博",
        "bid": from_href.split("/")[-1].split("?")[0] if from_href else "",
        "user_id": user_href.split("?")[0].rstrip("/").split("/")[-1] if user_href else "",
        "screen_name": first_attr(info, ".//a[1]/@nick-name") or first_text(info, ".//a[1]"),
        "text": text,
        "article_url": get_article_url(text_node),
        "location": location,
        "at_users": get_at_users(text_node),
        "topics": get_topics(text_node),
        "reposts_count": parse_count("".join(card.xpath('.//a[@action-type="feed_list_forward"]/text()'))),
        "comments_count": parse_count(first_text(card, './/a[@action-type="feed_list_comment"]/text()')),
        "attitudes_count": parse_count(first_text(card, '(.//span[contains(@class,"woo-like-count")])[last()]/text()')),
        "created_at": standardize_date(first_text(card, './/div[contains(@class,"from")]/a[1]/text()')),
        "source": first_text(card, './/div[contains(@class,"from")]/a[2]/text()'),
        "pics": pics,
        "video_url": video_url,
        "retweet_id": "",
        "crawl_keyword": unquote(crawl_keyword).replace("%23", "#"),
        "keyword": "",
        "matched_keywords": [],
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return item


class SeenStore:
    def __init__(self, file_name):
        self.path = resolve_crawler_path(file_name)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ids = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as file:
                self.ids = {line.strip() for line in file if line.strip()}

    def has(self, weibo_id):
        return weibo_id in self.ids

    def add(self, weibo_id):
        if not weibo_id or weibo_id in self.ids:
            return
        self.ids.add(weibo_id)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(weibo_id + "\n")


class KeyController:
    def __init__(self):
        self.paused = False
        self.stopped = False

    def poll(self):
        key = read_key()
        if key == "s":
            self.paused = True
            print("已暂停，按 b 继续，按 c 退出。")
        elif key == "b":
            self.paused = False
            print("继续爬取。")
        elif key == "c":
            self.stopped = True
            print("准备退出。")

    def wait_if_paused(self):
        while self.paused and not self.stopped:
            self.poll()
            time.sleep(0.1)


def read_key():
    if os.name == "nt":
        import msvcrt

        if msvcrt.kbhit():
            return msvcrt.getwch().lower()
        return ""

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1).lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ""


def fetch(session, url):
    last_error = None
    for index in range(1, setting.MAX_RETRY + 1):
        try:
            response = session.get(url, timeout=setting.REQUEST_TIMEOUT)
            response.raise_for_status()
            if "card-wrap" not in response.text and "登录" in response.text:
                print("页面像是要求登录了，请检查 setting.py 里的 cookie 是否有效。")
            return response.text
        except Exception as exc:
            last_error = exc
            print(f"请求失败，第 {index}/{setting.MAX_RETRY} 次: {exc}")
            time.sleep(setting.DOWNLOAD_DELAY)
    raise RuntimeError(last_error)


def summarize_search_page(page_text):
    text = str(page_text or "")
    if not text:
        return "empty response"
    title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    title = clean_text(title_match.group(1)) if title_match else ""
    retcode_match = re.search(r"retcode=(\d+)", text)
    retcode = retcode_match.group(1) if retcode_match else ""
    markers = []
    if "新浪通行证" in text:
        markers.append("passport_redirect")
    if "验证码" in text:
        markers.append("captcha")
    if "登录" in text:
        markers.append("login")
    if "未找到相关结果" in text:
        markers.append("no_result")
    if "card-wrap" in text:
        markers.append("has_card_wrap")
    parts = []
    if title:
        parts.append(f"title={title}")
    if retcode:
        parts.append(f"retcode={retcode}")
    if markers:
        parts.append("markers=" + ",".join(markers))
    if not parts:
        snippet = clean_text(text[:160])
        parts.append(f"snippet={snippet}")
    return "; ".join(parts)


def build_crawl_states(crawl_keywords):
    states = [{"keyword": keyword, "next_page": 1} for keyword in crawl_keywords]
    if getattr(setting, "RANDOMIZE_CRAWL_ORDER", True):
        random.shuffle(states)
    return states


def pick_crawl_state(states):
    if getattr(setting, "RANDOMIZE_CRAWL_ORDER", True):
        return random.choice(states)
    return states[0]


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


def run_crawler(controller=None, log=print, progress=None, item_callback=None):
    start_date, end_date = get_date_range()
    filter_keywords = read_plain_keywords(setting.KEYWORD_LIST)
    crawl_keyword_source = getattr(setting, "CRAWL_KEYWORD_LIST", []) or setting.KEYWORD_LIST
    crawl_keywords = read_keywords(crawl_keyword_source)
    seen = SeenStore(setting.SEEN_IDS_FILE)
    if controller is None:
        controller = KeyController()
    session = requests.Session()
    session.trust_env = bool(getattr(setting, "TRUST_ENV_PROXY", False))
    session.headers.update(setting.DEFAULT_REQUEST_HEADERS)

    client = MongoClient(setting.MONGO_URI)
    collection = client[setting.MONGO_DATABASE][setting.MONGO_COLLECTION]
    ensure_index(collection, "id", unique=True)

    recent_days = int(getattr(setting, "RECENT_DAYS", 60) or 60)

    log(f"?????? {recent_days} ?: {start_date} ? {end_date}")
    log(f"正文筛选关键词 {len(filter_keywords)} 个，发现搜索词 {len(crawl_keywords)} 个。")
    log("开始爬取。")
    inserted = 0
    skipped = 0
    discarded = 0
    unmatched = 0
    max_items = int(getattr(setting, "MAX_ITEMS_PER_RUN", 50) or 0)

    def report_progress():
        if progress:
            progress(
                {
                    "inserted": inserted,
                    "skipped": skipped,
                    "unmatched": unmatched,
                    "discarded": discarded,
                }
            )

    report_progress()

    try:
        crawl_states = build_crawl_states(crawl_keywords)
        while crawl_states and (max_items <= 0 or inserted < max_items):
            controller.poll()
            controller.wait_if_paused()
            if controller.stopped:
                raise KeyboardInterrupt

            state = pick_crawl_state(crawl_states)
            crawl_keyword = state["keyword"]
            page = state["next_page"]
            state["next_page"] += 1

            log(f"发现搜索词: {unquote(crawl_keyword)}，第 {page} 页")
            url = build_url(crawl_keyword, page, start_date, end_date)
            log(f"抓取第 {page} 页: {url}")
            page_text = fetch(session, url)
            items = list(parse_weibos(page_text, crawl_keyword))
            if not items:
                crawl_states.remove(state)
                log(f"发现搜索词 {unquote(crawl_keyword)} 已无更多结果，移出随机池。")
                log(f"微博原始返回摘要: {summarize_search_page(page_text)}")
                continue
            if state["next_page"] > setting.MAX_PAGES:
                crawl_states.remove(state)

            operations = []
            pending_analysis = []
            for item in items:
                if max_items > 0 and inserted >= max_items:
                    break
                controller.poll()
                controller.wait_if_paused()
                if controller.stopped:
                    raise KeyboardInterrupt

                if seen.has(item["id"]):
                    skipped += 1
                    report_progress()
                    continue
                if not item.get("id"):
                    discarded += 1
                    report_progress()
                    log("丢弃缺少 id 的微博。")
                    continue
                if not item.get("text", "").strip():
                    discarded += 1
                    seen.add(item["id"])
                    report_progress()
                    log(f"丢弃无正文微博: {item.get('id', '')}")
                    continue
                if getattr(setting, "REQUIRE_IMAGES", True) and not item.get("pics"):
                    discarded += 1
                    seen.add(item["id"])
                    report_progress()
                    log(f"丢弃无图片微博: {item.get('id', '')}")
                    continue
                matched_keywords = match_filter_keywords(item, filter_keywords)
                if getattr(setting, "REQUIRE_KEYWORD_MATCH", True) and not matched_keywords:
                    unmatched += 1
                    report_progress()
                    continue
                if not should_keep_by_age(item):
                    discarded += 1
                    report_progress()
                    continue
                item["matched_keywords"] = matched_keywords
                item["keyword"] = ",".join(matched_keywords)
                item["pics"] = download_pics(session, item)
                if getattr(setting, "REQUIRE_IMAGES", True) and not item["pics"]:
                    discarded += 1
                    seen.add(item["id"])
                    report_progress()
                    log(f"丢弃图片下载失败微博: {item.get('id', '')}")
                    continue
                operations.append(UpdateOne({"id": item["id"]}, {"$set": item}, upsert=True))
                pending_analysis.append(item)
                seen.add(item["id"])
                inserted += 1
                report_progress()

            if operations:
                collection.bulk_write(operations, ordered=False)
                log(
                    f"本页写入 {len(operations)} 条，累计写入 {inserted} 条，"
                    f"跳过重复 {skipped} 条，未命中关键词 {unmatched} 条，按时间丢弃 {discarded} 条。"
                )
                if item_callback:
                    for item in pending_analysis:
                        try:
                            item_callback(item)
                        except Exception as exc:
                            item["analysis_status"] = "error"
                            item["analysis_error"] = str(exc)
                            log(f"多模态分析失败，微博 {item['id']}: {exc}")
                        write_analysis_fields(collection, item)
            else:
                log(
                    f"本页没有写入，累计跳过重复 {skipped} 条，"
                    f"未命中关键词 {unmatched} 条，按时间丢弃 {discarded} 条。"
                )

            time.sleep(setting.DOWNLOAD_DELAY)
        if max_items > 0 and inserted >= max_items:
            log(f"已达到本平台本轮上限 {max_items} 条，停止微博爬取。")
    except KeyboardInterrupt:
        log("已退出。")
    finally:
        client.close()
        log(
            f"完成。写入/更新 {inserted} 条，跳过重复 {skipped} 条，"
            f"未命中关键词 {unmatched} 条，按时间丢弃 {discarded} 条。"
        )
        report_progress()
    return {
        "inserted": inserted,
        "skipped": skipped,
        "unmatched": unmatched,
        "discarded": discarded,
    }


def main():
    run_crawler()


if __name__ == "__main__":
    main()
