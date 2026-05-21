"""调用 Claude 对小红书笔记做四维拆解（直接走 HTTP，无需 anthropic SDK）。"""
import os
import json
import requests

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

SYSTEM = """你是资深的小红书内容运营，擅长拆解爆款笔记的底层规律。
你会收到一篇笔记的标题和正文，请从专业运营视角拆解它为什么能成为爆款。
只输出 JSON，不要任何额外文字。"""

PROMPT = """请拆解下面这篇小红书笔记，严格按以下 JSON 结构输出（所有内容用中文）：

{{
  "title_tactics": {{
    "hook_types": ["命中的标题钩子类型，如 数字党/痛点型/悬念型/对比型/身份认同/利益承诺"],
    "analysis": "标题为什么吸引人，用了什么技巧，2-4句"
  }},
  "structure": {{
    "outline": ["正文的结构骨架，按顺序列出每一段在做什么，如 开头抛痛点 / 给方案 / 行动号召"],
    "analysis": "内容结构的节奏和说服逻辑，2-4句"
  }},
  "keywords_tags": {{
    "keywords": ["正文里的核心关键词/SEO词"],
    "suggested_tags": ["建议带的话题标签，不含#号"]
  }},
  "angle_audience": {{
    "target_audience": "这条笔记切的是什么人群",
    "core_need": "满足了什么需求或痛点",
    "emotion": "调动了什么情绪",
    "angle": "选题切入角度，以及可复用的选题公式"
  }},
  "replicable_takeaway": "给想复刻这篇爆款的创作者一句最关键的可执行建议"
}}

标题：{title}

正文：
{content}"""


def analyze(title, content, api_key=None):
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("缺少 ANTHROPIC_API_KEY，请先配置 API key。")

    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 2000,
            "system": SYSTEM,
            "messages": [{
                "role": "user",
                "content": PROMPT.format(title=title or "(无标题)", content=content),
            }],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API 调用失败 {resp.status_code}: {resp.text[:300]}")

    text = resp.json()["content"][0]["text"].strip()
    # 模型偶尔会用 ```json 包裹，去掉
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)
