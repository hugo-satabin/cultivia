"""
cultivia_tiktok_demo.py
=======================
Demo app for TikTok Developer Portal review.
Implements Login Kit (OAuth 2.0) + Content Posting API (Direct Post).

Prerequisites:
    pip install flask requests

Configuration (set as environment variables or edit below):
    TIKTOK_CLIENT_KEY     = your app's Client Key from the Developer Portal
    TIKTOK_CLIENT_SECRET  = your app's Client Secret from the Developer Portal
    REDIRECT_URI          = your callback URL (must match what you set in the Portal)

Usage:
    python cultivia_tiktok_demo.py
    # Then open http://localhost:5000 in your browser

For HTTPS (required by TikTok), use ngrok:
    ngrok http 5000
    # Set REDIRECT_URI to the ngrok HTTPS URL + /callback
"""

import os
import json
import time
import secrets
import requests
from flask import Flask, request, redirect, session, jsonify, render_template_string

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# ---------------------------------------------------------------------------
# Configuration — fill these in or use environment variables
# ---------------------------------------------------------------------------

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "YOUR_CLIENT_KEY")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://your-ngrok-url.ngrok.io/callback")

# TikTok OAuth endpoints
OAUTH_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
OAUTH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
PUBLISH_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
PUBLISH_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# Scopes requested (must match what you configured in the Developer Portal)
SCOPES = [
    "user.info.basic",
    "video.publish",
    "video.upload",
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Main page — shows login or upload form depending on session state."""
    if "access_token" not in session:
        return render_template_string(LOGIN_PAGE, redirect_uri=REDIRECT_URI)
    return render_template_string(
        UPLOAD_PAGE,
        username=session.get("username", "User"),
        avatar=session.get("avatar", ""),
    )


@app.route("/login")
def login():
    """Step 1 — Redirect user to TikTok OAuth authorization page."""
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_key": CLIENT_KEY,
        "scope": ",".join(SCOPES),
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    auth_url = OAUTH_AUTHORIZE_URL + "?" + "&".join(
        f"{k}={v}" for k, v in params.items()
    )
    return redirect(auth_url)


@app.route("/callback")
def callback():
    """Step 2 — TikTok redirects here with an authorization code."""
    # Verify state to prevent CSRF
    received_state = request.args.get("state", "")
    if received_state != session.get("oauth_state", ""):
        return "Error: Invalid state parameter", 400

    code = request.args.get("code")
    if not code:
        return "Error: No authorization code received", 400

    # Step 3 — Exchange authorization code for access token
    token_resp = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    if not token_resp.ok:
        return f"Error exchanging code: {token_resp.text}", 400

    token_json = token_resp.json()
    # TikTok may return token fields at root level or nested under "data"
    token_data = token_json.get("data", token_json)
    access_token = token_data.get("access_token", "")
    open_id = token_data.get("open_id", "")

    if not access_token:
        return f"Error: No access token in response: {token_resp.text}", 400

    session["access_token"] = access_token
    session["open_id"] = open_id

    # Step 4 — Fetch user profile info (demonstrates user.info.basic scope)
    user_resp = requests.get(
        USER_INFO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        params={"fields": "open_id,union_id,avatar_url,display_name,bio_description"},
        timeout=30,
    )
    if user_resp.ok:
        user_data = user_resp.json().get("data", {})
        user = user_data.get("user", {})
        session["username"] = user.get("display_name", "TikTok User")
        session["avatar"] = user.get("avatar_url", "")

    return redirect("/")


@app.route("/upload", methods=["POST"])
def upload():
    """Step 5 — Upload and publish a video via Content Posting API."""
    if "access_token" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    access_token = session["access_token"]

    # Get uploaded file and metadata
    video_file = request.files.get("video")
    title = request.form.get("title", "")
    description = request.form.get("description", "")

    if not video_file:
        return jsonify({"error": "No video file provided"}), 400

    # Save video to temp file (cross-platform)
    import tempfile
    video_path = os.path.join(tempfile.gettempdir(), f"upload_{int(time.time())}.mp4")
    video_file.save(video_path)
    video_size = os.path.getsize(video_path)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    # Step 6 — Initialize upload via Content Posting API
    init_body = {
        "post_info": {
            "title": title[:2200],
            "privacy_level": "SELF_ONLY",  # sandbox mode forces SELF_ONLY
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }

    init_resp = requests.post(
        PUBLISH_INIT_URL, headers=headers, json=init_body, timeout=30
    )
    if not init_resp.ok:
        return jsonify({
            "error": "Init failed",
            "status_code": init_resp.status_code,
            "detail": init_resp.text,
        }), 400

    init_data = init_resp.json().get("data", {})
    publish_id = init_data.get("publish_id", "")
    upload_url = init_data.get("upload_url", "")

    if not publish_id or not upload_url:
        return jsonify({
            "error": "Incomplete init response",
            "detail": init_resp.text,
        }), 400

    # Step 7 — Upload video file via PUT
    with open(video_path, "rb") as fh:
        video_bytes = fh.read()

    put_resp = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        },
        data=video_bytes,
        timeout=300,
    )
    if not put_resp.ok:
        return jsonify({
            "error": "Upload PUT failed",
            "status_code": put_resp.status_code,
            "detail": put_resp.text,
        }), 400

    # Step 8 — Poll for publish status
    status = "PROCESSING"
    for _ in range(10):
        time.sleep(3)
        status_resp = requests.post(
            PUBLISH_STATUS_URL,
            headers=headers,
            json={"publish_id": publish_id},
            timeout=30,
        )
        if status_resp.ok:
            status = status_resp.json().get("data", {}).get("status", "PROCESSING")
            if status in ("PUBLISH_COMPLETE", "FAILED"):
                break

    # Clean up temp file
    os.remove(video_path)

    return jsonify({
        "success": True,
        "publish_id": publish_id,
        "status": status,
    })


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------------------------------------------------------------------
# HTML Pages (inline templates for simplicity)
# ---------------------------------------------------------------------------

LOGIN_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>publ_app_cultivia_world</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: Inter, system-ui, -apple-system, sans-serif;
      background: #0f0f0f;
      color: #fff;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .container { text-align: center; max-width: 480px; padding: 40px 24px; }
    .logo { font-size: 2rem; font-weight: 800; margin-bottom: 8px;
            background: linear-gradient(135deg, #fe2c55, #25f4ee);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .subtitle { color: #9ca3af; margin-bottom: 40px; font-size: 1rem; }
    .login-btn {
      display: inline-flex; align-items: center; gap: 10px;
      padding: 16px 36px; border: none; border-radius: 12px;
      background: linear-gradient(135deg, #fe2c55, #ff0050);
      color: #fff; font-size: 1.1rem; font-weight: 600;
      cursor: pointer; transition: transform 0.2s, opacity 0.2s;
      text-decoration: none;
    }
    .login-btn:hover { transform: scale(1.05); }
    .login-btn:active { transform: scale(0.98); }
    .login-btn svg { width: 24px; height: 24px; }
    .feature-list { margin-top: 32px; text-align: left;
                    color: #9ca3af; font-size: 0.9rem; line-height: 1.8; }
    .feature-list li { margin-bottom: 4px; list-style: none; }
    .feature-list li::before { content: "✓ "; color: #25f4ee; }
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">publ_app_cultivia_world</div>
    <p class="subtitle">Publish your content directly to TikTok</p>
    <a href="/login" class="login-btn">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64 2.93 2.93 0 0 1 .88.13V9.4a6.84 6.84 0 0 0-1-.05A6.33 6.33 0 0 0 5.2 20.1a6.34 6.34 0 0 0 10.86-4.43V8.66a8.16 8.16 0 0 0 4.77 1.52V6.73a4.85 4.85 0 0 1-1.24-.04z"/></svg>
      Connect with TikTok
    </a>
    <ul class="feature-list">
      <li>Authenticate with TikTok Login Kit</li>
      <li>Upload and publish videos via Content Posting API</li>
      <li>Direct post to your TikTok profile</li>
      <li>Supports titles, descriptions and hashtags</li>
    </ul>
  </div>
</body>
</html>
"""

UPLOAD_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>publ_app_cultivia_world — Publish</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: Inter, system-ui, -apple-system, sans-serif;
      background: #0f0f0f;
      color: #fff;
      min-height: 100vh;
    }
    .header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 16px 24px; background: #161616; border-bottom: 1px solid #2a2a2a;
    }
    .header .logo { font-size: 1.2rem; font-weight: 700;
      background: linear-gradient(135deg, #fe2c55, #25f4ee);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .user-info { display: flex; align-items: center; gap: 10px; }
    .user-info img { width: 32px; height: 32px; border-radius: 50%; }
    .user-info .name { color: #d1d5db; font-size: 0.9rem; }
    .logout { color: #9ca3af; text-decoration: none; font-size: 0.85rem; }
    .container { max-width: 600px; margin: 0 auto; padding: 32px 24px; }
    h1 { font-size: 1.4rem; margin-bottom: 24px; }
    .form-group { margin-bottom: 20px; }
    label { display: block; margin-bottom: 6px; color: #d1d5db;
           font-size: 0.9rem; font-weight: 500; }
    input[type="text"], textarea {
      width: 100%; padding: 12px; border-radius: 8px;
      border: 1px solid #374151; background: #1a1a1a; color: #fff;
      font-size: 0.95rem; font-family: inherit;
    }
    textarea { resize: vertical; min-height: 80px; }
    .file-drop {
      border: 2px dashed #374151; border-radius: 12px; padding: 40px;
      text-align: center; cursor: pointer; transition: border-color 0.2s;
      background: #1a1a1a;
    }
    .file-drop:hover { border-color: #fe2c55; }
    .file-drop.has-file { border-color: #25f4ee; border-style: solid; }
    .file-drop p { color: #9ca3af; font-size: 0.9rem; margin-top: 8px; }
    .file-drop .icon { font-size: 2rem; }
    .file-name { color: #25f4ee; font-size: 0.85rem; margin-top: 8px; }
    input[type="file"] { display: none; }
    .submit-btn {
      width: 100%; padding: 16px; border: none; border-radius: 12px;
      background: linear-gradient(135deg, #fe2c55, #ff0050);
      color: #fff; font-size: 1.1rem; font-weight: 600;
      cursor: pointer; transition: opacity 0.2s; margin-top: 8px;
    }
    .submit-btn:hover { opacity: 0.9; }
    .submit-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .status-box {
      margin-top: 24px; padding: 16px; border-radius: 12px;
      display: none;
    }
    .status-box.show { display: block; }
    .status-box.success { background: #064e3b; border: 1px solid #10b981; }
    .status-box.error { background: #7f1d1d; border: 1px solid #ef4444; }
    .status-box.processing { background: #1e3a5f; border: 1px solid #3b82f6; }
    .status-box h3 { margin-bottom: 8px; font-size: 1rem; }
    .status-box p { font-size: 0.9rem; color: #d1d5db; }
    .step-indicator { display: flex; gap: 8px; margin-top: 16px; }
    .step { flex: 1; height: 4px; border-radius: 2px; background: #374151;
            transition: background 0.3s; }
    .step.active { background: #25f4ee; }
    .step.done { background: #10b981; }
    .step-labels { display: flex; gap: 8px; margin-top: 6px; }
    .step-labels span { flex: 1; text-align: center; font-size: 0.75rem;
                         color: #6b7280; }
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">publ_app_cultivia_world</div>
    <div class="user-info">
      <img src="{{ avatar }}" alt="avatar" onerror="this.style.display='none'">
      <span class="name">{{ username }}</span>
      <a href="/logout" class="logout">Logout</a>
    </div>
  </div>

  <div class="container">
    <h1>Publish a video to TikTok</h1>

    <form id="uploadForm">
      <div class="form-group">
        <label>Video file (MP4, max 50MB)</label>
        <div class="file-drop" id="fileDrop" onclick="document.getElementById('videoFile').click()">
          <div class="icon">📹</div>
          <p>Click to select a video</p>
          <div class="file-name" id="fileName"></div>
        </div>
        <input type="file" id="videoFile" accept="video/mp4" required>
      </div>

      <div class="form-group">
        <label>Title</label>
        <input type="text" id="title" placeholder="My awesome video" maxlength="2200" required>
      </div>

      <div class="form-group">
        <label>Description</label>
        <textarea id="description" placeholder="Add a description and #hashtags" maxlength="2200"></textarea>
      </div>

      <button type="submit" class="submit-btn" id="submitBtn">Publish to TikTok</button>
    </form>

    <div class="status-box" id="statusBox">
      <h3 id="statusTitle"></h3>
      <p id="statusMessage"></p>
      <div class="step-indicator">
        <div class="step" id="step1"></div>
        <div class="step" id="step2"></div>
        <div class="step" id="step3"></div>
      </div>
      <div class="step-labels">
        <span>Initializing</span>
        <span>Uploading</span>
        <span>Publishing</span>
      </div>
    </div>
  </div>

  <script>
    const fileDrop = document.getElementById('fileDrop');
    const videoFile = document.getElementById('videoFile');
    const fileName = document.getElementById('fileName');
    const form = document.getElementById('uploadForm');
    const submitBtn = document.getElementById('submitBtn');
    const statusBox = document.getElementById('statusBox');
    const statusTitle = document.getElementById('statusTitle');
    const statusMessage = document.getElementById('statusMessage');

    videoFile.addEventListener('change', (e) => {
      if (e.target.files[0]) {
        fileName.textContent = e.target.files[0].name;
        fileDrop.classList.add('has-file');
        fileDrop.querySelector('p').textContent = 'Click to change video';
      }
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      submitBtn.disabled = true;
      submitBtn.textContent = 'Publishing...';

      // Show steps
      statusBox.className = 'status-box show processing';
      statusTitle.textContent = 'Publishing in progress...';
      statusMessage.textContent = 'Uploading your video to TikTok';
      document.getElementById('step1').className = 'step active';

      const formData = new FormData();
      formData.append('video', videoFile.files[0]);
      formData.append('title', document.getElementById('title').value);
      formData.append('description', document.getElementById('description').value);

      try {
        const resp = await fetch('/upload', { method: 'POST', body: formData });
        const data = await resp.json();

        document.getElementById('step1').className = 'step done';
        document.getElementById('step2').className = 'step done';
        document.getElementById('step3').className = 'step done';

        if (data.success) {
          statusBox.className = 'status-box show success';
          statusTitle.textContent = '✓ Video published successfully!';
          statusMessage.textContent = 'Publish ID: ' + data.publish_id +
            ' | Status: ' + data.status;
        } else {
          statusBox.className = 'status-box show error';
          statusTitle.textContent = '✗ Publishing failed';
          statusMessage.textContent = data.error + ': ' + (data.detail || '');
        }
      } catch (err) {
        statusBox.className = 'status-box show error';
        statusTitle.textContent = '✗ Error';
        statusMessage.textContent = err.message;
      }

      submitBtn.disabled = false;
      submitBtn.textContent = 'Publish to TikTok';
    });
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  publ_app_cultivia_world — TikTok Demo")
    print("=" * 60)
    print(f"  Client Key:    {CLIENT_KEY[:8]}...")
    print(f"  Client Secret: {CLIENT_SECRET[:4]}...")
    print(f"  Redirect URI:  {REDIRECT_URI}")
    print(f"  Scopes:        {', '.join(SCOPES)}")
    print("=" * 60)
    print("  Open http://localhost:5000 in your browser")
    print("  For HTTPS, run: ngrok http 5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)