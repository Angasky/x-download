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
LANG = os.getenv('LANG', 'zh')

# 确保下载目录存在
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

# 多语言文本
I18N = {
    'zh': {
        'title': 'x-download - 视频下载工具',
        'subtitle': '简单快速的视频下载工具',
        'placeholder': '粘贴视频链接（支持 YouTube、抖音、B站等）',
        'get_info': '获取信息',
        'getting': '获取中...',
        'download': '开始下载',
        'downloading': '下载中...',
        'select_quality': '选择画质：',
        'best_quality': '最佳画质（推荐）',
        'status': '服务状态',
        'running': '✓ 运行中',
        'stopped': '✗ 已停止',
        'connection_failed': '✗ 连接失败',
        'current_files': '当前文件数',
        'max_files': '最大保留数',
        'help_title': '使用说明',
        'help_1': '粘贴视频链接，点击"获取信息"查看视频详情',
        'help_2': '选择合适的画质，点击"开始下载"',
        'help_3': '下载完成后会自动保存到服务器',
        'help_4': '支持 YouTube、抖音、B站、Twitter 等主流平台',
        'help_5': '系统会自动清理旧文件，保持最新的 {max} 个视频',
        'footer': 'Powered by yt-dlp | x-download v1.0',
        'download_success': '✓ 下载成功！',
        'download_failed': '✗ 下载失败',
        'file_name': '文件名',
        'file_size': '大小',
        'request_failed': '✗ 请求失败',
        'enter_url': '请输入视频链接',
        'no_info': '无法获取视频信息',
        'duration_unknown': '未知',
        'uploader': '上传者',
        'duration': '时长',
        'hour': '小时',
        'minute': '分',
        'second': '秒',
        'download_complete': '下载完成！',
        'downloading_progress': '正在下载... {pct}%',
        'status_running': '运行中',
        'status_stopped': '已停止',
    },
    'en': {
        'title': 'x-download - Video Downloader',
        'subtitle': 'Simple and fast video downloader',
        'placeholder': 'Paste video URL (supports YouTube, TikTok, Bilibili, etc.)',
        'get_info': 'Get Info',
        'getting': 'Getting...',
        'download': 'Start Download',
        'downloading': 'Downloading...',
        'select_quality': 'Select Quality:',
        'best_quality': 'Best Quality (Recommended)',
        'status': 'Service Status',
        'running': '✓ Running',
        'stopped': '✗ Stopped',
        'connection_failed': '✗ Connection Failed',
        'current_files': 'Current Files',
        'max_files': 'Max Files',
        'help_title': 'Instructions',
        'help_1': 'Paste video URL and click "Get Info" to view details',
        'help_2': 'Select quality and click "Start Download"',
        'help_3': 'Downloaded files are automatically saved to server',
        'help_4': 'Supports YouTube, TikTok, Bilibili, Twitter and more',
        'help_5': 'System automatically cleans old files, keeps latest {max} videos',
        'footer': 'Powered by yt-dlp | x-download v1.0',
        'download_success': '✓ Download Success!',
        'download_failed': '✗ Download Failed',
        'file_name': 'File Name',
        'file_size': 'Size',
        'request_failed': '✗ Request Failed',
        'enter_url': 'Please enter video URL',
        'no_info': 'Unable to get video info',
        'duration_unknown': 'Unknown',
        'uploader': 'Uploader',
        'duration': 'Duration',
        'hour': 'h',
        'minute': 'm',
        'second': 's',
        'download_complete': 'Download Complete!',
        'downloading_progress': 'Downloading... {pct}%',
        'status_running': 'Running',
        'status_stopped': 'Stopped',
    }
}


def get_lang():
    """获取当前语言"""
    # 优先 URL 参数，其次环境变量，默认中文
    lang = request.args.get('lang', LANG)
    if lang not in I18N:
        lang = 'zh'
    return lang


def t(key, **kwargs):
    """翻译文本"""
    lang = get_lang()
    text = I18N.get(lang, {}).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


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
                'title': info.get('title', t('no_info')),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', t('uploader')),
                'success': True
            }
    except Exception as e:
        pass
    return {'success': False, 'error': t('no_info')}


def download_video(url: str, task_id: str, format_id: str = '') -> dict:
    """下载视频"""
    try:
        output_template = os.path.join(DOWNLOAD_DIR, f'%(title)s_{task_id}.%(ext)s')
        
        cmd = [
            'yt-dlp',
            '-o', output_template,
            '--no-playlist',
            url
        ]
        if format_id:
            cmd = [
                'yt-dlp',
                '-o', output_template,
                '--no-playlist',
                '-f', format_id,
                url
            ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            for f in os.listdir(DOWNLOAD_DIR):
                if task_id in f:
                    file_path = os.path.join(DOWNLOAD_DIR, f)
                    return {
                        'success': True,
                        'file': f,
                        'path': file_path,
                        'size': os.path.getsize(file_path)
                    }
        
        return {'success': False, 'error': result.stderr or t('download_failed')}
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': t('download_failed')}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def cleanup_old_files():
    """清理旧文件"""
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
    return render_template('index.html', 
                         lang=get_lang(),
                         max_files=MAX_FILES,
                         t=t)


@app.route('/api/info', methods=['POST'])
def api_info():
    """获取视频信息"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'error': t('enter_url')})
    
    info = get_video_info(url)
    return jsonify(info)


@app.route('/api/download', methods=['POST'])
def api_download():
    """下载视频"""
    data = request.get_json()
    url = data.get('url', '').strip()
    format_id = data.get('format', '')
    
    if not url:
        return jsonify({'success': False, 'error': t('enter_url')})
    
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
        return jsonify({'success': False, 'error': t('enter_url'), 'formats': []})
    
    try:
        result = subprocess.run(
            ['yt-dlp', '-F', url],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            formats = []
            for line in lines[3:]:
                parts = line.split()
                if len(parts) >= 2:
                    formats.append({
                        'id': parts[0],
                        'desc': ' '.join(parts[1:])
                    })
            return jsonify({'success': True, 'formats': formats[:20]})
    except Exception as e:
        pass
    
    return jsonify({'success': False, 'error': t('no_info'), 'formats': []})


@app.route('/download/<filename>')
def serve_file(filename):
    """提供文件下载"""
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    
    if not os.path.exists(file_path):
        return jsonify({'error': t('no_info')}), 404
    
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


@app.route('/api/i18n')
def api_i18n():
    """获取前端翻译文本"""
    lang = request.args.get('lang', 'zh')
    if lang not in I18N:
        lang = 'zh'
    return jsonify(I18N[lang])


if __name__ == '__main__':
    print(f"x-download 服务启动中... / Starting...")
    print(f"访问地址 / URL: http://0.0.0.0:{PORT}")
    print(f"下载目录 / Download dir: {DOWNLOAD_DIR}")
    print(f"语言 / Language: {LANG}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
