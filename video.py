"""视频下载（小红书链接 / 本地文件）+ 阿里云语音识别转逐字稿。"""
import os
import re
import json
import time
import hmac
import hashlib
import base64
import uuid
import tempfile
import subprocess
import urllib.parse
from datetime import datetime, timezone
import requests

ALI_FILETRANS_URL = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/FlowRecognizer"


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
    """用 ffmpeg 从视频提取音频（wav 16kHz 单声道，阿里云要求）。"""
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


def transcribe(audio_path, appkey, ak_id=None, ak_secret=None):
    """调用阿里云一句话识别 / 录音文件识别，返回逐字稿。

    对于短音频（<60s）用实时识别，长音频用录音文件转写。
    这里统一用流式一句话识别的简化方案：直接 POST 音频数据。
    """
    if not appkey:
        raise RuntimeError("缺少阿里云 AppKey")

    ak_id = ak_id or os.environ.get("ALI_AK_ID")
    ak_secret = ak_secret or os.environ.get("ALI_AK_SECRET")

    token = _get_ali_token(ak_id, ak_secret) if ak_id and ak_secret else os.environ.get("ALI_TOKEN")
    if not token:
        raise RuntimeError("缺少阿里云 Token（需要 AccessKey ID + Secret，或直接提供 Token）")

    file_size = os.path.getsize(audio_path)

    if file_size > 2 * 1024 * 1024:
        return _transcribe_filetrans(audio_path, appkey, ak_id, ak_secret)

    return _transcribe_short(audio_path, appkey, token)


def _transcribe_short(audio_path, appkey, token):
    """一句话识别（<60s 短音频）。"""
    url = (
        f"https://nls-gateway-cn-shanghai.aliyuncs.com"
        f"/stream/v1/asr"
        f"?appkey={appkey}"
        f"&format=pcm&sample_rate=16000"
        f"&enable_punctuation_prediction=true"
        f"&enable_inverse_text_normalization=true"
    )
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    resp = requests.post(
        url,
        headers={
            "X-NLS-Token": token,
            "Content-Type": "application/octet-stream",
        },
        data=audio_data,
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"阿里云识别失败 {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    if data.get("status") != 20000000:
        raise RuntimeError(f"识别错误: {data.get('message', data)}")

    text = data.get("result", "")
    return {"text": text, "segments": [], "duration": 0}


def _transcribe_filetrans(audio_path, appkey, ak_id, ak_secret):
    """录音文件识别（长音频），需要先上传再轮询结果。
    简化方案：把长音频切成多段短音频分别识别。
    """
    chunk_dir = tempfile.mkdtemp(prefix="xhs_chunks_")
    cmd = [
        "ffmpeg", "-i", audio_path,
        "-f", "segment", "-segment_time", "55",
        "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        os.path.join(chunk_dir, "chunk_%03d.wav"),
    ]
    subprocess.run(cmd, capture_output=True, timeout=120, check=True)

    chunks = sorted(f for f in os.listdir(chunk_dir) if f.endswith(".wav"))

    token = _get_ali_token(ak_id, ak_secret)
    all_text = []
    all_segments = []
    offset = 0.0

    for chunk_name in chunks:
        chunk_path = os.path.join(chunk_dir, chunk_name)
        result = _transcribe_short(chunk_path, appkey, token)
        text = result["text"]
        if text:
            all_text.append(text)
            all_segments.append({
                "start": offset,
                "end": offset + 55,
                "text": text,
            })
        offset += 55

    return {
        "text": "".join(all_text),
        "segments": all_segments,
        "duration": offset,
    }


def _get_ali_token(ak_id, ak_secret):
    """用 AccessKey 获取阿里云 NLS Token。"""
    if not ak_id or not ak_secret:
        raise RuntimeError("缺少阿里云 AccessKey ID / Secret")

    params = {
        "AccessKeyId": ak_id,
        "Action": "CreateToken",
        "Format": "JSON",
        "RegionId": "cn-shanghai",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2019-02-28",
    }

    sorted_params = sorted(params.items())
    query = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote)
    string_to_sign = "GET&%2F&" + urllib.parse.quote(query, safe="")

    sign = hmac.new(
        (ak_secret + "&").encode(),
        string_to_sign.encode(),
        hashlib.sha1,
    ).digest()
    signature = base64.b64encode(sign).decode()

    params["Signature"] = signature
    resp = requests.get("https://nls-meta.cn-shanghai.aliyuncs.com/", params=params, timeout=15)
    data = resp.json()

    token_obj = data.get("Token")
    if not token_obj:
        raise RuntimeError(f"获取 Token 失败: {data}")
    return token_obj["Id"]


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
