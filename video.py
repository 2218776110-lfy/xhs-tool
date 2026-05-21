"""视频下载（小红书链接 / 本地文件）+ Whisper 语音识别转逐字稿。"""
import os
import re
import tempfile
import subprocess
import requests

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("[Whisper] 加载模型 base ...")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        print("[Whisper] 模型加载完成")
    return _whisper_model


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
    """用 faster-whisper 本地识别，返回逐字稿。"""
    model = _get_model()
    print(f"[Whisper] 开始识别: {audio_path} ({os.path.getsize(audio_path)} bytes)")

    segments_iter, info = model.transcribe(
        audio_path, language="zh", beam_size=3, vad_filter=True
    )
    print(f"[Whisper] 语言: {info.language}, 时长: {info.duration:.1f}s")

    all_text = []
    all_segments = []
    for seg in segments_iter:
        all_text.append(seg.text)
        all_segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })
        print(f"[Whisper] [{seg.start:.1f}-{seg.end:.1f}] {seg.text}")

    final_text = "".join(all_text).strip()
    print(f"[Whisper] 识别完成，文本长度: {len(final_text)}")

    if not final_text:
        raise RuntimeError("语音识别完成但未识别到文字，可能原因：视频无人声或音频质量差")

    return {
        "text": final_text,
        "segments": all_segments,
        "duration": info.duration,
    }


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
