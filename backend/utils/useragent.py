# backend/utils/useragent.py
"""Tiny, dependency-free User-Agent classifier (good enough for an admin UI)."""
import re

_BOTS = re.compile(r'bot|crawl|spider|curl|wget|python-requests|httpx|postman|insomnia|scrapy|go-http', re.I)


def parse_user_agent(ua):
    """Return {'browser', 'os', 'device'} for a User-Agent string."""
    if not ua:
        return {'browser': 'Unknown', 'os': 'Unknown', 'device': 'unknown'}

    if _BOTS.search(ua):
        device = 'bot'
    elif re.search(r'iPad|Tablet|Nexus 7|SM-T', ua, re.I):
        device = 'tablet'
    elif re.search(r'Mobi|iPhone|Android', ua, re.I):
        device = 'mobile'
    else:
        device = 'desktop'

    if re.search(r'Edg(e|A|iOS)?/', ua):
        browser = 'Edge'
    elif re.search(r'OPR/|Opera', ua):
        browser = 'Opera'
    elif re.search(r'Firefox/|FxiOS', ua):
        browser = 'Firefox'
    elif re.search(r'Chrome/|CriOS', ua):
        browser = 'Chrome'
    elif re.search(r'Safari/', ua):
        browser = 'Safari'
    elif device == 'bot':
        m = re.search(r'(curl|wget|python-requests|httpx|postman|insomnia|scrapy|go-http-client)', ua, re.I)
        browser = m.group(1) if m else 'Bot'
    else:
        browser = 'Unknown'

    if re.search(r'Windows', ua):
        os_name = 'Windows'
    elif re.search(r'Android', ua):
        os_name = 'Android'
    elif re.search(r'iPhone|iPad|iOS', ua):
        os_name = 'iOS'
    elif re.search(r'Mac OS X|Macintosh', ua):
        os_name = 'macOS'
    elif re.search(r'Linux|X11', ua):
        os_name = 'Linux'
    else:
        os_name = 'Unknown'

    return {'browser': browser, 'os': os_name, 'device': device}


def describe_user_agent(ua):
    info = parse_user_agent(ua)
    if info['browser'] == 'Unknown' and info['os'] == 'Unknown':
        return 'Unknown device'
    return f"{info['browser']} on {info['os']}"
