#!/usr/bin/env python3
"""Hot Money · 本地 Flask 前端

用法:
    python3 webapp.py
    # 浏览器打开 http://localhost:8976
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import uuid
from collections import deque
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template_string, request, send_from_directory, url_for

ROOT = Path(__file__).parent.resolve()
REPORTS_DIR = ROOT / "skills" / "deep-analysis" / "scripts" / "reports"

# ─── 并发控制 ───
MAX_CONCURRENT = int(os.environ.get("HOTMONEY_CONCURRENCY", "2"))
_queue_lock = threading.Lock()
_queue: deque = deque()  # 等待中的 job_id
_running: set = set()     # 运行中的 job_id

# ─── Basic Auth (可选,设空字符串禁用) ───
AUTH_USER = os.environ.get("HOTMONEY_USER", "")
AUTH_PASS = os.environ.get("HOTMONEY_PASS", "")

app = Flask(__name__)


def _check_auth(auth):
    return auth and auth.username == AUTH_USER and auth.password == AUTH_PASS


@app.before_request
def require_auth():
    if not AUTH_USER or not AUTH_PASS:
        return  # 未设置凭证 → 完全开放
    auth = request.authorization
    if not _check_auth(auth):
        return Response(
            "Authentication required\n", 401,
            {"WWW-Authenticate": 'Basic realm="Hot Money"'}
        )

JOBS: dict[str, dict] = {}


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Hot Money · 个股深度分析</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #fafaf7;
    --bg-2: #ffffff;
    --panel: #ffffff;
    --border: rgba(10,10,20,0.08);
    --border-strong: rgba(10,10,20,0.14);
    --text: #0a0a14;
    --text-dim: #6e6e7a;
    --text-light: #9a9aa4;
    --accent: #b8902a;
    --accent-2: #d4af37;
    --red: #dc2626;
    --green: #16a34a;
  }
  html, body { background: var(--bg); color: var(--text); }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif;
    min-height: 100vh;
    font-feature-settings: "cv11","ss01","ss03";
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    background:
      radial-gradient(circle at 10% 10%, rgba(212,175,55,0.08), transparent 50%),
      radial-gradient(circle at 90% 90%, rgba(212,175,55,0.05), transparent 50%);
    pointer-events: none;
    z-index: 0;
  }
  .wrap { position: relative; z-index: 1; max-width: 720px; margin: 0 auto;
          padding: 64px 24px 48px; }

  header { margin-bottom: 56px; }
  .brand { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
  .logo {
    font-family: 'Inter', sans-serif;
    font-weight: 800; font-size: 38px; letter-spacing: -0.03em;
    background: linear-gradient(135deg, #0a0a14 0%, var(--accent) 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .brand-zh { color: var(--text-light); font-size: 13px; font-weight: 500;
              letter-spacing: 0.22em; text-transform: uppercase; }
  .tagline { color: var(--text-dim); font-size: 15px; line-height: 1.65;
             font-weight: 400; max-width: 540px; }
  .tagline strong { color: var(--accent); font-weight: 600; }

  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 36px;
    box-shadow: 0 2px 8px rgba(10,10,20,0.03), 0 20px 50px rgba(10,10,20,0.06);
  }

  label { display: block; font-size: 11px; font-weight: 600; color: var(--text-dim);
          letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; }
  label:not(:first-child) { margin-top: 24px; }

  input[type=text], select {
    width: 100%; padding: 16px 18px;
    background: #fafafa;
    border: 1.5px solid var(--border);
    border-radius: 12px;
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 16px; font-weight: 500;
    transition: all 0.2s ease;
  }
  input[type=text]::placeholder { color: var(--text-light); font-weight: 400; }
  input[type=text]:focus, select:focus {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 4px rgba(184,144,42,0.12);
    background: #ffffff;
  }
  select { appearance: none; cursor: pointer;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='%236e6e7a' d='M6 8L2 4h8z'/></svg>");
    background-repeat: no-repeat; background-position: right 18px center; padding-right: 44px;
  }
  .hint { font-size: 12px; color: var(--text-light); margin-top: 8px; }

  .checkbox-row {
    display: flex; align-items: center; gap: 10px;
    margin-top: 20px !important; padding: 14px 16px;
    background: #fafafa; border: 1px solid var(--border);
    border-radius: 10px; cursor: pointer;
    font-size: 13px; color: var(--text-dim); font-weight: 500;
    letter-spacing: 0; text-transform: none;
    transition: all 0.15s;
  }
  .checkbox-row:hover { border-color: var(--accent); }
  .checkbox-row input[type=checkbox] {
    width: 16px; height: 16px; margin: 0;
    accent-color: var(--accent); cursor: pointer;
  }

  .btn-wrap { margin-top: 32px; }
  button {
    width: 100%; padding: 18px;
    background: linear-gradient(135deg, #1a1a24 0%, #000000 100%);
    color: #ffffff; font-family: 'Inter', sans-serif;
    font-size: 14px; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; border: 0; border-radius: 12px;
    cursor: pointer; transition: all 0.2s ease;
    box-shadow: 0 4px 16px rgba(10,10,20,0.15);
  }
  button:hover { transform: translateY(-1px);
                 box-shadow: 0 8px 24px rgba(10,10,20,0.25);
                 background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%); }
  button:active { transform: translateY(0); }
  .build-info {
    margin-top: 14px; text-align: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: var(--text-light); letter-spacing: 0.05em;
  }
  .build-info .sep { color: var(--border-strong); margin: 0 8px; }
  .build-info .badge {
    display: inline-block; padding: 2px 8px;
    background: rgba(22,163,74,0.08); color: var(--green);
    border-radius: 20px; font-weight: 600; font-size: 10px;
    letter-spacing: 0.1em;
  }

  .recent { margin-top: 48px; }
  .recent-head { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
  .recent-head h3 { font-size: 11px; color: var(--text-dim); letter-spacing: 0.18em;
                    text-transform: uppercase; font-weight: 600; }
  .recent-head .count { font-size: 10px; color: var(--accent);
                        border: 1px solid var(--accent); padding: 2px 8px;
                        border-radius: 20px; font-family: 'JetBrains Mono', monospace;
                        font-weight: 600; }
  .recent a {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 18px; margin-bottom: 8px;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px; text-decoration: none;
    color: var(--text); font-size: 14px;
    transition: all 0.15s ease;
  }
  .recent a:hover { border-color: var(--accent); box-shadow: 0 4px 12px rgba(184,144,42,0.12);
                    transform: translateX(2px); }
  .recent .name { display: flex; align-items: baseline; gap: 10px; min-width: 0; flex: 1; }
  .recent .sname { font-family: 'Inter', sans-serif; font-weight: 600;
                   color: var(--text); font-size: 14px;
                   white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .recent .code { font-family: 'JetBrains Mono', monospace; font-weight: 500;
                  color: var(--text-dim); font-size: 12px; flex-shrink: 0; }
  .recent .time { font-size: 12px; color: var(--text-dim); flex-shrink: 0; margin-left: 12px; }

  footer { margin-top: 48px; text-align: center; font-size: 10px;
           color: var(--text-light); letter-spacing: 0.15em;
           font-family: 'JetBrains Mono', monospace; }
  footer .dot { display: inline-block; width: 5px; height: 5px;
                background: var(--green); border-radius: 50%;
                margin-right: 6px; vertical-align: middle;
                animation: pulse 2s infinite;
                box-shadow: 0 0 8px rgba(22,163,74,0.5); }
  footer a { color: var(--text-dim); text-decoration: none; }
  footer a:hover { color: var(--accent); }
  @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.3;} }

  @media (max-width: 640px) {
    .wrap { padding: 40px 16px 32px; }
    .panel { padding: 24px; border-radius: 16px; }
    .logo { font-size: 30px; }
    header { margin-bottom: 36px; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <span class="logo">Hot Money</span>
      <span class="brand-zh">个股深度分析</span>
    </div>
    <p class="tagline">输入一只股票,<strong>AI 分析师</strong>用 22 个维度、17 种机构方法、51 位投资大佬视角,吐一份 Bloomberg 级别的研报。</p>
  </header>

  <div class="panel">
    <form method="post" action="/analyze">
      <label>股票代码 / 名称</label>
      <input type="text" name="ticker" placeholder="600519 · 贵州茅台 · AAPL · 00700.HK" required autofocus autocomplete="off">
      <div class="hint">A 股 6 位代码 · 中文名 · 港股 .HK · 美股代码</div>

      <label>分析深度</label>
      <select name="depth">
        <option value="lite">⚡ LITE · 速判模式 (1-2 分钟)</option>
        <option value="medium" selected>📊 STANDARD · 标准分析 (5-8 分钟)</option>
        <option value="deep">🔬 DEEP · 深度研究 (15-20 分钟)</option>
      </select>
      <div class="hint">首次分析任意档位会慢一些,后续相同股票有缓存提速</div>

      <label class="checkbox-row">
        <input type="checkbox" name="force">
        <span>强制重新分析(忽略 3 天内的缓存报告)</span>
      </label>

      <div class="btn-wrap">
        <button type="submit">启动分析引擎</button>
        <div class="build-info">
          <span class="badge">v{{ version }}</span>
          <span class="sep">|</span>
          <span>BUILD · {{ build_date }}</span>
        </div>
      </div>
    </form>
  </div>

  {% if recent %}
  <div class="recent">
    <div class="recent-head">
      <h3>最近报告</h3>
      <span class="count">{{ recent|length }}</span>
    </div>
    {% for r in recent %}
    <a href="/report/{{ r.name }}">
      <span class="name">
        {% if r.stock_name %}<span class="sname">{{ r.stock_name }}</span>{% endif %}
        <span class="code">{{ r.code }}</span>
      </span>
      <span class="time">{{ r.mtime }}</span>
    </a>
    {% endfor %}
  </div>
  {% endif %}

  <footer>
    <span class="dot"></span>SYSTEM ONLINE · <a href="https://github.com/godisego/hot-money" target="_blank">GODISEGO/HOT-MONEY</a>
  </footer>
</div>
</body>
</html>
"""

RUNNING_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>分析中 · {{ ticker }}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #fafaf7; --panel: #ffffff;
    --border: rgba(10,10,20,0.08);
    --text: #0a0a14; --text-dim: #6e6e7a; --text-light: #9a9aa4;
    --accent: #b8902a; --accent-2: #d4af37;
    --green: #16a34a; --red: #dc2626; --amber: #d97706;
  }
  body {
    font-family: 'Inter', "PingFang SC", sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100vh; -webkit-font-smoothing: antialiased;
  }
  body::before {
    content: ""; position: fixed; inset: 0;
    background: radial-gradient(circle at 50% 0%, rgba(212,175,55,0.06), transparent 50%);
    pointer-events: none;
  }
  .wrap { position: relative; max-width: 960px; margin: 0 auto; padding: 40px 24px; }
  header { display: flex; justify-content: space-between; align-items: center;
           margin-bottom: 28px; flex-wrap: wrap; gap: 16px; }
  .title { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
  .title .ticker { background: linear-gradient(135deg, #0a0a14, var(--accent));
                   -webkit-background-clip: text; background-clip: text;
                   color: transparent; font-family: 'JetBrains Mono', monospace; }
  .back { color: var(--text-dim); text-decoration: none; font-size: 13px;
          padding: 8px 14px; border: 1px solid var(--border); border-radius: 8px;
          transition: all 0.15s; background: var(--panel); }
  .back:hover { border-color: var(--accent); color: var(--accent); }

  .status-card {
    background: var(--panel);
    border: 1px solid var(--border); border-radius: 16px;
    padding: 20px 24px; margin-bottom: 16px;
    display: flex; align-items: center; gap: 16px;
    box-shadow: 0 2px 8px rgba(10,10,20,0.03);
  }
  .spinner {
    width: 14px; height: 14px; border-radius: 50%;
    background: var(--amber); position: relative;
    box-shadow: 0 0 0 4px rgba(217,119,6,0.15);
    animation: pulse 1.4s infinite;
  }
  .spinner.done { background: var(--green); animation: none;
                  box-shadow: 0 0 0 4px rgba(22,163,74,0.15); }
  .spinner.error { background: var(--red); animation: none;
                   box-shadow: 0 0 0 4px rgba(220,38,38,0.15); }
  @keyframes pulse { 0%,100%{opacity:1; transform: scale(1);} 50%{opacity:0.5; transform: scale(0.9);} }
  .phase { font-size: 15px; font-weight: 500; flex: 1; color: var(--text); }
  .elapsed { font-family: 'JetBrains Mono', monospace; font-size: 13px;
             color: var(--text-dim); padding: 6px 12px;
             background: #f0f0ec; border-radius: 6px; font-weight: 600; }

  .term {
    background: #0d0d14; border: 1px solid #1f1f2a; border-radius: 16px;
    overflow: hidden; box-shadow: 0 10px 40px rgba(10,10,20,0.15);
  }
  .term-head {
    display: flex; align-items: center; gap: 8px;
    padding: 12px 16px; background: #16161f;
    border-bottom: 1px solid #1f1f2a;
  }
  .term-dot { width: 10px; height: 10px; border-radius: 50%; }
  .term-dot.r { background: #ff5f56; }
  .term-dot.y { background: #ffbd2e; }
  .term-dot.g { background: #27c93f; }
  .term-title { margin-left: 12px; font-size: 12px; color: #8a8a95;
                font-family: 'JetBrains Mono', monospace; }
  pre#log {
    margin: 0; padding: 20px 24px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; line-height: 1.7;
    color: #c8c8d0;
    height: 65vh; overflow-y: auto;
    white-space: pre-wrap; word-break: break-all;
  }
  pre#log::-webkit-scrollbar { width: 8px; }
  pre#log::-webkit-scrollbar-track { background: transparent; }
  pre#log::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="title">分析目标 · <span class="ticker">{{ ticker }}</span> · <span style="color: var(--text-dim); font-size: 14px; font-weight: 400;">{{ depth|upper }}</span></div>
    <a href="/" class="back">← 返回</a>
  </header>

  <div class="status-card">
    <div class="spinner" id="spinner"></div>
    <div class="phase" id="phase">初始化分析引擎...</div>
    <div class="elapsed" id="elapsed">00:00</div>
  </div>

  <div class="term">
    <div class="term-head">
      <div class="term-dot r"></div>
      <div class="term-dot y"></div>
      <div class="term-dot g"></div>
      <div class="term-title">hot-money-engine · live log</div>
    </div>
    <pre id="log">等待启动...</pre>
  </div>
</div>

<script>
const jobId = "{{ job_id }}";
const logEl = document.getElementById("log");
const phaseEl = document.getElementById("phase");
const spinnerEl = document.getElementById("spinner");
const elapsedEl = document.getElementById("elapsed");

function fmt(s) {
  const m = Math.floor(s / 60).toString().padStart(2, '0');
  const ss = (s % 60).toString().padStart(2, '0');
  return m + ':' + ss;
}

async function poll() {
  try {
    const r = await fetch('/status/' + jobId);
    const j = await r.json();
    if (j.log) {
      logEl.textContent = j.log;
      logEl.scrollTop = logEl.scrollHeight;
    }
    elapsedEl.textContent = fmt(j.elapsed || 0);
    if (j.status === 'running') phaseEl.textContent = '分析中 · 处理数据维度...';
    else if (j.status === 'queued') {
      const pos = j.queue_position || 1;
      phaseEl.textContent = `排队中 · 前面还有 ${pos - 1} 人 (并发 ${j.running_count}/${j.max_concurrent})`;
    }
    else if (j.status === 'done') {
      phaseEl.textContent = '✓ 分析完成,正在跳转...';
      spinnerEl.classList.add('done');
      setTimeout(() => window.location = '/report/' + j.report_dir, 900);
      return;
    } else if (j.status === 'error') {
      phaseEl.textContent = '✗ 分析失败,请查看日志';
      spinnerEl.classList.add('error');
      return;
    }
  } catch (e) { console.error(e); }
  setTimeout(poll, 1500);
}
poll();
</script>
</body>
</html>
"""


def run_analysis(job_id: str, ticker: str, depth: str):
    job = JOBS[job_id]

    # 等队列(若并发已满)
    while True:
        with _queue_lock:
            if job_id not in _queue and len(_running) < MAX_CONCURRENT:
                _running.add(job_id)
                break
            if job_id in _queue and _queue[0] == job_id and len(_running) < MAX_CONCURRENT:
                _queue.popleft()
                _running.add(job_id)
                break
            # 更新队列位置
            if job_id in _queue:
                job["queue_position"] = list(_queue).index(job_id) + 1
        threading.Event().wait(0.5)

    job["status"] = "running"
    job["started"] = datetime.now()
    cmd = ["python3", str(ROOT / "run.py"), ticker, "--depth", depth, "--no-browser"]
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=str(ROOT),
        )
        for line in proc.stdout:
            job["log"] += line
            job["log_display"] = re.sub(r"\x1b\[[0-9;]*m", "", job["log"])[-12000:]
        proc.wait()
        if proc.returncode != 0:
            job["status"] = "error"
            return
        candidates = sorted(
            [p for p in REPORTS_DIR.glob("*") if p.is_dir()
             and (p / "full-report.html").exists()],
            key=lambda p: p.stat().st_mtime, reverse=True
        )
        if candidates:
            job["report_dir"] = candidates[0].name
            job["status"] = "done"
        else:
            job["status"] = "error"
            job["log"] += "\n\n✗ 未找到生成的报告文件"
    except Exception as e:
        job["status"] = "error"
        job["log"] += f"\n\n✗ 异常: {e}"
    finally:
        with _queue_lock:
            _running.discard(job_id)


def _get_build_info():
    import json
    version = "?"
    try:
        manifest = ROOT / ".claude-plugin" / "plugin.json"
        if manifest.exists():
            version = json.loads(manifest.read_text(encoding="utf-8")).get("version", "?")
    except Exception:
        pass
    # 以 webapp.py 最后修改时间作为 build date
    try:
        mtime = Path(__file__).stat().st_mtime
        build_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        build_date = "unknown"
    return version, build_date


def _extract_stock_name(report_dir: Path) -> str:
    """从 one-liner.txt 第一行提取股票中文名,失败返回空串。"""
    f = report_dir / "one-liner.txt"
    if not f.exists():
        return ""
    try:
        first = f.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
        # 形如 "阳光电源 体检结果:..." / "金圆股份 体检结果:..."
        m = re.match(r"^([^\s]+?)\s*体检结果", first)
        if m:
            return m.group(1)
        # 兜底:第一个空格前
        return first.split()[0] if first else ""
    except Exception:
        return ""


@app.route("/")
def index():
    recent = []
    if REPORTS_DIR.exists():
        dirs = sorted(
            [p for p in REPORTS_DIR.glob("*") if p.is_dir()
             and (p / "full-report.html").exists()],
            key=lambda p: p.stat().st_mtime, reverse=True
        )[:10]
        for d in dirs:
            # 目录名 e.g. "600519.SH_20260420" → code="600519.SH"
            code = d.name.rsplit("_", 1)[0] if "_" in d.name else d.name
            recent.append({
                "name": d.name,
                "code": code,
                "stock_name": _extract_stock_name(d),
                "mtime": datetime.fromtimestamp(d.stat().st_mtime).strftime("%m-%d %H:%M"),
            })
    version, build_date = _get_build_info()
    return render_template_string(INDEX_HTML, recent=recent,
                                   version=version, build_date=build_date)


def find_existing_report(user_input: str, max_age_days: int = 3):
    """查找最近的已有报告。返回 (report_dir_name, age_days) 或 None。"""
    if not REPORTS_DIR.exists():
        return None
    user_norm = user_input.strip().upper()
    if not user_norm:
        return None
    now = datetime.now()
    candidates = []
    for p in REPORTS_DIR.glob("*"):
        if not p.is_dir() or not (p / "full-report.html").exists():
            continue
        # 文件夹名类似: 600519.SH_20260420
        try:
            core, date_str = p.name.rsplit("_", 1)
            report_date = datetime.strptime(date_str, "%Y%m%d")
        except (ValueError, IndexError):
            continue
        age = (now - report_date).days
        if age > max_age_days:
            continue
        # 匹配:完整代码 / 去后缀 / 大小写不敏感
        core_up = core.upper()
        core_bare = core_up.split(".")[0]  # 600519.SH → 600519
        if user_norm == core_up or user_norm == core_bare:
            candidates.append((p.name, age))
    if candidates:
        # 最新的优先
        candidates.sort(key=lambda x: x[1])
        return candidates[0]
    return None


@app.route("/analyze", methods=["POST"])
def analyze():
    ticker = request.form.get("ticker", "").strip()
    depth = request.form.get("depth", "medium")
    force = request.form.get("force") == "on"
    if not ticker:
        return redirect(url_for("index"))

    # 🆕 缓存命中 → 直接跳转(除非强制刷新)
    if not force:
        existing = find_existing_report(ticker, max_age_days=3)
        if existing:
            report_dir, age_days = existing
            age_tag = "today" if age_days == 0 else f"{age_days}d"
            return redirect(f"/report/{report_dir}/?cached={age_tag}")

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "ticker": ticker, "depth": depth, "status": "queued",
        "log": "", "log_display": "", "report_dir": None,
        "queue_position": 0,
    }
    with _queue_lock:
        if len(_running) >= MAX_CONCURRENT:
            _queue.append(job_id)
            JOBS[job_id]["queue_position"] = len(_queue)
    threading.Thread(target=run_analysis, args=(job_id, ticker, depth), daemon=True).start()
    return render_template_string(RUNNING_HTML, job_id=job_id, ticker=ticker, depth=depth)


@app.route("/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"status": "notfound"}), 404
    elapsed = int((datetime.now() - job["started"]).total_seconds()) if job.get("started") else 0
    # 如果还在排队,实时算位置
    q_pos = 0
    if job["status"] == "queued":
        with _queue_lock:
            if job_id in _queue:
                q_pos = list(_queue).index(job_id) + 1
    return jsonify({
        "status": job["status"],
        "log": job.get("log_display", ""),
        "report_dir": job.get("report_dir"),
        "elapsed": elapsed,
        "queue_position": q_pos,
        "running_count": len(_running),
        "max_concurrent": MAX_CONCURRENT,
    })


@app.route("/report/<name>/")
def report_index(name):
    return send_from_directory(REPORTS_DIR / name, "full-report.html")


@app.route("/report/<name>")
def report_redirect(name):
    return redirect(f"/report/{name}/")


@app.route("/report/<name>/<path:sub>")
def report_asset(name, sub):
    return send_from_directory(REPORTS_DIR / name, sub)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8976))
    print(f"🎯 Hot Money 启动: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
