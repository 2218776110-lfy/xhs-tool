"""小红书爆款选题拆解工具 —— 本地网页版。"""
import os
import tempfile
from flask import Flask, render_template, request, jsonify

from scraper import fetch_note
from analyzer import analyze
from video import download_video, extract_audio, transcribe

app = Flask(__name__)

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "xhs_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.route("/")
def index():
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_ali = bool(os.environ.get("ALI_APPKEY"))
    return render_template("index.html", has_anthropic=has_anthropic, has_ali=has_ali)


@app.route("/fetch", methods=["POST"])
def fetch():
    data = request.get_json(force=True)
    link = (data.get("link") or "").strip()
    cookie = (data.get("cookie") or "").strip() or None
    if not link:
        return jsonify(ok=False, error="请输入链接")
    try:
        note = fetch_note(link, cookie=cookie)
        return jsonify(ok=True, **note)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/transcribe_link", methods=["POST"])
def transcribe_link():
    data = request.get_json(force=True)
    link = (data.get("link") or "").strip()
    cookie = (data.get("cookie") or "").strip() or None
    appkey = (data.get("ali_appkey") or "").strip() or os.environ.get("ALI_APPKEY")
    ak_id = (data.get("ali_ak_id") or "").strip() or os.environ.get("ALI_AK_ID")
    ak_secret = (data.get("ali_ak_secret") or "").strip() or os.environ.get("ALI_AK_SECRET")

    if not link:
        return jsonify(ok=False, error="请输入链接")
    if not appkey:
        return jsonify(ok=False, error="需要阿里云 AppKey 才能转写")

    try:
        video_path = download_video(link, cookie=cookie)
        audio_path = extract_audio(video_path)
        result = transcribe(audio_path, appkey, ak_id, ak_secret)
        _cleanup(video_path, audio_path)
        return jsonify(ok=True, **result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/transcribe_upload", methods=["POST"])
def transcribe_upload():
    appkey = request.form.get("ali_appkey", "").strip() or os.environ.get("ALI_APPKEY")
    ak_id = request.form.get("ali_ak_id", "").strip() or os.environ.get("ALI_AK_ID")
    ak_secret = request.form.get("ali_ak_secret", "").strip() or os.environ.get("ALI_AK_SECRET")

    if not appkey:
        return jsonify(ok=False, error="需要阿里云 AppKey 才能转写")

    file = request.files.get("video")
    if not file:
        return jsonify(ok=False, error="请上传视频文件")

    video_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(video_path)

    try:
        audio_path = extract_audio(video_path)
        result = transcribe(audio_path, appkey, ak_id, ak_secret)
        _cleanup(video_path, audio_path)
        return jsonify(ok=True, **result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/analyze", methods=["POST"])
def do_analyze():
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    api_key = (data.get("api_key") or "").strip() or None
    if not content:
        return jsonify(ok=False, error="正文为空，无法拆解")
    try:
        result = analyze(title, content, api_key=api_key)
        return jsonify(ok=True, result=result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


def _cleanup(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
