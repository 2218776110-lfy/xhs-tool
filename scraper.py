"""小红书笔记抓取：尽力而为，失败时由前端回退到手动粘贴。"""
import re
import json
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _extract_url(text):
    """从用户粘贴的分享文案里抠出真正的链接。"""
    m = re.search(r"https?://[^\s，,]+", text)
    return m.group(0) if m else text.strip()


def fetch_note(raw_input, cookie=None):
    """返回 {title, content} 或抛出异常。

    小红书反爬较强，无登录态时常失败——调用方应捕获异常并回退到手动粘贴。
    """
    url = _extract_url(raw_input)
    headers = dict(HEADERS)
    if cookie:
        headers["Cookie"] = cookie

    resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    # 小红书页面把笔记数据塞在 window.__INITIAL_STATE__ 里
    title, content = _parse_initial_state(html)
    if content and _is_real_content(content):
        return {"title": title, "content": content, "source": "auto"}

    # 退而求其次：抓 og:title / meta description
    title = title or _meta(html, "og:title")
    desc = _meta(html, "description")
    if desc and _is_real_content(desc):
        return {"title": title or "", "content": desc, "source": "meta"}

    # 只拿到标题/标签但没有正文
    if title or content:
        return {"title": title or "", "content": "", "source": "partial"}

    raise ValueError("抓取不到正文，可能需要登录 cookie，请改用手动粘贴。")


def _parse_initial_state(html):
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if not m:
        return None, None
    raw = m.group(1).replace("undefined", "null")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, None
    # 结构会变，这里做宽松遍历找 title/desc
    title, content = _deep_find(data)
    return title, content


def _deep_find(obj):
    title = content = None
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if not title and isinstance(cur.get("title"), str) and cur["title"]:
                title = cur["title"]
            if not content and isinstance(cur.get("desc"), str) and len(cur.get("desc", "")) > 20:
                content = cur["desc"]
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return title, content


def _is_real_content(text):
    """判断文本是否是真正的正文（而不是纯标签/空内容）。"""
    cleaned = re.sub(r"#[^\s#\[\]]+(\[话题\])?", "", text).strip()
    return len(cleaned) > 30


def _meta(html, key):
    pat = rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']'
    m = re.search(pat, html, re.I)
    return m.group(1) if m else None
