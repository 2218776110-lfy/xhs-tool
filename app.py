"""视频文案提取工具 —— 支持任意平台视频链接。"""
import io
import os
import tempfile
import threading
import uuid
from flask import Flask, render_template, request, jsonify, send_file

from analyzer import correct_transcript
from video import download_video, extract_audio, transcribe, get_video_title, get_comments

app = Flask(__name__)

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "xhs_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

tasks = {}


@app.route("/")
def index():
    return render_template("index.html")


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
            # 同时提取标题
            title = get_video_title(link, cookie=cookie)
            video_path = download_video(link, cookie=cookie)
            audio_path = extract_audio(video_path)
            result = transcribe(audio_path)
            if title:
                result["title"] = title
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



@app.route("/batch_transcribe", methods=["POST"])
def batch_transcribe():
    data = request.get_json(force=True)
    import re
    raw_lines = (data.get("links") or "").strip().splitlines()
    cookie = (data.get("cookie") or "").strip() or None
    # 只提取包含 URL 的行，忽略纯文字描述行
    links = []
    for line in raw_lines:
        m = re.search(r"https?://[^\s，,]+", line)
        if m:
            links.append(m.group(0))

    if not links:
        return jsonify(ok=False, error="请输入至少一个链接")
    if len(links) > 10:
        return jsonify(ok=False, error="最多同时处理 10 个链接")

    task_ids = []
    for link in links:
        task_id = str(uuid.uuid4())
        tasks[task_id] = {"status": "processing", "result": None, "error": None, "link": link}

        def run(tid=task_id, lnk=link):
            try:
                title = get_video_title(lnk, cookie=cookie)
                video_path = download_video(lnk, cookie=cookie)
                audio_path = extract_audio(video_path)
                result = transcribe(audio_path)
                if title:
                    result["title"] = title
                result["link"] = lnk
                _cleanup(video_path, audio_path)
                tasks[tid]["result"] = result
                tasks[tid]["status"] = "done"
            except Exception as e:
                tasks[tid]["error"] = str(e)
                tasks[tid]["status"] = "error"

        threading.Thread(target=run, daemon=True).start()
        task_ids.append(task_id)

    return jsonify(ok=True, task_ids=task_ids)


@app.route("/comments", methods=["POST"])
def fetch_comments():
    data = request.get_json(force=True)
    link = (data.get("link") or "").strip()
    cookie = (data.get("cookie") or "").strip() or None
    if not link:
        return jsonify(ok=False, error="请输入链接")
    try:
        comments = get_comments(link, cookie=cookie)
        if not comments:
            return jsonify(ok=False, error="未能提取到评论，该平台可能不支持或需要 Cookie")
        return jsonify(ok=True, comments=comments)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/export_docx", methods=["POST"])
def export_docx():
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify(ok=False, error="逐字稿为空，无法导出")

    from docx import Document
    from docx.shared import Pt

    doc = Document()
    if title:
        doc.add_heading(title, level=1)
    for para_text in content.split("\n"):
        p = doc.add_paragraph(para_text)
        for run in p.runs:
            run.font.size = Pt(12)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    filename = (title[:30] if title else "逐字稿") + ".docx"
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _cleanup(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
