"""调用 AI 大模型对小红书笔记做四维拆解 + 逐字稿纠错。"""
import os
import json
import requests

# SiliconFlow API（兼容 OpenAI 格式）
SF_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
SF_MODEL = "deepseek-ai/DeepSeek-V2.5"

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


CORRECT_SYSTEM = """你是中文逐字稿校对专家，专门修正语音识别（ASR）产生的同音/近音错别字。
你只做纠错，绝不改写、润色、增删内容，也不改变说话人的原意和口语风格。"""

CORRECT_PROMPT = """下面是一段语音识别得到的中文逐字稿，存在同音或近音错别字（例如把"兴奋"识别成"新分"、"上瘾"识别成"上引"）。

请结合上下文，只修正这类识别错误，严格遵守：
1. 不要改写句子、不要润色、不要增删字数和内容；
2. 保留原有的口语表达和语气；
3. 完整保留原文的换行结构（有几行就输出几行）；
4. 只输出修正后的逐字稿全文，不要任何解释或额外文字。

【逐字稿】
{content}"""


def _sf_key():
    return os.environ.get("SILICONFLOW_API_KEY")


def _call_sf(system, user_msg, max_tokens=4000):
    """调用 SiliconFlow API（OpenAI 兼容格式）。"""
    key = _sf_key()
    if not key:
        raise RuntimeError("缺少 SILICONFLOW_API_KEY，请在 Railway Variables 中配置。")

    resp = requests.post(
        SF_API_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": SF_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API 调用失败 {resp.status_code}: {resp.text[:300]}")

    return resp.json()["choices"][0]["message"]["content"].strip()


def correct_transcript(content, api_key=None):
    """用 AI 修正逐字稿中的同音/近音错别字。"""
    if not (content or "").strip():
        return content
    return _call_sf(CORRECT_SYSTEM, CORRECT_PROMPT.format(content=content), max_tokens=8000)


def analyze(title, content, api_key=None):
    """四维拆解分析。"""
    text = _call_sf(SYSTEM, PROMPT.format(title=title or "(无标题)", content=content))
    # 提取 JSON 部分
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    # 尝试找到 JSON 对象
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试修复常见问题：末尾多余逗号
        import re
        text = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"AI 返回的格式有误，请重试。原文：{text[:200]}")
