#!/usr/bin/env python3
"""
x-download Web API
yt-dlp 視頻下載服務 / Video Downloader Web API
中英雙文界面 / Bilingual UI (中文為主 / Chinese primary)
"""
import os
import sys
import json
import uuid
import time
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template

# ============================================================
# Configuration
# ============================================================
BASE_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = Path(os.environ.get('DOWNLOAD_DIR', BASE_DIR / 'downloads'))
MAX_FILES = int(os.environ.get('MAX_FILES', 50))
PORT = int(os.environ.get('PORT', 8080))
LANG = os.environ.get('LANG', 'zh')

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# ============================================================
# Bilingual i18n (Chinese primary)
# ============================================================
I18N = {
    'zh': {
        'title': 'x-download',
        'subtitle': 'yt-dlp 視頻下載服務 / Video Downloader',
        'url_placeholder': '請輸入視頻鏈接 (YouTube / Bilibili / Twitter / 抖音...) / Enter video URL',
        'download_btn': '開始下載 / Start Download',
        'status': {
            'pending': '等待中 / Pending',
            'downloading': '下載中 / Downloading',
            'completed': '已完成 / Completed',
            'failed': '失敗 / Failed'
        },
        'delete_btn': '刪除 / Delete',
        'no_tasks': '暫無下載任務 / No download tasks',
        'max_notice': '最多保留 {} 個文件，超出自動刪除最早的文件 / Max {} files retained, oldest auto-deleted',
        'file': '文件 / File',
        'size': '大小 / Size',
        'time': '時間 / Time',
        'action': '操作 / Action',
        'confirm_delete': '確定刪除此文件? / Delete this file?',
        'error_required': '請輸入鏈接地址 / Please enter a URL',
        'error_network': '網絡錯誤，請稍後重試 / Network error, please try again',
        'success': '下載成功 / Download complete',
        'failed': '下載失敗 / Download failed',
        'downloading': '正在下載... / Downloading...',
    }
}

def t(key, *args):
    text = I18N.get('zh', {}).get(key, key)
    if args:
        text = text.format(*args)
    return text

# ============================================================
# Task Management
# ============================================================
tasks = {}
tasks_lock = threading.Lock()

def cleanup_old_files():
    """Delete oldest files when count exceeds MAX_FILES."""
    try:
        files = sorted(DOWNLOAD_DIR.glob('*'), key=lambda p: p.stat().st_mtime, reverse=True)
        if len(files) > MAX_FILES:
            for old_file in files[MAX_FILES:]:
                try:
                    old_file.unlink()
                    print(f"[cleanup] Deleted: {old_file.name}")
                except Exception as e:
                    print(f"[cleanup] Failed to delete {old_file.name}: {e}")
    except Exception as e:
        print(f"[cleanup] Error: {e}")

def get_file_size(path):
    try:
        size = path.stat().st_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
    except Exception:
        return "N/A"

def time_ago(timestamp):
    diff = time.time() - timestamp
    if diff < 60:
        return "剛剛 / just now"
    elif diff < 3600:
        m = int(diff // 60)
        return f"{m}分鐘前 / {m}m ago"
    elif diff < 86400:
        h = int(diff // 3600)
        return f"{h}小時前 / {h}h ago"
    else:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

# ============================================================
# Download Worker
# ============================================================
def download_worker(task_id, url):
    with tasks_lock:
        tasks[task_id]['status'] = 'downloading'
        tasks[task_id]['updated_at'] = time.time()
    
    output_template = str(DOWNLOAD_DIR / '%(title)s.%(ext)s')
    cmd = [
        'yt-dlp',
        '--no-warnings',
        '--no-playlist',
        '-o', output_template,
        '--merge-output-format', 'mp4',
        url
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(DOWNLOAD_DIR)
        )
        
        if result.returncode == 0:
            files = sorted(DOWNLOAD_DIR.glob('*'), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                newest = files[0]
                with tasks_lock:
                    tasks[task_id]['status'] = 'completed'
                    tasks[task_id]['file'] = newest.name
                    tasks[task_id]['file_path'] = str(newest)
                    tasks[task_id]['size'] = get_file_size(newest)
                    tasks[task_id]['updated_at'] = time.time()
                cleanup_old_files()
            else:
                with tasks_lock:
                    tasks[task_id]['status'] = 'completed'
                    tasks[task_id]['file'] = 'unknown'
                    tasks[task_id]['updated_at'] = time.time()
        else:
            stderr = result.stderr.strip()[:200] if result.stderr else 'Unknown error'
            with tasks_lock:
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['error'] = stderr
                tasks[task_id]['updated_at'] = time.time()
    except subprocess.TimeoutExpired:
        with tasks_lock:
            tasks[task_id]['status'] = 'failed'
            tasks[task_id]['error'] = '下載超時 (5分鐘) / Download timeout (5 minutes)'
            tasks[task_id]['updated_at'] = time.time()
    except Exception as e:
        with tasks_lock:
            tasks[task_id]['status'] = 'failed'
            tasks[task_id]['error'] = str(e)
            tasks[task_id]['updated_at'] = time.time()

# ============================================================
# Routes
# ============================================================
@app.route('/')
def index():
    return render_template('index.html', lang=LANG)

@app.route('/api/download', methods=['POST'])
def start_download():
    data = request.get_json(force=True) or {}
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'message': t('error_required')}), 400
    
    task_id = str(uuid.uuid4())
    with tasks_lock:
        tasks[task_id] = {
            'task_id': task_id,
            'url': url,
            'status': 'pending',
            'created_at': time.time(),
            'updated_at': time.time(),
            'file': None,
            'size': None,
            'error': None,
        }
    
    thread = threading.Thread(target=download_worker, args=(task_id, url), daemon=True)
    thread.start()
    
    return jsonify({'success': True, 'task_id': task_id})

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    task_list = list(tasks.values())
    task_list.sort(key=lambda x: x['created_at'], reverse=True)
    
    result = []
    for task in task_list:
        result.append({
            'task_id': task['task_id'],
            'url': task['url'],
            'status': task['status'],
            'file': task.get('file'),
            'size': task.get('size'),
            'error': task.get('error'),
            'created_at': task['created_at'],
            'time_ago': time_ago(task['created_at']),
        })
    
    return jsonify({
        'tasks': result,
        'max_files': MAX_FILES,
        'downloads_dir': str(DOWNLOAD_DIR),
        'lang': LANG,
    })

@app.route('/api/delete', methods=['POST'])
def delete_task():
    data = request.get_json(force=True) or {}
    task_id = data.get('task_id', '').strip()
    
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': t('error_required')}), 404
        
        file_path = task.get('file_path')
        if file_path and Path(file_path).exists():
            try:
                Path(file_path).unlink()
            except Exception as e:
                print(f"[delete] Failed to delete file: {e}")
        
        del tasks[task_id]
    
    return jsonify({'success': True, 'message': t('success')})

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'max_files': MAX_FILES,
        'port': PORT,
        'lang': LANG,
        'downloads_dir': str(DOWNLOAD_DIR),
    })

@app.route('/downloads/<path:filename>')
def serve_file(filename):
    file_path = DOWNLOAD_DIR / filename
    if file_path.exists() and file_path.is_file():
        return send_file(str(file_path), as_attachment=True, download_name=filename)
    return jsonify({'error': 'File not found'}), 404

# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print(f"[x-download] Starting on port {PORT}, max_files={MAX_FILES}, lang={LANG}")
    print(f"[x-download] Downloads: {DOWNLOAD_DIR}")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
