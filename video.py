"""视频下载（小红书链接 / 本地文件）+ SiliconFlow 语音识别转逐字稿。"""
import os
import re
import tempfile
import subprocess
import requests

_t2s = None


def _to_simplified(text):
    global _t2s
    if _t2s is None:
        from opencc import OpenCC
        _t2s = OpenCC('t2s')
    return _t2s.convert(text)


def download_video(url_or_share_text, cookie=None):
    """从小红书链接下载视频，返回本地临时文件路径。"""
    url = _extract_url(url_or_share_text)
    tmp = tempfile.mktemp(suffix=".mp4", prefix="xhs_")

    cmd = ["yt-dlp", "-o", tmp, "--no-warnings"]
    if cookie:
        cmd += ["--add-header", f"Cookie: {cookie}"]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        video_url = _scrape_video_url(url, cookie)
        if video_url:
            _download_direct(video_url, tmp, cookie)
        else:
            raise RuntimeError(
                f"视频下载失败。yt-dlp: {result.stderr[:300]}\n"
                "建议：手动下载视频后上传。"
            )
    return tmp


def extract_audio(video_path):
    """用 ffmpeg 从视频提取音频（wav 16kHz 单声道）。"""
    audio_path = video_path.rsplit(".", 1)[0] + ".wav"
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        "-y", audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"音频提取失败: {result.stderr[:300]}")
    return audio_path


def transcribe(audio_path, **kwargs):
    """用 SiliconFlow API 语音识别。"""
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 SILICONFLOW_API_KEY，请在 Railway Variables 中配置。")

    print(f"[转写] 音频: {audio_path} ({os.path.getsize(audio_path)} bytes)")
    print(f"[SiliconFlow] 发送音频到 SiliconFlow Whisper API...")

    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.siliconflow.cn/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(audio_path), f, "audio/wav")},
            data={
                "model": "FunAudioLLM/SenseVoiceSmall",
                "language": "zh",
                "response_format": "verbose_json",
            },
            timeout=180,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"语音识别失败 {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    text = _to_simplified(data.get("text", ""))
    segments = []
    for seg in data.get("segments", []):
        seg_text = _to_simplified(seg.get("text", ""))
        segments.append({
            "start": seg.get("start", 0),
            "end": seg.get("end", 0),
            "text": seg_text,
        })

    print(f"[SiliconFlow] 识别完成，文本长度: {len(text)}")

    if not text.strip():
        raise RuntimeError("语音识别完成但未识别到文字，可能原因：视频无人声或音频质量差")

    return {"text": text, "segments": segments, "duration": data.get("duration", 0)}


def _extract_url(text):
    m = re.search(r"https?://[^\s，,]+", text)
    return m.group(0) if m else text.strip()


def _scrape_video_url(url, cookie=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    }
    if cookie:
        headers["Cookie"] = cookie
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        m = re.search(r'"originVideoKey"\s*:\s*"([^"]+)"', resp.text)
        if m:
            return f"https://sns-video-bd.xhscdn.com/{m.group(1)}"
        m = re.search(r'<meta[^>]+name="og:video"[^>]+content="([^"]+)"', resp.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _download_direct(video_url, output_path, cookie=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }
    if cookie:
        headers["Cookie"] = cookie
    resp = requests.get(video_url, headers=headers, timeout=60, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
