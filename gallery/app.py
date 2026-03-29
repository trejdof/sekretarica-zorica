import json
import mimetypes
import os
from functools import wraps

from flask import Flask, abort, make_response, redirect, render_template, request, send_file, url_for

import config

app = Flask(__name__)

MEDIA_DIR = config.MEDIA_DIR
IMAGE_DIR = os.path.join(MEDIA_DIR, "images")
os.makedirs(IMAGE_DIR, exist_ok=True)
SECRET = config.GALLERY_SECRET
STORAGE_LIMIT_GB = 5


def _authed():
    token = request.args.get("t") or request.cookies.get("gt")
    return token == SECRET


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _authed():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _safe_id(item_id):
    if not item_id or "/" in item_id or ".." in item_id:
        abort(400)
    return item_id


def _get_videos():
    videos = []
    for f in os.listdir(MEDIA_DIR):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(MEDIA_DIR, f)) as fp:
            meta = json.load(fp)
        if meta.get("type") == "image":
            continue
        video_path = os.path.join(MEDIA_DIR, meta["id"] + ".mp4")
        if os.path.exists(video_path):
            meta["size_mb"] = round(os.path.getsize(video_path) / 1024 / 1024, 1)
            videos.append(meta)
    return videos


def _get_images():
    images = []
    if not os.path.exists(IMAGE_DIR):
        return images
    for f in os.listdir(IMAGE_DIR):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(IMAGE_DIR, f)) as fp:
            meta = json.load(fp)
        ext = meta.get("file_ext", ".jpg")
        img_path = os.path.join(IMAGE_DIR, meta["id"] + ext)
        if os.path.exists(img_path):
            meta["size_kb"] = meta.get("size_kb", round(os.path.getsize(img_path) / 1024, 1))
            images.append(meta)
    return images


def _total_storage_gb(videos, images):
    video_mb = sum(v["size_mb"] for v in videos)
    image_kb = sum(i.get("size_kb", 0) for i in images)
    return (video_mb + image_kb / 1024) / 1024


@app.route("/")
def index():
    if not _authed():
        abort(403)

    sort = request.args.get("sort", "date")
    videos = _get_videos()
    if sort == "size":
        videos.sort(key=lambda v: v["size_mb"], reverse=True)
    else:
        videos.sort(key=lambda v: v.get("downloaded_at", ""), reverse=True)

    images = _get_images()
    total_gb = _total_storage_gb(videos, images)
    pct = min(total_gb / STORAGE_LIMIT_GB * 100, 100)

    resp = make_response(render_template(
        "index.html",
        videos=videos,
        sort=sort,
        total_gb=round(total_gb, 2),
        limit_gb=STORAGE_LIMIT_GB,
        pct=round(pct, 1),
        image_count=len(images),
    ))
    if t := request.args.get("t"):
        resp.set_cookie("gt", t, max_age=60 * 60 * 24 * 30, httponly=True)
    return resp


@app.route("/images")
def images():
    if not _authed():
        abort(403)

    sort = request.args.get("sort", "date")
    image_list = _get_images()
    if sort == "size":
        image_list.sort(key=lambda i: i.get("size_kb", 0), reverse=True)
    else:
        image_list.sort(key=lambda i: i.get("downloaded_at", ""), reverse=True)

    videos = _get_videos()
    total_gb = _total_storage_gb(videos, image_list)
    pct = min(total_gb / STORAGE_LIMIT_GB * 100, 100)

    resp = make_response(render_template(
        "images.html",
        images=image_list,
        sort=sort,
        total_gb=round(total_gb, 2),
        limit_gb=STORAGE_LIMIT_GB,
        pct=round(pct, 1),
        video_count=len(videos),
    ))
    if t := request.args.get("t"):
        resp.set_cookie("gt", t, max_age=60 * 60 * 24 * 30, httponly=True)
    return resp


@app.route("/v/<video_id>")
@auth_required
def video(video_id):
    _safe_id(video_id)
    meta_path = os.path.join(MEDIA_DIR, video_id + ".json")
    if not os.path.exists(meta_path):
        abort(404)
    with open(meta_path) as f:
        meta = json.load(f)
    meta["size_mb"] = round(os.path.getsize(os.path.join(MEDIA_DIR, video_id + ".mp4")) / 1024 / 1024, 1)
    return render_template("video.html", video=meta)


@app.route("/stream/<video_id>")
@auth_required
def stream(video_id):
    _safe_id(video_id)
    path = os.path.join(MEDIA_DIR, video_id + ".mp4")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="video/mp4", conditional=True)


@app.route("/thumb/<video_id>")
@auth_required
def thumb(video_id):
    _safe_id(video_id)
    path = os.path.join(MEDIA_DIR, video_id + ".jpg")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg")


@app.route("/download/<video_id>")
@auth_required
def download(video_id):
    _safe_id(video_id)
    path = os.path.join(MEDIA_DIR, video_id + ".mp4")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=video_id + ".mp4")


@app.route("/delete/<video_id>", methods=["POST"])
@auth_required
def delete(video_id):
    _safe_id(video_id)
    for ext in (".mp4", ".jpg", ".json"):
        path = os.path.join(MEDIA_DIR, video_id + ext)
        if os.path.exists(path):
            os.remove(path)
    return redirect(request.referrer or url_for("index"))


@app.route("/img/<image_id>")
@auth_required
def serve_image(image_id):
    _safe_id(image_id)
    meta_path = os.path.join(IMAGE_DIR, image_id + ".json")
    if not os.path.exists(meta_path):
        abort(404)
    with open(meta_path) as f:
        meta = json.load(f)
    ext = meta.get("file_ext", ".jpg")
    path = os.path.join(IMAGE_DIR, image_id + ext)
    if not os.path.exists(path):
        abort(404)
    mime = mimetypes.types_map.get(ext, "image/jpeg")
    return send_file(path, mimetype=mime)


@app.route("/download-img/<image_id>")
@auth_required
def download_image(image_id):
    _safe_id(image_id)
    meta_path = os.path.join(IMAGE_DIR, image_id + ".json")
    if not os.path.exists(meta_path):
        abort(404)
    with open(meta_path) as f:
        meta = json.load(f)
    ext = meta.get("file_ext", ".jpg")
    path = os.path.join(IMAGE_DIR, image_id + ext)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=image_id + ext)


@app.route("/delete-img/<image_id>", methods=["POST"])
@auth_required
def delete_image(image_id):
    _safe_id(image_id)
    meta_path = os.path.join(IMAGE_DIR, image_id + ".json")
    ext = ".jpg"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        ext = meta.get("file_ext", ".jpg")
        os.remove(meta_path)
    img_path = os.path.join(IMAGE_DIR, image_id + ext)
    if os.path.exists(img_path):
        os.remove(img_path)
    return redirect(request.referrer or url_for("images"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, threaded=True)
