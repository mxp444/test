# -*- coding: utf-8 -*-
"""
抖音图文爬虫配置。

给关键词后，后端会搜索抖音并筛选“内容形式=图文”的有图有文作品，
再按微博项目同款字段写入 MongoDB: test.test_douyin。
"""

MONGO_URI = "mongodb://localhost:27017"
MONGO_DATABASE = "test"
MONGO_COLLECTION = "test_douyin"

# 发现作品用的搜索关键词。为空时默认沿用 KEYWORD_LIST。
DOUYIN_SEARCH_KEYWORD_LIST = []

# 可选：抖音图文分享链接、作品链接或 aweme_id。每个元素一个作品，用于补采指定作品。
DOUYIN_URL_LIST = []

# 可选：如果你想用 txt 文件批量放链接，再把这里改成文件名；留空表示不用文件。
DOUYIN_URL_FILE = ""

# 抖音网页搜索接口通常需要登录态 cookie；没有 cookie 时常返回 verify_check 空结果。
# 可从浏览器打开 douyin.com，完成登录/验证后，在开发者工具 Network 里复制 Cookie。
# User-Agent 必须尽量和复制 Cookie 的浏览器一致，否则 Cookie 有效也可能触发 verify_check。
DOUYIN_COOKIE = 'enter_pc_once=1; UIFID_TEMP=26198ff38959f773c63a6fc9b3542e2fdcfd2f10d2782124ed1adc24709862dfa937c33d0a5d22241cfaadd87400bdc61541f635ee38d9af53ea82a4a7321220fd80e9aa83e4ba170bb08267b7848cc6; hevc_supported=true; fpk1=U2FsdGVkX19c9lgpN17Kc38jQRAHsrvCVdmfMtqIwHiWKPMzvDBKaIyT0D+rhtctfVYARxc0BISQskbUUlLS5Q==; fpk2=ffc3218438300d069a0fd5dfa5c6e851; bd_ticket_guard_client_web_domain=2; passport_csrf_token=2ea91eda3ea99cf47d0d8bb9e0050806; passport_csrf_token_default=2ea91eda3ea99cf47d0d8bb9e0050806; s_v_web_id=verify_mnswsumn_qYhZ9hqj_KikQ_4lll_8FfC_u9b94d6gMQsX; SEARCH_UN_LOGIN_PV_CURR_DAY=%7B%22date%22%3A1775825797766%2C%22count%22%3A2%7D; passport_mfa_token=CjdMMDBeN6ilcwnrlChP%2BfGg2cE7XQ65kdDBufbaCXZq0kp%2F6zExlB%2BdMzLIrpiHYfXTc7%2BwLQuaGkoKPAAAAAAAAAAAAABQSQsP%2BsycyvijCVe6QArzoGmOmkpzi1lpjaw9vgIu037VH62lZ3IkimM6MbBmCEkiBxDXuY4OGPax0WwgAiIBAyrWZh0%3D; d_ticket=5778b720bcf4c9594f75a5f2547624874b1cb; passport_assist_user=CkElFpxpQc8qf1FNTxTeDndfRa_taLIJbUAN7Od56yWvhi09rIw-0-kouN3CS0Xm-D9Bz1wrPGq-gMyniyZZuSgIHBpKCjwAAAAAAAAAAAAAUEnHrGt6ELAcfQX_Cyf4RHPwBnXYDSrqV3SKrrv_HPhjE31l0EfHuQGAKswlFvpwFYEQh7uODhiJr9ZUIAEiAQPyvGt4; n_mh=nXx8eqmqp7CzqjBIKa7_6lrhO3RByhp9yLkNpmrc1yI; uid_tt=39678521d4d549bac7f330fc800bccce; uid_tt_ss=39678521d4d549bac7f330fc800bccce; sid_tt=8cf33203deeafa27ce7a48417d6eb8a7; sessionid=8cf33203deeafa27ce7a48417d6eb8a7; sessionid_ss=8cf33203deeafa27ce7a48417d6eb8a7; is_staff_user=false; has_biz_token=false; _bd_ticket_crypt_cookie=780c8f3eb53e6bb46c9521f7a850f969; __security_server_data_status=1; login_time=1775825848354; SEARCH_RESULT_LIST_TYPE=%22single%22; UIFID=26198ff38959f773c63a6fc9b3542e2fdcfd2f10d2782124ed1adc24709862df5da61dadcd78879900335c1420ca6c33d70a197b712a91032783026fa7612d27e68a415b67941dceb14e5415fef19e2e0b09345bd9fe1ff4040eeb0bc6bcf0469c22ce9ad98314978a935dab44e3e79a0ba0173eada98c783c92248ff902eebd596158424f87a46592659e6457f42101b98da77a3d46df45f636c605a54e8352; PhoneResumeUidCacheV1=%7B%223567248407540525%22%3A%7B%22time%22%3A1775825891664%2C%22noClick%22%3A1%7D%7D; my_rd=2; dy_swidth=1707; dy_sheight=1067; is_dash_user=1; publish_badge_show_info=%220%2C0%2C0%2C1778061849021%22; sid_guard=8cf33203deeafa27ce7a48417d6eb8a7%7C1778061851%7C5183999%7CSun%2C+05-Jul-2026+10%3A04%3A10+GMT; session_tlb_tag=sttt%7C6%7CjPMyA97q-ifOekhBfW64p_________-_tnC-7rPisZseMf25Z2Q5X2FOmT6LTLlD5LypJ1lI0V8%3D; sid_ucp_v1=1.0.0-KGVlYTM1OTgyZjJkMGUyNDkzNmVjMDZhM2Q4YThiN2U4YmMzM2E3OTcKIQit5qDxy4yrBhCbpOzPBhjvMSAMMIvFr5oGOAdA9AdIBBoCaGwiIDhjZjMzMjAzZGVlYWZhMjdjZTdhNDg0MTdkNmViOGE3; ssid_ucp_v1=1.0.0-KGVlYTM1OTgyZjJkMGUyNDkzNmVjMDZhM2Q4YThiN2U4YmMzM2E3OTcKIQit5qDxy4yrBhCbpOzPBhjvMSAMMIvFr5oGOAdA9AdIBBoCaGwiIDhjZjMzMjAzZGVlYWZhMjdjZTdhNDg0MTdkNmViOGE3; __security_mc_1_s_sdk_crypt_sdk=bddf9703-4bbf-a226; __security_mc_1_s_sdk_cert_key=7bbbd574-4000-94a1; __security_mc_1_s_sdk_sign_data_key_web_protect=6d1a8fd1-43b0-952a; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Afalse%2C%22volume%22%3A0.49%7D; SelfTabRedDotControl=%5B%7B%22id%22%3A%227535455773527115802%22%2C%22u%22%3A97%2C%22c%22%3A96%7D%5D; download_guide=%223%2F20260506%2F1%22; __druidClientInfo=JTdCJTIyY2xpZW50V2lkdGglMjIlM0E0ODUlMkMlMjJjbGllbnRIZWlnaHQlMjIlM0E4OTElMkMlMjJ3aWR0aCUyMiUzQTQ4NSUyQyUyMmhlaWdodCUyMiUzQTg5MSUyQyUyMmRldmljZVBpeGVsUmF0aW8lMjIlM0ExLjUlMkMlMjJ1c2VyQWdlbnQlMjIlM0ElMjJNb3ppbGxhJTJGNS4wJTIwKFdpbmRvd3MlMjBOVCUyMDEwLjAlM0IlMjBXaW42NCUzQiUyMHg2NCklMjBBcHBsZVdlYktpdCUyRjUzNy4zNiUyMChLSFRNTCUyQyUyMGxpa2UlMjBHZWNrbyklMjBDaHJvbWUlMkYxMzEuMC4wLjAlMjBTYWZhcmklMkY1MzcuMzYlMjBFZGclMkYxMzEuMC4wLjAlMjIlN0Q=; __ac_signature=_02B4Z6wo00f01x1OeKQAAIDCSBNVhsMOAEsdbnwAAK6zd0; douyin.com; device_web_cpu_core=32; device_web_memory_size=8; architecture=amd64; is_support_rtm_web_ts=1; FOLLOW_LIVE_POINT_INFO=%22MS4wLjABAAAAW8yVgn3I3hp4wAJjDa5t-KsvI2APam2i0uIl7hU-mRLTV0kMjR3sBCjEElOvVbfp%2F1778169600000%2F0%2F0%2F1778159180437%22; playRecommendGuideTagCount=3; totalRecommendGuideTagCount=18; IsDouyinActive=true; home_can_add_dy_2_desktop=%220%22; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1707%2C%5C%22screen_height%5C%22%3A1067%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A32%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A50%7D%22; strategyABtestKey=%221778228391.626%22; FOLLOW_NUMBER_YELLOW_POINT_INFO=%22MS4wLjABAAAAW8yVgn3I3hp4wAJjDa5t-KsvI2APam2i0uIl7hU-mRLTV0kMjR3sBCjEElOvVbfp%2F1778256000000%2F0%2F1778228392015%2F0%22; ttwid=1%7CMVys6cT7Cw6L7i2FMsj8ubYqyuUYqWVN29cKt0navO4%7C1778228394%7C768a6c626282e7041bcc462a9b0f303f482de559b3c2e5447cd2c20fa9316dc1; biz_trace_id=43d31752; bd_ticket_guard_client_data=eyJiZC10aWNrZXQtZ3VhcmQtdmVyc2lvbiI6MiwiYmQtdGlja2V0LWd1YXJkLWl0ZXJhdGlvbi12ZXJzaW9uIjoxLCJiZC10aWNrZXQtZ3VhcmQtcmVlLXB1YmxpYy1rZXkiOiJCT0pVUWpvQ1hJMGhhbmVUQzF4NGNpblNuTzZIRU9DZjM1MG1CZEVtbmt0M043S0JnWDRsQ3o0WGYwQlJIa3JmQnVYekJ1T3R2WjRZTVR5dG5IZ053aHc9IiwiYmQtdGlja2V0LWd1YXJkLXdlYi12ZXJzaW9uIjoyfQ%3D%3D; bd_ticket_guard_client_data_v2=eyJyZWVfcHVibGljX2tleSI6IkJPSlVRam9DWEkwaGFuZVRDMXg0Y2luU25PNkhFT0NmMzUwbUJkRW1ua3QzTjdLQmdYNGxDejRYZjBCUkhrcmZCdVh6QnVPdHZaNFlNVHl0bkhnTndodz0iLCJ0c19zaWduIjoidHMuMi44ZjdiZGU1ODY5NGE4NTdmMWNhN2U1Yjc2YWRkYjdkNGMzYWE4MTExYTZiNTUyNDBhYTNhYThiMmNjMjVlM2EzYzRmYmU4N2QyMzE5Y2YwNTMxODYyNGNlZGExNDkxMWNhNDA2ZGVkYmViZWRkYjJlMzBmY2U4ZDRmYTAyNTc1ZCIsInJlcV9jb250ZW50Ijoic2VjX3RzIiwicmVxX3NpZ24iOiJSRXZTK09XOUJrdXBnbm5OMU15WkV3MFlINTZidElkL0s2V3hkUU42SWE4PSIsInNlY190cyI6IiM2NVYwZFlNK0MvUTA1bkI0TkhUcUVqWStNWjZKMXdNRVpFYzJOeldlTVhxOWJQNldRQ0ZGQjBFa2Fhc2MifQ%3D%3D; odin_tt=a82da1bdf96a754b580098bfe2509f126bf660c6431555d598c0efd4543eeb60fd43ac6262df9d177dfc5c13c52df1f2b48e5e9d36477e9c70b4d55b6f51de67'

DEFAULT_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.douyin.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' 
        'AppleWebKit/537.36 (KHTML, like Gecko)'
        'Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'
    ),
}

REQUEST_TIMEOUT = 15
MAX_RETRY = 3
DOWNLOAD_DELAY = 5
IMAGE_TIMEOUT = 30
TRUST_ENV_PROXY = False

# 搜索页配置。CONTENT_TYPE=2 对应抖音筛选里的“图文”。
MAX_PAGES_PER_KEYWORD = 3
SEARCH_COUNT = 30
SORT_TYPE = "0"  # 0 综合排序，1 最多点赞，2 最新发布
PUBLISH_TIME = "0"  # 0 不限，1 一天内，7 一周内，180 半年内
FILTER_DURATION = "0"
CONTENT_TYPE = "2"

# 图文采集：只保存“内容形式=图文”且“有图有文”的作品。
REQUIRE_IMAGE_TEXT = True
REQUIRE_IMAGES = True
REQUIRE_TEXT = True

# 关键词过滤。设 REQUIRE_KEYWORD_MATCH=False 可抓到就存。
REQUIRE_KEYWORD_MATCH = False
KEYWORD_LIST = [
    "保本",
    "稳赚",
    "日赚",
    "区块链",
    "拉人头",
    "限时优惠",
    "返利",
    "理财",
    "众筹",
    "炒股",
    "外汇",
    "期货",
    "原始股",
    "无风险",
]

RESULT_DIR = "result"
PIC_DIR = "pic"
SEEN_IDS_FILE = "seen_ids.txt"
