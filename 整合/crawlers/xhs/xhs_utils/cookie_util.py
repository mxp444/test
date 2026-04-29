def trans_cookies(cookies_str):
    cookies_str = str(cookies_str or "").strip()
    if not cookies_str:
        return {}
    if '; ' in cookies_str:
        ck = {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookies_str.split('; ')}
    else:
        ck = {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookies_str.split(';')}
    return {key: value for key, value in ck.items() if key}
