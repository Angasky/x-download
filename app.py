#!/usr/bin/env python3
"""
x-download - 视频下载服务
基于 Flask + yt-dlp 的网页版视频下载工具
"""

import os
import sys
import json
import time
import uuid
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, after_this_request

app = Flask(__name__)

# 配置
PORT = int(os.getenv('PORT', 8080))
MAX_FILES = int(os.getenv('MAX_FILES', 50))
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', '/opt/x-download/downloads')

# 确保下载目录存在
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)


def get_video_info(url: str) -> dict:
    """获取视频信息"""
    try:
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-download', url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return {
                'title': info.get('title', '未知标题'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', '未知'),
                'success': True
            }
    except Exception as e:
        pass
    return {'success': False, 'error': '无法获取视频信息'}


def download_video(url: str, task_id: str, format_id: str = 'best') -> dict:
    """下载视频"""
    try:
        output_template = os.path.join(DOWNLOAD_DIR, f'%(title)s_{task_id}.%(ext)s')
        
        cmd = [
            'yt-dlp',
            '-o', output_template,
            '--no-playlist',
            '-f', format_id,
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # 查找下载的文件
            for f in os.listdir(DOWNLOAD_DIR):
                if task_id in f:
                    file_path = os.path.join(DOWNLOAD_DIR, f)
                    return {
                        'success': True,
                        'file': f,
                        'path': file_path,
                        'size': os.path.getsize(file_path)
                    }
        
        return {'success': False, 'error': result.stderr or '下载失败'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': '下载超时'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def cleanup_old_files():
    """清理旧文件，保留最新的 MAX_FILES 个"""
    try:
        files = sorted(
            [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))],
            key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)),
            reverse=True
        )
        
        if len(files) > MAX_FILES:
            for old_file in files[MAX_FILES:]:
                os.remove(os.path.join(DOWNLOAD_DIR, old_file))
    except Exception:
        pass


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def api_info():
    """获取视频信息"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'error': '请输入视频链接'})
    
    info = get_video_info(url)
    return jsonify(info)


@app.route('/api/download', methods=['POST'])
def api_download():
    """下载视频"""
    data = request.get_json()
    url = data.get('url', '').strip()
    format_id = data.get('format', 'best')
    
    if not url:
        return jsonify({'success': False, 'error': '请输入视频链接'})
    
    task_id = str(uuid.uuid4())[:8]
    result = download_video(url, task_id, format_id)
    
    if result['success']:
        cleanup_old_files()
    
    return jsonify(result)


@app.route('/api/formats', methods=['POST'])
def api_formats():
    """获取可用格式"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'error': '请输入视频链接', 'formats': []})
    
    try:
        result = subprocess.run(
            ['yt-dlp', '-F', url],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            formats = []
            for line in lines[3:]:  # 跳过表头
                parts = line.split()
                if len(parts) >= 2:
                    formats.append({
                        'id': parts[0],
                        'desc': ' '.join(parts[1:])
                    })
            return jsonify({'success': True, 'formats': formats[:20]})  # 最多返回20个
    except Exception as e:
        pass
    
    return jsonify({'success': False, 'error': '获取格式失败', 'formats': []})


@app.route('/download/<filename>')
def serve_file(filename):
    """提供文件下载"""
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    
    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404
    
    @after_this_request
    def remove_file(response):
        try:
            os.remove(file_path)
        except Exception:
            pass
        return response
    
    return send_file(file_path, as_attachment=True)


@app.route('/api/status')
def api_status():
    """服务状态"""
    file_count = len([f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))])
    return jsonify({
        'status': 'running',
        'files': file_count,
        'max_files': MAX_FILES,
        'download_dir': DOWNLOAD_DIR
    })


if __name__ == '__main__':
    print(f"x-download 服务启动中...")
    print(f"访问地址: http://0.0.0.0:{PORT}")
    print(f"下载目录: {DOWNLOAD_DIR}")
    print(f"最大保留文件数: {MAX_FILES}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
