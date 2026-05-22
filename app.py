"""小红书爆款选题拆解工具 —— 本地网页版。"""
import os
import tempfile
import threading
import uuid
from flask import Flask, render_template, request, jsonify

from scraper import fetch_note
from analyzer import analyze, correct_transcript
from video import download_video, extract_audio, transcribe

app = Flask(__name__)

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "xhs_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

tasks = {}


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

    if not link:
        return jsonify(ok=False, error="请输入链接")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "result": None, "error": None}

    def run():
        try:
            video_path = download_video(link, cookie=cookie)
            audio_path = extract_audio(video_path)
            result = transcribe(audio_path)
            _cleanup(video_path, audio_path)
            tasks[task_id]["result"] = result
            tasks[task_id]["status"] = "done"
        except Exception as e:
            tasks[task_id]["error"] = str(e)
            tasks[task_id]["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True, task_id=task_id)


@app.route("/transcribe_upload", methods=["POST"])
def transcribe_upload():
    file = request.files.get("video")
    if not file:
        return jsonify(ok=False, error="请上传视频文件")

    video_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(video_path)

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "result": None, "error": None}

    def run():
        try:
            audio_path = extract_audio(video_path)
            result = transcribe(audio_path)
            _cleanup(video_path, audio_path)
            tasks[task_id]["result"] = result
            tasks[task_id]["status"] = "done"
        except Exception as e:
            tasks[task_id]["error"] = str(e)
            tasks[task_id]["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True, task_id=task_id)


@app.route("/task/<task_id>")
def get_task(task_id):
    t = tasks.get(task_id)
    if not t:
        return jsonify(ok=False, error="任务不存在")
    if t["status"] == "processing":
        return jsonify(ok=True, status="processing")
    if t["status"] == "error":
        tasks.pop(task_id, None)
        return jsonify(ok=False, error=t["error"])
    result = t["result"]
    tasks.pop(task_id, None)
    return jsonify(ok=True, status="done", **result)


@app.route("/correct", methods=["POST"])
def do_correct():
    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    api_key = (data.get("api_key") or "").strip() or None
    if not content:
        return jsonify(ok=False, error="逐字稿为空，无法纠错")
    try:
        corrected = correct_transcript(content, api_key=api_key)
        return jsonify(ok=True, content=corrected)
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
