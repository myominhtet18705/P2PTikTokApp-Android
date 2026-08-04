"""
P2P OFFLINE TIKTOK v23 - SELF-CONTAINED PORTABLE
✅ Account & Database ကို Script ထဲမှာကို သိမ်းဆည်းထား
✅ ဘယ် LAN ပြောင်းပြောင်း အကောင့်ဟောင်း အလိုအလျောက်ပါလာ
✅ လူကိုယ်တိုင် DB သယ်စရာ၊ Path ပြန်ပြင်စရာ မလို
✅ Video ဖိုင်တွေကို P2P Sync မှ ပြန်ဆွဲယူ
"""

import os
import sys
import time
import json
import uuid
import socket
import sqlite3
import threading
import logging
import base64
import atexit
import re
from datetime import datetime
from functools import wraps

import shutil
import requests

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, send_from_directory, jsonify
)

# ==================== CONFIGURATION ====================
# Android app ရဲ့ private data folder ကို Kotlin (MainActivity) ကနေ
# environment variable အဖြစ် ပေးပို့ပေးမှာဖြစ်ပါတယ်။ ဒီလိုမပါလာရင်
# (PC ပေါ်မှာ တိုက်ရိုက် run ရင်) လက်ရှိ folder ကိုပဲ သုံးမယ်။
APP_DATA_DIR = os.environ.get('APP_DATA_DIR', os.path.dirname(os.path.abspath(__file__)))

UPLOAD_FOLDER = os.path.join(APP_DATA_DIR, 'uploads')
THUMBNAIL_FOLDER = os.path.join(APP_DATA_DIR, 'thumbnails')
PROFILE_PICS_FOLDER = os.path.join(APP_DATA_DIR, 'profile_pics')
DATABASE_FILE = os.path.join(APP_DATA_DIR, 'p2p_offline.db')
PEER_DISCOVERY_PORT = 5001
MAX_VIDEO_SIZE = 500 * 1024 * 1024

app = Flask(__name__)
app.secret_key = 'p2p_offline_secret_key_2024'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_VIDEO_SIZE

for folder in [UPLOAD_FOLDER, THUMBNAIL_FOLDER, PROFILE_PICS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== SELF-CONTAINED DB LOGIC (NEW) ====================
# ဒီနေရာမှာ Database ကို Base64 နဲ့ သိမ်းမယ်။
# ပထမဆုံး Run ချိန်မှာ ဒီ String က အလွတ်ဖြစ်နေမယ်။
# App ပိတ်တဲ့အခါ ဒီ String ထဲကို ပြန်ရေးသွင်းပေးမယ်။
EMBEDDED_DB_B64 = ""

def embed_db_into_script():
    """လက်ရှိ p2p_offline.db ကို Base64 ပြောင်းပြီး ဒီ Script ထဲမှာ ပြန်သိမ်းတယ်။
    Android ပေါ်မှာတော့ DB က APP_DATA_DIR ထဲမှာ တိုက်ရိုက် persist ဖြစ်နေပြီးသား
    ဖြစ်လို့ ဒီ trick မလိုအပ်တော့ဘူး (Chaquopy က .py ဖိုင်ကို install တိုင်း ပြန် extract
    လုပ်လို့ ဒီထဲ ပြန်ရေးထားလည်း မထိန်းသိမ်းနိုင်ဘူး)။"""
    if 'APP_DATA_DIR' in os.environ:
        return
    global EMBEDDED_DB_B64
    try:
        db_path = os.path.join(os.path.dirname(__file__), DATABASE_FILE)
        if not os.path.exists(db_path):
            return
        
        with open(db_path, 'rb') as f:
            db_bytes = f.read()
        new_b64 = base64.b64encode(db_bytes).decode('ascii')
        
        script_path = os.path.abspath(__file__)
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # ဟောင်းနေတဲ့ Base64 String ကို အသစ်နဲ့ အစားထိုးတယ်
        pattern = r'EMBEDDED_DB_B64 = ".*?"'
        replacement = f'EMBEDDED_DB_B64 = "{new_b64}"'
        
        if re.search(pattern, content):
            new_content = re.sub(pattern, replacement, content)
        else:
            # မတွေ့ရင် နေရာထည့်ပေးတယ်
            insert_pos = content.find('EMBEDDED_DB_B64 = ""')
            if insert_pos != -1:
                new_content = content.replace('EMBEDDED_DB_B64 = ""', replacement)
            else:
                new_content = content + f'\n\nEMBEDDED_DB_B64 = "{new_b64}"'
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        logger.info("✅ Database successfully embedded into script.")
    except Exception as e:
        logger.error(f"❌ Failed to embed DB: {e}")

def restore_db_from_script():
    """Script ထဲက Base64 ကနေ p2p_offline.db ကို ပြန်ဖော်ထုတ်တယ်။"""
    if 'APP_DATA_DIR' in os.environ:
        return
    # Database ရှိပြီးသားဆိုရင် မလုပ်တော့ဘူး (အရှိန်မြှင့်ဖို့)
    if os.path.exists(DATABASE_FILE):
        return
    
    if not EMBEDDED_DB_B64:
        logger.info("ℹ️ No embedded DB found. Creating new database on first run.")
        return
    
    try:
        db_bytes = base64.b64decode(EMBEDDED_DB_B64)
        with open(DATABASE_FILE, 'wb') as f:
            f.write(db_bytes)
        logger.info("✅ Database restored from embedded script.")
    except Exception as e:
        logger.error(f"❌ Failed to restore DB: {e}")

# ==================== DATABASE ====================
def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        profile_pic TEXT DEFAULT '',
        theme TEXT DEFAULT 'dark',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE NOT NULL,
        thumbnail TEXT DEFAULT '',
        description TEXT,
        user_id INTEGER,
        likes INTEGER DEFAULT 0,
        saves INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        is_private INTEGER DEFAULT 0,
        is_deleted INTEGER DEFAULT 0,
        is_cache INTEGER DEFAULT 0,
        size_bytes INTEGER DEFAULT 0,
        peer_ip TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER,
        user_id INTEGER,
        comment_text TEXT,
        likes INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(video_id) REFERENCES videos(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS video_likes (
        user_id INTEGER,
        video_id INTEGER,
        PRIMARY KEY(user_id, video_id)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS video_views (
        user_id INTEGER,
        video_id INTEGER,
        viewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id, video_id)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS follows (
        follower_id INTEGER,
        following_id INTEGER,
        PRIMARY KEY(follower_id, following_id)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        message_text TEXT,
        is_read INTEGER DEFAULT 0,
        is_seen INTEGER DEFAULT 0,
        is_deleted_for_all INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sender_id) REFERENCES users(id),
        FOREIGN KEY(receiver_id) REFERENCES users(id)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        from_user_id INTEGER,
        video_id INTEGER DEFAULT 0,
        comment_id INTEGER DEFAULT 0,
        is_read INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(from_user_id) REFERENCES users(id)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS peer_index (
        peer_ip TEXT,
        video_filename TEXT,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(peer_ip, video_filename)
    )''')
    
    conn.execute('CREATE INDEX IF NOT EXISTS idx_videos_user_id ON videos(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_videos_views ON videos(views DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver_id ON messages(receiver_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

# ==================== P2P FUNCTIONS ====================
peers = set()
peer_lock = threading.Lock()
device_id = str(uuid.uuid4())[:8]
local_ip = None

def get_local_ip():
    global local_ip
    if local_ip:
        return local_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        local_ip = ip
        return ip
    except:
        local_ip = "127.0.0.1"
        return "127.0.0.1"

def broadcast_presence():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            sock.sendto(b"P2P_DISCOVER", ('255.255.255.255', PEER_DISCOVERY_PORT))
        except:
            pass
        time.sleep(3)

def listen_for_peers():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', PEER_DISCOVERY_PORT))
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if data == b"P2P_DISCOVER" and addr[0] != get_local_ip():
                with peer_lock:
                    if addr[0] not in peers:
                        peers.add(addr[0])
                        logger.info(f"Peer found: {addr[0]}")
        except:
            break

def get_peer_video_list(peer_ip):
    try:
        response = requests.get(f"http://{peer_ip}:5000/api/videos/list", timeout=3)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def download_from_peer(peer_ip, filename):
    try:
        response = requests.get(f"http://{peer_ip}:5000/uploads/{filename}", stream=True, timeout=30)
        if response.status_code == 200:
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
    except:
        pass
    return False

def auto_sync():
    while True:
        try:
            for peer in list(peers):
                videos = get_peer_video_list(peer)
                if not videos:
                    continue
                conn = get_db_connection()
                for v in videos:
                    existing = conn.execute('SELECT id FROM videos WHERE filename = ?', (v['filename'],)).fetchone()
                    if not existing:
                        filepath = os.path.join(UPLOAD_FOLDER, v['filename'])
                        if not os.path.exists(filepath):
                            if download_from_peer(peer, v['filename']):
                                size = os.path.getsize(filepath)
                                conn.execute(
                                    '''INSERT INTO videos (filename, description, user_id, likes, views, size_bytes, is_cache, peer_ip, created_at)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                    (v['filename'], v.get('description', ''), v['user_id'], v.get('likes', 0), v.get('views', 0),
                                     size, 1, peer, v.get('created_at', datetime.now().isoformat()))
                                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"Auto sync error: {e}")
        time.sleep(20)

# ==================== DECORATORS ====================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Please login first'}), 401
            return redirect(url_for('profile'))
        return f(*args, **kwargs)
    return decorated

# ==================== STORAGE FUNCTIONS ====================
def get_storage_info():
    try:
        usage = shutil.disk_usage(APP_DATA_DIR)
        percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0
        return {
            'total': usage.total,
            'used': usage.used,
            'free': usage.free,
            'percent': percent,
            'total_gb': round(usage.total / (1024**3), 1),
            'used_gb': round(usage.used / (1024**3), 1),
            'free_gb': round(usage.free / (1024**3), 1)
        }
    except:
        return {'total': 0, 'used': 0, 'free': 0, 'percent': 0, 'total_gb': 0, 'used_gb': 0, 'free_gb': 0}

def get_video_storage(user_id):
    conn = get_db_connection()
    own = conn.execute('SELECT size_bytes FROM videos WHERE user_id = ? AND is_deleted = 0 AND is_cache = 0', (user_id,)).fetchall()
    own_size = sum([v['size_bytes'] for v in own])
    own_count = len(own)
    cache = conn.execute('SELECT size_bytes FROM videos WHERE user_id != ? AND is_deleted = 0 AND is_cache = 1', (user_id,)).fetchall()
    cache_size = sum([v['size_bytes'] for v in cache])
    cache_count = len(cache)
    conn.close()
    return {
        'own': {'size': own_size, 'count': own_count, 'size_gb': round(own_size/(1024**3), 1)},
        'cache': {'size': cache_size, 'count': cache_count, 'size_gb': round(cache_size/(1024**3), 1)},
        'total_gb': round((own_size + cache_size) / (1024**3), 1)
    }

# ==================== DELETE FUNCTIONS ====================
def delete_videos_with_options(user_id, sort_by='new', amount=10, unit='MB'):
    if unit == 'GB':
        target_bytes = amount * 1024 * 1024 * 1024
    else:
        target_bytes = amount * 1024 * 1024
    
    conn = get_db_connection()
    
    if sort_by == 'new':
        videos = conn.execute('SELECT * FROM videos WHERE user_id = ? AND is_deleted = 0 ORDER BY created_at DESC', (user_id,)).fetchall()
    else:
        videos = conn.execute('SELECT * FROM videos WHERE user_id = ? AND is_deleted = 0 ORDER BY created_at ASC', (user_id,)).fetchall()
    
    total_size = 0
    to_delete = []
    
    for video in videos:
        filepath = os.path.join(UPLOAD_FOLDER, video['filename'])
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            if total_size + size <= target_bytes:
                total_size += size
                to_delete.append(video)
            else:
                break
    
    deleted_count = 0
    for video in to_delete:
        try:
            filepath = os.path.join(UPLOAD_FOLDER, video['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
            if video['thumbnail']:
                thumbpath = os.path.join(THUMBNAIL_FOLDER, video['thumbnail'])
                if os.path.exists(thumbpath):
                    os.remove(thumbpath)
            conn.execute('DELETE FROM videos WHERE id = ?', (video['id'],))
            conn.execute('DELETE FROM video_likes WHERE video_id = ?', (video['id'],))
            conn.execute('DELETE FROM video_views WHERE video_id = ?', (video['id'],))
            conn.execute('DELETE FROM comments WHERE video_id = ?', (video['id'],))
            deleted_count += 1
        except Exception as e:
            logger.error(f"Delete error: {e}")
    
    conn.commit()
    conn.close()
    return {'deleted_count': deleted_count, 'total_size_mb': round(total_size / (1024**2), 1), 'total_size_gb': round(total_size / (1024**3), 1)}

def delete_single_video(video_id, user_id):
    conn = get_db_connection()
    video = conn.execute('SELECT * FROM videos WHERE id = ? AND user_id = ? AND is_deleted = 0', (video_id, user_id)).fetchone()
    if not video:
        conn.close()
        return False
    try:
        filepath = os.path.join(UPLOAD_FOLDER, video['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)
        if video['thumbnail']:
            thumbpath = os.path.join(THUMBNAIL_FOLDER, video['thumbnail'])
            if os.path.exists(thumbpath):
                os.remove(thumbpath)
        conn.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.execute('DELETE FROM video_likes WHERE video_id = ?', (video_id,))
        conn.execute('DELETE FROM video_views WHERE video_id = ?', (video_id,))
        conn.execute('DELETE FROM comments WHERE video_id = ?', (video_id,))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

# ==================== ROUTES ====================

@app.route('/')
def index():
    try:
        user_id = session.get('user_id', 0)
        sort = request.args.get('sort', 'new')
        
        conn = get_db_connection()
        
        query = '''SELECT v.*, u.username, u.profile_pic FROM videos v 
                   JOIN users u ON v.user_id = u.id
                   WHERE v.is_deleted = 0'''
        params = []
        
        if sort == 'following' and user_id:
            following = conn.execute('SELECT following_id FROM follows WHERE follower_id = ?', (user_id,)).fetchall()
            following_ids = [f['following_id'] for f in following]
            if following_ids:
                placeholders = ','.join(['?'] * len(following_ids))
                query += f' AND v.user_id IN ({placeholders})'
                params.extend(following_ids)
            else:
                conn.close()
                storage = get_storage_info()
                return render_template_string(MAIN_TEMPLATE, 
                                              videos=[], 
                                              user_id=user_id,
                                              peers=len(peers),
                                              local_ip=get_local_ip(),
                                              storage_percent=storage['percent'],
                                              current_sort=sort)
        
        if sort == 'new':
            query += ' ORDER BY v.created_at DESC'
        elif sort == 'old':
            query += ' ORDER BY v.created_at ASC'
        elif sort == 'random':
            query += ' ORDER BY RANDOM()'
        elif sort == 'following':
            query += ' ORDER BY v.created_at DESC'
        else:
            query += ' ORDER BY v.created_at DESC'
        
        query += ' LIMIT 50'
        
        videos = conn.execute(query, params).fetchall()
        conn.close()
        
        storage = get_storage_info()
        return render_template_string(MAIN_TEMPLATE, 
                                      videos=videos, 
                                      user_id=user_id,
                                      peers=len(peers),
                                      local_ip=get_local_ip(),
                                      storage_percent=storage['percent'],
                                      current_sort=sort)
    except Exception as e:
        logger.error(f"Index error: {e}")
        return render_template_string(MAIN_TEMPLATE, videos=[], user_id=0, peers=0, local_ip='127.0.0.1', storage_percent=0, current_sort='new')

@app.route('/profile')
@app.route('/profile/<username>')
def profile(username=None):
    try:
        conn = get_db_connection()
        
        if username is None:
            if 'user_id' not in session:
                return render_template_string(LOGIN_TEMPLATE)
            user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            if not user:
                session.clear()
                return redirect('/')
            is_own = True
            viewer_id = session['user_id']
        else:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if not user:
                return "User not found", 404
            viewer_id = session.get('user_id')
            is_own = viewer_id == user['id']
        
        if is_own:
            videos = conn.execute('SELECT * FROM videos WHERE user_id = ? AND is_deleted = 0 ORDER BY created_at DESC', (user['id'],)).fetchall()
        else:
            videos = conn.execute('SELECT * FROM videos WHERE user_id = ? AND is_deleted = 0 AND is_private = 0 ORDER BY created_at DESC', (user['id'],)).fetchall()
        
        followers = conn.execute('SELECT COUNT(*) as count FROM follows WHERE following_id = ?', (user['id'],)).fetchone()
        following = conn.execute('SELECT COUNT(*) as count FROM follows WHERE follower_id = ?', (user['id'],)).fetchone()
        total_likes = conn.execute('SELECT COALESCE(SUM(likes), 0) as count FROM videos WHERE user_id = ? AND is_deleted = 0', (user['id'],)).fetchone()
        total_views = conn.execute('SELECT COALESCE(SUM(views), 0) as count FROM videos WHERE user_id = ? AND is_deleted = 0', (user['id'],)).fetchone()
        
        is_following = False
        if viewer_id and not is_own:
            follow = conn.execute('SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?', (viewer_id, user['id'])).fetchone()
            is_following = bool(follow)
        
        conn.close()
        
        storage = get_storage_info()
        video_storage = get_video_storage(user['id'])
        
        return render_template_string(PROFILE_TEMPLATE,
                                      user=user,
                                      videos=videos,
                                      is_own=is_own,
                                      is_following=is_following,
                                      followers=followers[0] if followers else 0,
                                      following=following[0] if following else 0,
                                      total_likes=total_likes[0] if total_likes else 0,
                                      total_views=total_views[0] if total_views else 0,
                                      storage=storage,
                                      video_storage=video_storage,
                                      peers=len(peers))
    except Exception as e:
        logger.error(f"Profile error: {e}")
        return f"Error loading profile: {str(e)}", 500

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    try:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            username = request.form.get('username', '').strip().lower()
            bio = request.form.get('bio', '').strip()
            
            if username and username != user['username']:
                existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
                if existing:
                    conn.close()
                    return '<script>alert("Username already taken!"); window.location.href="/profile/edit";</script>'
            
            if 'profile_pic' in request.files:
                file = request.files['profile_pic']
                if file and file.filename != '':
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"profile_{session['user_id']}_{int(time.time())}.{ext}"
                    filepath = os.path.join(PROFILE_PICS_FOLDER, filename)
                    file.save(filepath)
                    conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (filename, session['user_id']))
            
            conn.execute('UPDATE users SET name = ?, username = ?, bio = ? WHERE id = ?', (name, username, bio, session['user_id']))
            conn.commit()
            session['username'] = username
            conn.close()
            return redirect('/profile')
        
        conn.close()
        return render_template_string(EDIT_PROFILE_TEMPLATE, user=user)
    except Exception as e:
        logger.error(f"Edit profile error: {e}")
        return "Error editing profile", 500

@app.route('/inbox')
@login_required
def inbox():
    try:
        user_id = session['user_id']
        conn = get_db_connection()
        
        notifications = conn.execute(
            '''SELECT n.*, u.username, u.profile_pic FROM notifications n 
               JOIN users u ON n.from_user_id = u.id
               WHERE n.user_id = ? ORDER BY n.created_at DESC LIMIT 20''',
            (user_id,)
        ).fetchall()
        
        messages = conn.execute(
            '''SELECT m.*, u.username, u.profile_pic FROM messages m 
               JOIN users u ON m.sender_id = u.id
               WHERE m.receiver_id = ? AND m.is_deleted_for_all = 0 ORDER BY m.created_at DESC LIMIT 10''',
            (user_id,)
        ).fetchall()
        
        unread = conn.execute('SELECT COUNT(*) as count FROM messages WHERE receiver_id = ? AND is_read = 0', (user_id,)).fetchone()
        conn.close()
        
        return render_template_string(INBOX_TEMPLATE,
                                      notifications=notifications,
                                      messages=messages,
                                      unread=unread[0] if unread else 0)
    except Exception as e:
        logger.error(f"Inbox error: {e}")
        return "Error loading inbox", 500

@app.route('/chat')
@app.route('/chat/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def chat(receiver_id=None):
    try:
        conn = get_db_connection()
        my_id = session['user_id']
        
        if request.method == 'POST' and receiver_id:
            text = request.form.get('message', '').strip()
            if text:
                conn.execute('INSERT INTO messages (sender_id, receiver_id, message_text) VALUES (?, ?, ?)', (my_id, receiver_id, text))
                conn.commit()
            return redirect(url_for('chat', receiver_id=receiver_id))
        
        chat_list = conn.execute(
            '''SELECT DISTINCT u.id, u.username, u.profile_pic, u.bio,
               (SELECT message_text FROM messages WHERE ((sender_id = u.id AND receiver_id = ?) OR (sender_id = ? AND receiver_id = u.id)) AND is_deleted_for_all = 0 ORDER BY created_at DESC LIMIT 1) as last_message,
               (SELECT created_at FROM messages WHERE ((sender_id = u.id AND receiver_id = ?) OR (sender_id = ? AND receiver_id = u.id)) AND is_deleted_for_all = 0 ORDER BY created_at DESC LIMIT 1) as last_time,
               (SELECT COUNT(*) FROM messages WHERE sender_id = u.id AND receiver_id = ? AND is_read = 0 AND is_deleted_for_all = 0) as unread
               FROM users u
               WHERE u.id IN (SELECT sender_id FROM messages WHERE receiver_id = ? AND is_deleted_for_all = 0 UNION SELECT receiver_id FROM messages WHERE sender_id = ? AND is_deleted_for_all = 0)
               AND u.id != ?
               ORDER BY last_time DESC''',
            (my_id, my_id, my_id, my_id, my_id, my_id, my_id, my_id)
        ).fetchall()
        
        followed = conn.execute('SELECT following_id FROM follows WHERE follower_id = ?', (my_id,)).fetchall()
        followed_ids = [f['following_id'] for f in followed]
        
        if followed_ids:
            placeholders = ','.join(['?'] * len(followed_ids))
            suggestions = conn.execute(
                f'''SELECT id, username, profile_pic, bio FROM users 
                   WHERE id != ? AND id NOT IN ({placeholders}) 
                   ORDER BY RANDOM() LIMIT 6''',
                [my_id] + followed_ids
            ).fetchall()
        else:
            suggestions = conn.execute(
                '''SELECT id, username, profile_pic, bio FROM users 
                   WHERE id != ? ORDER BY RANDOM() LIMIT 6''',
                (my_id,)
            ).fetchall()
        
        active_chat_user = None
        chat_messages = []
        
        if receiver_id:
            active_chat_user = conn.execute('SELECT * FROM users WHERE id = ?', (receiver_id,)).fetchone()
            if active_chat_user:
                conn.execute('UPDATE messages SET is_read = 1, is_seen = 1 WHERE sender_id = ? AND receiver_id = ?', (receiver_id, my_id))
                conn.commit()
                chat_messages = conn.execute(
                    '''SELECT m.*, u.username, u.profile_pic FROM messages m 
                       JOIN users u ON m.sender_id = u.id
                       WHERE ((m.sender_id = ? AND m.receiver_id = ?) OR (m.sender_id = ? AND m.receiver_id = ?))
                       AND m.is_deleted_for_all = 0
                       ORDER BY m.created_at ASC''',
                    (my_id, receiver_id, receiver_id, my_id)
                ).fetchall()
        
        conn.close()
        
        return render_template_string(CHAT_TEMPLATE,
                                      chat_list=chat_list,
                                      active_chat_user=active_chat_user,
                                      chat_messages=chat_messages,
                                      my_id=my_id,
                                      receiver_id=receiver_id,
                                      suggestions=suggestions)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return "Error loading chat", 500

@app.route('/api/message/delete/<int:message_id>', methods=['POST'])
@login_required
def api_delete_message(message_id):
    user_id = session['user_id']
    conn = get_db_connection()
    
    msg = conn.execute('SELECT sender_id, receiver_id FROM messages WHERE id = ? AND is_deleted_for_all = 0', (message_id,)).fetchone()
    if not msg:
        conn.close()
        return jsonify({'error': 'Message not found'}), 404
    
    if msg['sender_id'] != user_id and msg['receiver_id'] != user_id:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
    
    conn.execute('UPDATE messages SET is_deleted_for_all = 1 WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Message deleted for everyone'})

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        try:
            if 'video' not in request.files:
                return '<script>alert("No file selected"); window.location.href="/upload";</script>'
            file = request.files['video']
            if file.filename == '':
                return '<script>alert("No file selected"); window.location.href="/upload";</script>'
            
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            if size > MAX_VIDEO_SIZE:
                return f'<script>alert("File too large (max {MAX_VIDEO_SIZE//(1024*1024)}MB)"); window.location.href="/upload";</script>'
            
            filename = file.filename
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(filepath):
                base, ext = os.path.splitext(filename)
                filename = f"{base}_{int(time.time())}{ext}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            description = request.form.get('description', '').strip()
            is_private = 1 if request.form.get('is_private') == 'on' else 0
            
            conn = get_db_connection()
            conn.execute('INSERT INTO videos (filename, description, user_id, is_private, size_bytes) VALUES (?, ?, ?, ?, ?)', (filename, description, session['user_id'], is_private, size))
            conn.commit()
            conn.close()
            return redirect('/')
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return f'<script>alert("Upload failed"); window.location.href="/upload";</script>'
    
    return UPLOAD_PAGE

@app.route('/uploads/<filename>')
def serve_video(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/profile_pics/<filename>')
def serve_profile_pic(filename):
    return send_from_directory(PROFILE_PICS_FOLDER, filename)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
    conn.close()
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect('/')
    return '<script>alert("Invalid username or password"); window.location.href="/profile";</script>'

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        if len(username) < 3:
            return '<script>alert("Username must be at least 3 characters"); window.location.href="/signup";</script>'
        if len(password) < 4:
            return '<script>alert("Password must be at least 4 characters"); window.location.href="/signup";</script>'
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password, name) VALUES (?, ?, ?)', (username, password, username))
            conn.commit()
            conn.close()
            return '<script>alert("Account created! Please login."); window.location.href="/profile";</script>'
        except sqlite3.IntegrityError:
            conn.close()
            return '<script>alert("Username already exists"); window.location.href="/signup";</script>'
    return SIGNUP_PAGE

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/api/theme', methods=['POST'])
@login_required
def api_set_theme():
    data = request.json
    theme = data.get('theme', 'dark')
    if theme not in ['dark', 'light']:
        return jsonify({'error': 'Invalid theme'}), 400
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET theme = ? WHERE id = ?', (theme, session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'theme': theme})

@app.route('/api/user/theme', methods=['GET'])
@login_required
def api_get_theme():
    conn = get_db_connection()
    user = conn.execute('SELECT theme FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return jsonify({'theme': user['theme'] if user else 'dark'})

# ==================== API ROUTES ====================

@app.route('/api/videos/list', methods=['GET'])
def api_videos_list():
    conn = get_db_connection()
    videos = conn.execute('SELECT filename, description, user_id, likes, views, size_bytes, created_at FROM videos WHERE is_deleted = 0').fetchall()
    conn.close()
    return jsonify([dict(v) for v in videos])

@app.route('/api/like/<int:video_id>', methods=['POST'])
@login_required
def api_like(video_id):
    user_id = session['user_id']
    conn = get_db_connection()
    existing = conn.execute('SELECT 1 FROM video_likes WHERE user_id = ? AND video_id = ?', (user_id, video_id)).fetchone()
    if existing:
        conn.execute('DELETE FROM video_likes WHERE user_id = ? AND video_id = ?', (user_id, video_id))
        conn.execute('UPDATE videos SET likes = likes - 1 WHERE id = ? AND likes > 0', (video_id,))
        liked = False
    else:
        conn.execute('INSERT INTO video_likes (user_id, video_id) VALUES (?, ?)', (user_id, video_id))
        conn.execute('UPDATE videos SET likes = likes + 1 WHERE id = ?', (video_id,))
        liked = True
        video = conn.execute('SELECT user_id FROM videos WHERE id = ?', (video_id,)).fetchone()
        if video and video['user_id'] != user_id:
            conn.execute('INSERT INTO notifications (user_id, type, from_user_id, video_id) VALUES (?, "like", ?, ?)', (video['user_id'], user_id, video_id))
    conn.commit()
    video = conn.execute('SELECT likes FROM videos WHERE id = ?', (video_id,)).fetchone()
    conn.close()
    return jsonify({'status': 'success', 'liked': liked, 'likes': video['likes'] if video else 0})

@app.route('/api/view/<int:video_id>', methods=['POST'])
@login_required
def api_view(video_id):
    user_id = session['user_id']
    conn = get_db_connection()
    existing = conn.execute('SELECT 1 FROM video_views WHERE user_id = ? AND video_id = ?', (user_id, video_id)).fetchone()
    if not existing:
        conn.execute('INSERT INTO video_views (user_id, video_id) VALUES (?, ?)', (user_id, video_id))
        conn.execute('UPDATE videos SET views = views + 1 WHERE id = ?', (video_id,))
        conn.commit()
    video = conn.execute('SELECT views FROM videos WHERE id = ?', (video_id,)).fetchone()
    conn.close()
    return jsonify({'status': 'success', 'views': video['views'] if video else 0})

@app.route('/api/comment/<int:video_id>', methods=['POST'])
@login_required
def api_comment(video_id):
    data = request.json
    comment_text = data.get('comment', '').strip()
    if not comment_text:
        return jsonify({'error': 'Comment cannot be empty'}), 400
    conn = get_db_connection()
    conn.execute('INSERT INTO comments (video_id, user_id, comment_text) VALUES (?, ?, ?)', (video_id, session['user_id'], comment_text))
    video = conn.execute('SELECT user_id FROM videos WHERE id = ?', (video_id,)).fetchone()
    if video and video['user_id'] != session['user_id']:
        conn.execute('INSERT INTO notifications (user_id, type, from_user_id, video_id) VALUES (?, "comment", ?, ?)', (video['user_id'], session['user_id'], video_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/comments/<int:video_id>', methods=['GET'])
def api_get_comments(video_id):
    conn = get_db_connection()
    comments = conn.execute(
        '''SELECT c.*, u.username, u.profile_pic FROM comments c 
           JOIN users u ON c.user_id = u.id
           WHERE c.video_id = ? ORDER BY c.created_at DESC''',
        (video_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(c) for c in comments])

@app.route('/api/follow/<int:target_id>', methods=['POST'])
@login_required
def api_follow(target_id):
    user_id = session['user_id']
    if user_id == target_id:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    conn = get_db_connection()
    existing = conn.execute('SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?', (user_id, target_id)).fetchone()
    if existing:
        conn.execute('DELETE FROM follows WHERE follower_id = ? AND following_id = ?', (user_id, target_id))
        following = False
    else:
        conn.execute('INSERT INTO follows (follower_id, following_id) VALUES (?, ?)', (user_id, target_id))
        following = True
        conn.execute('INSERT INTO notifications (user_id, type, from_user_id) VALUES (?, "follow", ?)', (target_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'following': following})

@app.route('/api/video/delete', methods=['POST'])
@login_required
def api_delete_videos():
    data = request.json
    sort_by = data.get('sort_by', 'new')
    amount = int(data.get('amount', 10))
    unit = data.get('unit', 'MB')
    result = delete_videos_with_options(session['user_id'], sort_by=sort_by, amount=amount, unit=unit)
    return jsonify({'status': 'success', 'deleted_count': result['deleted_count'], 'total_size_mb': result['total_size_mb'], 'total_size_gb': result['total_size_gb']})

@app.route('/api/video/delete/<int:video_id>', methods=['POST'])
@login_required
def api_delete_single_video(video_id):
    result = delete_single_video(video_id, session['user_id'])
    if result:
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Video not found'}), 404

# ==================== TEMPLATES ====================
# (မူလ Template အကုန်လုံးကို ဒီနေရာမှာ ထည့်ပါ။ သူတို့က မပြောင်းလဲပါဘူး။
# နေရာလွတ်သက်သာဖို့ အတိုချုံးထားတာ။ ခင်ဗျားရဲ့ မူလ Code ထဲက Template အကုန်လုံးကို ဒီနေရာမှာ ပြန်ထည့်ပါ။)

MAIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>P2P TikTok</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow: hidden; height: 100vh; max-width: 500px; margin: 0 auto; }
        .sort-tabs {
            position: fixed;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 30;
            display: flex;
            gap: 6px;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(10px);
            padding: 4px 8px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .sort-tabs a {
            color: rgba(255,255,255,0.5);
            text-decoration: none;
            font-size: 11px;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 14px;
            transition: all 0.2s;
            white-space: nowrap;
        }
        .sort-tabs a.active { color: #fff; background: #fe2c55; }
        .sort-tabs a:active { transform: scale(0.95); }
        .video-container { height: 100vh; overflow-y: scroll; scroll-snap-type: y mandatory; scroll-behavior: smooth; padding-top: 55px; }
        .video-container::-webkit-scrollbar { display: none; }
        .video-wrapper { height: 100vh; scroll-snap-align: start; position: relative; display: flex; justify-content: center; align-items: center; background: #000; }
        .video-wrapper video { width: 100%; height: 100%; object-fit: cover; max-width: 500px; display: block; }
        .side-bar { position: absolute; right: 12px; bottom: 100px; display: flex; flex-direction: column; align-items: center; gap: 16px; z-index: 10; }
        .action-btn { display: flex; flex-direction: column; align-items: center; color: #fff; cursor: pointer; text-shadow: 0 2px 4px rgba(0,0,0,0.5); text-decoration: none; }
        .action-btn i { font-size: 28px; margin-bottom: 4px; transition: transform 0.15s; }
        .action-btn i:active { transform: scale(0.8); }
        .action-btn span { font-size: 11px; font-weight: 600; }
        .action-btn .avatar-small { width: 44px; height: 44px; border-radius: 50%; border: 2px solid #fff; display: flex; justify-content: center; align-items: center; background: #fe2c55; font-size: 16px; font-weight: bold; margin-bottom: 4px; overflow: hidden; }
        .action-btn .avatar-small img { width: 100%; height: 100%; object-fit: cover; }
        .action-btn .heart-active { color: #fe2c55; }
        .video-info { position: absolute; bottom: 80px; left: 12px; z-index: 10; max-width: 75%; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
        .video-info h3 { font-size: 15px; font-weight: 600; margin-bottom: 4px; cursor: pointer; }
        .video-info h3:hover { text-decoration: underline; }
        .video-info p { font-size: 14px; line-height: 1.4; margin-bottom: 4px; }
        .video-info .views { font-size: 12px; color: #aaa; }
        .sound-icon { position: absolute; bottom: 120px; right: 70px; z-index: 10; background: rgba(0,0,0,0.5); border-radius: 50%; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center; cursor: pointer; border: 1px solid rgba(255,255,255,0.2); }
        .sound-icon i { font-size: 18px; }
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; max-width: 500px; height: 60px; background: rgba(0,0,0,0.9); backdrop-filter: blur(10px); border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-around; align-items: center; z-index: 20; margin: 0 auto; }
        .bottom-nav a { color: rgba(255,255,255,0.6); text-decoration: none; display: flex; flex-direction: column; align-items: center; font-size: 10px; transition: color 0.2s; }
        .bottom-nav a.active { color: #fff; }
        .bottom-nav a i { font-size: 22px; margin-bottom: 2px; }
        .bottom-nav .upload-btn { background: #fe2c55; color: #fff; padding: 4px 16px; border-radius: 30px; font-size: 16px; font-weight: 700; }
        .heart-pop { position: fixed; color: #fe2c55; font-size: 60px; z-index: 100; pointer-events: none; animation: heartPop 0.6s forwards; }
        @keyframes heartPop { 0% { transform: scale(0); opacity: 0; } 30% { transform: scale(1.3); opacity: 1; } 70% { transform: scale(1); opacity: 1; } 100% { transform: scale(0.8); opacity: 0; } }
        .badge { position: absolute; top: 10px; right: 10px; z-index: 10; background: rgba(0,0,0,0.7); padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; }
        @media (max-width: 500px) { .video-wrapper video { max-width: 100%; } }
    </style>
</head>
<body>

<div class="sort-tabs">
    <a href="/?sort=new" class="{% if current_sort == 'new' %}active{% endif %}">🔥 New</a>
    <a href="/?sort=old" class="{% if current_sort == 'old' %}active{% endif %}">📅 Old</a>
    <a href="/?sort=random" class="{% if current_sort == 'random' %}active{% endif %}">🎲 Random</a>
    <a href="/?sort=following" class="{% if current_sort == 'following' %}active{% endif %}">👥 Following</a>
    <a href="/?sort=foryou" class="{% if current_sort == 'foryou' %}active{% endif %}">⭐ For You</a>
</div>

<div class="video-container">
    {% for v in videos %}
    <div class="video-wrapper" data-id="{{ v.id }}">
        <video src="/uploads/{{ v.filename }}" loop playsinline></video>
        
        <div class="side-bar">
            <a href="/profile/{{ v.username }}" class="action-btn">
                <div class="avatar-small">
                    {% if v.profile_pic %}
                    <img src="/profile_pics/{{ v.profile_pic }}">
                    {% else %}
                    {{ v.username[0].upper() }}
                    {% endif %}
                </div>
            </a>
            <div class="action-btn" onclick="likeVideo({{ v.id }})">
                <i class="fa-solid fa-heart" id="heart-{{ v.id }}"></i>
                <span id="likes-{{ v.id }}">{{ v.likes }}</span>
            </div>
            <div class="action-btn" onclick="openComments({{ v.id }})">
                <i class="fa-solid fa-comment-dots"></i>
                <span>Comments</span>
            </div>
            <div class="action-btn" onclick="shareVideo({{ v.id }})">
                <i class="fa-solid fa-share"></i>
                <span>Share</span>
            </div>
        </div>
        
        <div class="video-info">
            <h3 onclick="location.href='/profile/{{ v.username }}'">@{{ v.username }}</h3>
            <p>{{ v.description or '' }}</p>
            <div class="views"><i class="fa-solid fa-eye"></i> {{ v.views }} views</div>
        </div>
        
        <div class="sound-icon" onclick="toggleSound({{ v.id }})">
            <i class="fa-solid fa-volume-high" id="sound-{{ v.id }}"></i>
        </div>
        
        {% if v.is_cache %}
        <div class="badge" style="background:#FF9800;">Cache</div>
        {% endif %}
    </div>
    {% else %}
    <div style="height:100vh; display:flex; justify-content:center; align-items:center; text-align:center; padding:20px; color:#666;">
        <div><i class="fa-solid fa-video-slash" style="font-size:48px; margin-bottom:15px; display:block;"></i>
            <h3>No videos yet</h3>
            <p style="margin-top:8px;">Upload one now or wait for peers</p>
            <a href="/upload" style="color:#fe2c55; text-decoration:none; margin-top:12px; display:inline-block;">Upload →</a>
        </div>
    </div>
    {% endfor %}
</div>

<div class="bottom-nav">
    <a href="/" class="active"><i class="fa-solid fa-house"></i></a>
    <a href="/inbox"><i class="fa-solid fa-message"></i></a>
    <a href="/upload" class="upload-btn">+</a>
    <a href="/chat"><i class="fa-solid fa-envelope"></i></a>
    <a href="/profile"><i class="fa-solid fa-user"></i></a>
</div>

<script>
var videoObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
        var wrapper = entry.target;
        var video = wrapper.querySelector('video');
        if (entry.isIntersecting) {
            video.play();
            document.querySelectorAll('.video-wrapper video').forEach(function(v) { if (v !== video) v.pause(); });
            if (!wrapper.dataset.viewed) {
                wrapper.dataset.viewed = 'true';
                fetch('/api/view/' + wrapper.dataset.id, { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.status === 'success') {
                        var viewsEl = wrapper.querySelector('.views');
                        if (viewsEl) {
                            viewsEl.innerHTML = '<i class="fa-solid fa-eye"></i> ' + data.views + ' views';
                        }
                    }
                });
            }
        } else {
            video.pause();
        }
    });
}, { threshold: 0.6 });
document.querySelectorAll('.video-wrapper').forEach(function(w) { videoObserver.observe(w); });

function toggleSound(id) {
    var video = document.querySelector('.video-wrapper[data-id="' + id + '"] video');
    var icon = document.getElementById('sound-' + id);
    if (video) { video.muted = !video.muted;
        if (icon) { icon.className = video.muted ? 'fa-solid fa-volume-xmark' : 'fa-solid fa-volume-high'; }
    }
}

function likeVideo(id) {
    var heart = document.getElementById('heart-' + id);
    var count = document.getElementById('likes-' + id);
    fetch('/api/like/' + id, { method: 'POST' })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.status === 'success') {
            if (data.liked) { heart.classList.add('heart-active');
                var pop = document.createElement('div');
                pop.className = 'heart-pop';
                pop.innerHTML = '❤️';
                pop.style.left = (event.clientX - 30) + 'px';
                pop.style.top = (event.clientY - 30) + 'px';
                document.body.appendChild(pop);
                setTimeout(function() { pop.remove(); }, 600);
            } else { heart.classList.remove('heart-active'); }
            count.textContent = data.likes;
        }
    });
}

function openComments(id) {
    var panel = document.getElementById('commentsPanel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'commentsPanel';
        panel.className = 'comments-panel';
        panel.innerHTML = '<div class="comments-header"><span>Comments</span><span onclick="closeComments()" style="cursor:pointer;">✕</span></div><div class="comments-list" id="commentsList"></div><div class="comments-input"><input type="text" id="commentInput" placeholder="Add a comment..."><button onclick="postComment()">Post</button></div>';
        document.body.appendChild(panel);
        var style = document.createElement('style');
        style.textContent = '.comments-panel { position: fixed; bottom: -60vh; left: 0; right: 0; height: 50vh; background: #121212; border-radius: 16px 16px 0 0; z-index: 30; transition: bottom 0.3s ease; display: flex; flex-direction: column; } .comments-panel.active { bottom: 60px; } .comments-panel .comments-header { padding: 15px; text-align: center; border-bottom: 1px solid #222; position: relative; font-weight: 600; } .comments-panel .comments-header span:last-child { position: absolute; right: 15px; top: 15px; } .comments-panel .comments-list { flex: 1; overflow-y: auto; padding: 15px; } .comments-panel .comment-item { display: flex; gap: 10px; margin-bottom: 12px; } .comments-panel .comment-item .avatar { width: 32px; height: 32px; border-radius: 50%; display: flex; justify-content: center; align-items: center; font-size: 12px; font-weight: bold; flex-shrink: 0; overflow: hidden; background: #fe2c55; } .comments-panel .comment-item .avatar img { width: 100%; height: 100%; object-fit: cover; } .comments-panel .comment-item .content { flex: 1; } .comments-panel .comment-item .content .user { font-weight: 600; font-size: 13px; } .comments-panel .comment-item .content .text { font-size: 14px; color: #ddd; } .comments-panel .comments-input { padding: 12px; border-top: 1px solid #222; display: flex; gap: 10px; } .comments-panel .comments-input input { flex: 1; padding: 10px 16px; border-radius: 20px; border: none; background: #222; color: #fff; outline: none; } .comments-panel .comments-input button { background: #fe2c55; border: none; color: #fff; padding: 0 16px; border-radius: 20px; font-weight: 600; cursor: pointer; }';
        document.head.appendChild(style);
    }
    panel.dataset.videoId = id;
    panel.classList.add('active');
    fetch('/api/comments/' + id)
    .then(function(res) { return res.json(); })
    .then(function(data) {
        var list = document.getElementById('commentsList');
        list.innerHTML = '';
        data.forEach(function(c) {
            var avatarHtml = c.profile_pic ? '<img src="/profile_pics/' + c.profile_pic + '">' : c.username[0].toUpperCase();
            list.innerHTML += '<div class="comment-item"><div class="avatar">' + avatarHtml + '</div><div class="content"><div class="user">@' + c.username + '</div><div class="text">' + c.comment_text + '</div></div></div>';
        });
    });
}

function closeComments() { document.getElementById('commentsPanel').classList.remove('active'); }

function postComment() {
    var panel = document.getElementById('commentsPanel');
    var input = document.getElementById('commentInput');
    var id = panel.dataset.videoId;
    if (!input.value.trim()) return;
    fetch('/api/comment/' + id, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ comment: input.value }) })
    .then(function(res) { return res.json(); })
    .then(function(data) { if (data.status === 'success') { input.value = ''; openComments(id); } });
}

function shareVideo(id) {
    var url = window.location.origin + '/video/' + id;
    if (navigator.share) { navigator.share({ title: 'Check this video!', url: url }); } 
    else { navigator.clipboard.writeText(url).then(function() { alert('Link copied to clipboard!'); }); }
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowUp') { document.querySelector('.video-container').scrollBy({ top: -window.innerHeight, behavior: 'smooth' }); } 
    else if (e.key === 'ArrowDown') { document.querySelector('.video-container').scrollBy({ top: window.innerHeight, behavior: 'smooth' }); }
});
</script>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; max-width: 500px; margin: 0 auto; }
        .login-box { background: #1a1a1a; padding: 35px; border-radius: 16px; width: 320px; text-align: center; }
        .login-box h2 { color: #fe2c55; margin-bottom: 10px; font-size: 24px; }
        .login-box p { color: #666; font-size: 14px; margin-bottom: 25px; }
        .login-box input { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid #333; background: #222; color: #fff; outline: none; box-sizing: border-box; margin-bottom: 12px; }
        .login-box button { background: #fe2c55; color: #fff; border: none; padding: 12px; border-radius: 30px; font-weight: 600; font-size: 16px; cursor: pointer; width: 100%; margin-bottom: 10px; }
        .login-box a { color: #666; font-size: 13px; text-decoration: none; }
        .login-box .home-link { color: #fe2c55; display: block; margin-top: 15px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2><i class="fa-brands fa-tiktok"></i> P2P TikTok</h2>
        <p>LAN Only • No Internet Required</p>
        <form action="/login" method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        <a href="/signup">Create Account →</a>
        <a href="/" class="home-link">← Home</a>
    </div>
</body>
</html>
"""

SIGNUP_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; max-width: 500px; margin: 0 auto; }
        .signup-box { background: #1a1a1a; padding: 35px; border-radius: 16px; width: 320px; text-align: center; }
        .signup-box h2 { color: #fe2c55; margin-bottom: 20px; font-size: 24px; }
        .signup-box input { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid #333; background: #222; color: #fff; outline: none; box-sizing: border-box; margin-bottom: 12px; }
        .signup-box button { background: #fe2c55; color: #fff; border: none; padding: 12px; border-radius: 30px; font-weight: 600; font-size: 16px; cursor: pointer; width: 100%; margin-bottom: 10px; }
        .signup-box a { color: #666; font-size: 13px; text-decoration: none; }
    </style>
</head>
<body>
    <div class="signup-box">
        <h2><i class="fa-brands fa-tiktok"></i> Sign Up</h2>
        <form method="POST">
            <input type="text" name="username" placeholder="Username (min 3 chars)" required>
            <input type="password" name="password" placeholder="Password (min 4 chars)" required>
            <button type="submit">Create Account</button>
        </form>
        <a href="/profile">← Back to Login</a>
    </div>
</body>
</html>
"""

UPLOAD_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Upload - P2P TikTok</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { margin: 0; background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; max-width: 500px; margin: 0 auto; }
        .upload-box { background: #1a1a1a; padding: 30px; border-radius: 16px; width: 340px; }
        .upload-box h2 { color: #fe2c55; text-align: center; margin-bottom: 10px; font-size: 22px; }
        .upload-box .sub { color: #666; text-align: center; font-size: 13px; margin-bottom: 20px; }
        .upload-box input[type="file"] { display: block; width: 100%; padding: 30px; border: 2px dashed #333; border-radius: 12px; background: transparent; color: #fff; margin-bottom: 15px; text-align: center; cursor: pointer; }
        .upload-box textarea { width: 100%; height: 80px; padding: 12px; border-radius: 12px; border: 1px solid #333; background: #222; color: #fff; outline: none; resize: none; box-sizing: border-box; margin-bottom: 15px; font-family: inherit; }
        .upload-box label { color: #888; font-size: 14px; display: flex; align-items: center; gap: 8px; margin-bottom: 15px; }
        .upload-box button { background: #fe2c55; color: #fff; border: none; padding: 12px; border-radius: 30px; font-weight: 600; font-size: 16px; cursor: pointer; width: 100%; }
        .upload-box .back { display: block; text-align: center; color: #666; text-decoration: none; margin-top: 12px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="upload-box">
        <h2><i class="fa-brands fa-tiktok"></i> Upload</h2>
        <p class="sub">Original quality • No compression</p>
        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="video" accept="video/*" required>
            <textarea name="description" placeholder="Add description..."></textarea>
            <label><input type="checkbox" name="is_private"> Private</label>
            <button type="submit">Post</button>
        </form>
        <a href="/" class="back">← Back</a>
    </div>
</body>
</html>
"""

EDIT_PROFILE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { margin: 0; background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 500px; margin: 0 auto; }
        .header { padding: 16px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #222; }
        .header .back { color: #fff; text-decoration: none; font-size: 20px; }
        .header .title { flex: 1; text-align: center; font-size: 16px; font-weight: 600; }
        .header .save { color: #fe2c55; text-decoration: none; font-weight: 600; font-size: 14px; cursor: pointer; }
        .form-group { padding: 16px 20px; border-bottom: 1px solid #222; }
        .form-group label { display: block; font-size: 12px; color: #888; margin-bottom: 4px; }
        .form-group input, .form-group textarea { width: 100%; background: transparent; border: none; color: #fff; font-size: 16px; outline: none; font-family: inherit; }
        .form-group textarea { height: 60px; resize: none; }
        .form-group .photo { display: flex; align-items: center; gap: 16px; }
        .form-group .photo .avatar { width: 60px; height: 60px; border-radius: 50%; background: #fe2c55; display: flex; justify-content: center; align-items: center; font-size: 24px; font-weight: bold; flex-shrink: 0; overflow: hidden; }
        .form-group .photo .avatar img { width: 100%; height: 100%; object-fit: cover; }
        .form-group .photo .change { color: #fe2c55; font-weight: 600; cursor: pointer; }
        .form-group .photo input[type="file"] { display: none; }
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; max-width: 500px; height: 60px; background: rgba(0,0,0,0.9); backdrop-filter: blur(10px); border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-around; align-items: center; z-index: 20; margin: 0 auto; }
        .bottom-nav a { color: rgba(255,255,255,0.6); text-decoration: none; display: flex; flex-direction: column; align-items: center; font-size: 10px; }
        .bottom-nav a.active { color: #fff; }
        .bottom-nav a i { font-size: 22px; }
        .bottom-nav .upload-btn { background: #fe2c55; color: #fff; padding: 4px 16px; border-radius: 30px; font-size: 16px; font-weight: 700; }
    </style>
</head>
<body>
    <div class="header">
        <a href="/profile" class="back"><i class="fa-solid fa-arrow-left"></i></a>
        <span class="title">Edit profile</span>
        <a href="#" class="save" onclick="saveProfile()">Save</a>
    </div>
    
    <form id="editForm" method="POST" enctype="multipart/form-data">
        <div class="form-group">
            <div class="photo">
                {% if user.profile_pic %}
                <div class="avatar"><img src="/profile_pics/{{ user.profile_pic }}"></div>
                {% else %}
                <div class="avatar">{{ user.username[0].upper() }}</div>
                {% endif %}
                <div>
                    <span class="change" onclick="document.getElementById('photoInput').click()">Change photo</span>
                    <input type="file" id="photoInput" name="profile_pic" accept="image/*">
                </div>
            </div>
        </div>
        
        <div class="form-group">
            <label>Name</label>
            <input type="text" name="name" value="{{ user.name or user.username }}">
        </div>
        
        <div class="form-group">
            <label>Username</label>
            <input type="text" name="username" value="{{ user.username }}">
        </div>
        
        <div class="form-group">
            <label>Bio</label>
            <textarea name="bio" placeholder="Tell people about yourself...">{{ user.bio or '' }}</textarea>
        </div>
    </form>
    
    <div class="bottom-nav">
        <a href="/"><i class="fa-solid fa-house"></i></a>
        <a href="/inbox"><i class="fa-solid fa-message"></i></a>
        <a href="/upload" class="upload-btn">+</a>
        <a href="/chat"><i class="fa-solid fa-envelope"></i></a>
        <a href="/profile" class="active"><i class="fa-solid fa-user"></i></a>
    </div>
    
    <script>
        function saveProfile() {
            document.getElementById('editForm').submit();
        }
    </script>
</body>
</html>
"""

INBOX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { margin: 0; background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding-bottom: 80px; max-width: 500px; margin: 0 auto; }
        .header { padding: 16px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #222; }
        .header .back { color: #fff; text-decoration: none; font-size: 20px; }
        .header .title { flex: 1; text-align: center; font-size: 16px; font-weight: 600; }
        .inbox-item { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid #111; cursor: pointer; }
        .inbox-item:hover { background: #111; }
        .inbox-item .icon { width: 40px; height: 40px; border-radius: 50%; display: flex; justify-content: center; align-items: center; font-size: 18px; flex-shrink: 0; overflow: hidden; background: #fe2c55; }
        .inbox-item .icon img { width: 100%; height: 100%; object-fit: cover; }
        .inbox-item .icon.activity { background: #fe2c55; }
        .inbox-item .icon.message { background: #1a8cd8; }
        .inbox-item .icon.notification { background: #333; }
        .inbox-item .content { flex: 1; min-width: 0; }
        .inbox-item .content .title { font-weight: 600; font-size: 14px; }
        .inbox-item .content .sub { font-size: 13px; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .inbox-item .time { font-size: 11px; color: #666; flex-shrink: 0; }
        .inbox-item .badge { background: #fe2c55; color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; flex-shrink: 0; }
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; max-width: 500px; height: 60px; background: rgba(0,0,0,0.9); backdrop-filter: blur(10px); border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-around; align-items: center; z-index: 20; margin: 0 auto; }
        .bottom-nav a { color: rgba(255,255,255,0.6); text-decoration: none; display: flex; flex-direction: column; align-items: center; font-size: 10px; }
        .bottom-nav a.active { color: #fff; }
        .bottom-nav a i { font-size: 22px; }
        .bottom-nav .upload-btn { background: #fe2c55; color: #fff; padding: 4px 16px; border-radius: 30px; font-size: 16px; font-weight: 700; }
        .section-title { padding: 12px 16px; font-size: 13px; color: #888; font-weight: 600; background: #0a0a0a; }
    </style>
</head>
<body>
    <div class="header">
        <a href="/" class="back"><i class="fa-solid fa-arrow-left"></i></a>
        <span class="title">Inbox</span>
    </div>
    
    {% if unread > 0 %}
    <div style="padding:8px 16px; background:#1a1a1a; font-size:13px; color:#888;">
        <i class="fa-solid fa-circle" style="color:#fe2c55; font-size:8px;"></i> {{ unread }} unread messages
    </div>
    {% endif %}
    
    <div class="section-title">Activity & Notifications</div>
    {% for n in notifications %}
    <div class="inbox-item" onclick="location.href='/profile/{{ n.username }}'">
        <div class="icon activity">
            {% if n.profile_pic %}
            <img src="/profile_pics/{{ n.profile_pic }}">
            {% else %}
            <i class="fa-solid fa-user-plus"></i>
            {% endif %}
        </div>
        <div class="content">
            <div class="title">@{{ n.username }}</div>
            <div class="sub">{{ n.type }} your content</div>
        </div>
        <div class="time">{{ n.created_at[:16] }}</div>
    </div>
    {% else %}
    <div style="padding:20px; text-align:center; color:#666;">
        <i class="fa-solid fa-bell-slash" style="font-size:32px; display:block; margin-bottom:10px;"></i>
        No notifications yet
    </div>
    {% endfor %}
    
    <div class="section-title">Messages</div>
    {% for m in messages %}
    <div class="inbox-item" onclick="location.href='/chat/{{ m.sender_id }}'">
        <div class="icon message">
            {% if m.profile_pic %}
            <img src="/profile_pics/{{ m.profile_pic }}">
            {% else %}
            <i class="fa-solid fa-user"></i>
            {% endif %}
        </div>
        <div class="content">
            <div class="title">@{{ m.username }}</div>
            <div class="sub">{{ m.message_text[:50] }}</div>
        </div>
        <div class="time">{{ m.created_at[:16] }}</div>
    </div>
    {% else %}
    <div style="padding:20px; text-align:center; color:#666;">
        <i class="fa-solid fa-inbox" style="font-size:32px; display:block; margin-bottom:10px;"></i>
        No messages yet
    </div>
    {% endfor %}
    
    <div class="bottom-nav">
        <a href="/"><i class="fa-solid fa-house"></i></a>
        <a href="/inbox" class="active"><i class="fa-solid fa-message"></i></a>
        <a href="/upload" class="upload-btn">+</a>
        <a href="/chat"><i class="fa-solid fa-envelope"></i></a>
        <a href="/profile"><i class="fa-solid fa-user"></i></a>
    </div>
</body>
</html>
"""

PROFILE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { margin: 0; background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding-bottom: 80px; max-width: 500px; margin: 0 auto; }
        .header { padding: 12px 16px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #222; }
        .header .back { color: #fff; text-decoration: none; font-size: 20px; }
        .header .title { flex: 1; text-align: center; font-size: 16px; font-weight: 600; }
        .header .edit { color: #fe2c55; text-decoration: none; font-size: 14px; font-weight: 600; }
        .profile-info { text-align: center; padding: 20px; }
        .profile-info .avatar { width: 88px; height: 88px; border-radius: 50%; background: #fe2c55; display: inline-flex; justify-content: center; align-items: center; font-size: 36px; font-weight: bold; border: 2px solid #fe2c55; overflow: hidden; }
        .profile-info .avatar img { width: 100%; height: 100%; object-fit: cover; }
        .profile-info .name { font-size: 20px; font-weight: bold; margin-top: 10px; }
        .profile-info .username { font-size: 14px; color: #888; }
        .profile-info .bio { font-size: 14px; color: #aaa; margin-top: 8px; max-width: 400px; margin-left: auto; margin-right: auto; }
        .profile-stats { display: flex; justify-content: center; gap: 30px; padding: 12px; }
        .profile-stats .stat { text-align: center; cursor: pointer; }
        .profile-stats .stat .num { font-size: 18px; font-weight: bold; display: block; }
        .profile-stats .stat .label { font-size: 12px; color: #888; }
        .profile-actions { display: flex; gap: 10px; justify-content: center; padding: 10px; flex-wrap: wrap; }
        .profile-actions button, .profile-actions a { padding: 8px 24px; border-radius: 6px; border: none; font-weight: 600; font-size: 14px; cursor: pointer; text-decoration: none; }
        .btn-follow { background: #fe2c55; color: #fff; }
        .btn-follow.following { background: #333; }
        .btn-chat { background: #333; color: #fff; }
        .btn-edit { background: #333; color: #fff; }
        .btn-logout { background: #222; color: #888; }
        .btn-share { background: #333; color: #fff; }
        .btn-delete { background: #fe2c55; color: #fff; }
        .video-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; padding: 0 2px; margin-top: 10px; }
        .video-item { aspect-ratio: 9/14; background: #1a1a1a; position: relative; overflow: hidden; }
        .video-item video { width: 100%; height: 100%; object-fit: cover; }
        .video-item .overlay { position: absolute; bottom: 0; left: 0; right: 0; padding: 8px; background: linear-gradient(transparent, rgba(0,0,0,0.7)); display: flex; justify-content: space-between; font-size: 11px; }
        .video-item .overlay span { display: flex; align-items: center; gap: 4px; }
        .video-item .delete-single { position: absolute; top: 6px; left: 6px; background: rgba(254,44,85,0.8); color: #fff; border: none; border-radius: 50%; width: 24px; height: 24px; font-size: 12px; cursor: pointer; display: none; }
        .video-item:hover .delete-single { display: block; }
        .storage-card { background: #1a1a1a; margin: 12px; padding: 12px; border-radius: 12px; }
        .storage-card .title { font-size: 13px; color: #888; margin-bottom: 6px; }
        .storage-card .bar { width: 100%; height: 6px; background: #333; border-radius: 3px; overflow: hidden; }
        .storage-card .bar .fill { height: 100%; background: linear-gradient(90deg, #fe2c55, #ff6b8a); border-radius: 3px; }
        .storage-card .info { display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px; color: #aaa; }
        .section-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; }
        .section-header .delete-all { background: #fe2c55; color: #fff; border: none; padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; }
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; max-width: 500px; height: 60px; background: rgba(0,0,0,0.9); backdrop-filter: blur(10px); border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-around; align-items: center; z-index: 20; margin: 0 auto; }
        .bottom-nav a { color: rgba(255,255,255,0.6); text-decoration: none; display: flex; flex-direction: column; align-items: center; font-size: 10px; }
        .bottom-nav a.active { color: #fff; }
        .bottom-nav a i { font-size: 22px; }
        .bottom-nav .upload-btn { background: #fe2c55; color: #fff; padding: 4px 16px; border-radius: 30px; font-size: 16px; font-weight: 700; }
        .empty { text-align: center; padding: 50px; color: #666; grid-column: 1/-1; }
        .empty i { font-size: 40px; margin-bottom: 10px; display: block; }
        .empty a { color: #fe2c55; text-decoration: none; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 999; justify-content: center; align-items: center; }
        .modal.active { display: flex; }
        .modal-content { background: #1a1a1a; border-radius: 16px; width: 90%; max-width: 400px; padding: 24px; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; font-size: 18px; font-weight: 600; margin-bottom: 20px; }
        .modal-close { font-size: 24px; cursor: pointer; color: #888; }
        .modal-body label { display: block; color: #888; font-size: 13px; margin: 12px 0 6px 0; }
        .modal-body select, .modal-body input { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #222; color: #fff; box-sizing: border-box; }
        .modal-body .row { display: flex; gap: 10px; }
        .modal-body .row * { flex: 1; }
        .modal-footer { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
        .modal-footer button { padding: 10px 24px; border-radius: 8px; border: none; font-weight: 600; cursor: pointer; }
        .btn-cancel { background: #333; color: #fff; }
        .btn-delete-confirm { background: #fe2c55; color: #fff; }
    </style>
</head>
<body>

<div class="header">
    <a href="/" class="back"><i class="fa-solid fa-arrow-left"></i></a>
    <span class="title">{% if is_own %}Profile{% else %}@{{ user.username }}{% endif %}</span>
    {% if is_own %}
    <a href="/profile/edit" class="edit">Edit</a>
    {% endif %}
</div>

<div class="profile-info">
    <div class="avatar">
        {% if user.profile_pic %}
        <img src="/profile_pics/{{ user.profile_pic }}">
        {% else %}
        {{ user.username[0].upper() }}
        {% endif %}
    </div>
    <div class="name">{{ user.name or user.username }}</div>
    <div class="username">@{{ user.username }}</div>
    <div class="bio">{{ user.bio or '' }}</div>
</div>

<div class="profile-stats">
    <div class="stat"><span class="num">{{ following }}</span><span class="label">Following</span></div>
    <div class="stat"><span class="num">{{ followers }}</span><span class="label">Followers</span></div>
    <div class="stat"><span class="num">{{ total_likes }}</span><span class="label">Likes</span></div>
    <div class="stat"><span class="num">{{ total_views }}</span><span class="label">Views</span></div>
</div>

<div class="profile-actions">
    {% if not is_own %}
    <button class="btn-follow {% if is_following %}following{% endif %}" onclick="toggleFollow({{ user.id }})">
        {% if is_following %}Following{% else %}Follow{% endif %}
    </button>
    <a href="/chat/{{ user.id }}" class="btn-chat">Chat</a>
    <button class="btn-share" onclick="shareProfile('{{ user.username }}')"><i class="fa-solid fa-share"></i></button>
    {% else %}
    <button class="btn-logout" onclick="location.href='/logout'">Log Out</button>
    <button class="btn-edit" onclick="location.href='/profile/edit'">Edit Profile</button>
    <button class="btn-share" onclick="shareProfile('{{ user.username }}')"><i class="fa-solid fa-share"></i></button>
    {% endif %}
</div>

<div class="storage-card">
    <div class="title"><i class="fa-solid fa-hdd"></i> Storage</div>
    <div class="bar"><div class="fill" style="width: {{ storage.percent }}%"></div></div>
    <div class="info"><span>Used: {{ storage.used_gb }} GB</span><span>Free: {{ storage.free_gb }} GB</span></div>
</div>

<div class="section-header">
    <span style="font-weight:600;">Videos ({{ videos|length }})</span>
    {% if is_own and videos|length > 0 %}
    <button class="delete-all" onclick="openDeleteModal()"><i class="fa-solid fa-trash-can"></i> Delete</button>
    {% endif %}
</div>

<div class="video-grid">
    {% for v in videos %}
    <div class="video-item">
        <video src="/uploads/{{ v.filename }}" muted></video>
        <div class="overlay">
            <span><i class="fa-solid fa-play"></i> {{ v.views or 0 }}</span>
            <span><i class="fa-solid fa-heart"></i> {{ v.likes }}</span>
        </div>
        {% if v.is_cache %}
        <span style="position:absolute; top:6px; right:6px; font-size:9px; background:rgba(0,0,0,0.7); padding:2px 8px; border-radius:10px; color:#FF9800;">Cache</span>
        {% endif %}
        {% if is_own %}
        <button class="delete-single" onclick="deleteSingleVideo({{ v.id }})"><i class="fa-solid fa-xmark"></i></button>
        {% endif %}
    </div>
    {% else %}
    <div class="empty">
        <i class="fa-solid fa-video-slash"></i>
        <p>No videos yet</p>
        <a href="/upload">Upload now →</a>
    </div>
    {% endfor %}
</div>

<!-- Delete Modal -->
<div class="modal" id="deleteModal">
    <div class="modal-content">
        <div class="modal-header">
            <span>🗑️ Delete Videos</span>
            <span class="modal-close" onclick="closeDeleteModal()">&times;</span>
        </div>
        <div class="modal-body">
            <label>Sort By</label>
            <select id="deleteSort">
                <option value="new">Newest First</option>
                <option value="old">Oldest First</option>
            </select>
            <label>Amount</label>
            <div class="row">
                <input type="number" id="deleteAmount" value="10" min="1">
                <select id="deleteUnit">
                    <option value="MB">MB</option>
                    <option value="GB">GB</option>
                </select>
            </div>
            <div style="margin-top:15px;padding:12px;background:#222;border-radius:8px;font-size:12px;color:#888;">
                ⚠️ Videos will be deleted starting from the selected sort order until the specified amount is reached.
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn-cancel" onclick="closeDeleteModal()">Cancel</button>
            <button class="btn-delete-confirm" onclick="confirmDelete()">Delete</button>
        </div>
    </div>
</div>

<div class="bottom-nav">
    <a href="/"><i class="fa-solid fa-house"></i></a>
    <a href="/inbox"><i class="fa-solid fa-message"></i></a>
    <a href="/upload" class="upload-btn">+</a>
    <a href="/chat"><i class="fa-solid fa-envelope"></i></a>
    <a href="/profile" class="active"><i class="fa-solid fa-user"></i></a>
</div>

<script>
function toggleFollow(id) {
    fetch('/api/follow/' + id, { method: 'POST' })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.status === 'success') {
            var btn = document.querySelector('.btn-follow');
            if (btn) {
                btn.textContent = data.following ? 'Following' : 'Follow';
                btn.classList.toggle('following', data.following);
            }
        }
    });
}

function shareProfile(username) {
    var url = window.location.origin + '/profile/' + username;
    if (navigator.share) {
        navigator.share({ title: 'Check out @' + username + ' on P2P TikTok!', url: url });
    } else {
        navigator.clipboard.writeText(url).then(function() { alert('Profile link copied to clipboard!'); });
    }
}

function deleteSingleVideo(id) {
    if (confirm('Delete this video?')) {
        fetch('/api/video/delete/' + id, { method: 'POST' })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.status === 'success') { location.reload(); }
        });
    }
}

function openDeleteModal() { document.getElementById('deleteModal').classList.add('active'); }
function closeDeleteModal() { document.getElementById('deleteModal').classList.remove('active'); }

function confirmDelete() {
    var sort_by = document.getElementById('deleteSort').value;
    var amount = document.getElementById('deleteAmount').value;
    var unit = document.getElementById('deleteUnit').value;
    fetch('/api/video/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sort_by: sort_by, amount: parseInt(amount), unit: unit })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.status === 'success') {
            alert('Deleted ' + data.deleted_count + ' videos (' + data.total_size_mb + ' MB)');
            location.reload();
        }
    });
}
</script>

</body>
</html>
"""

# ==================== CHAT_TEMPLATE v22 (ULTIMATE LAYOUT FIX) ====================
CHAT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* ===== CSS VARIABLES ===== */
        :root {
            --bg-primary: #000000;
            --bg-secondary: #111111;
            --bg-header: #111111;
            --bg-input: #222222;
            --bg-input-focus: #2a2a2a;
            --bg-bubble-me: #fe2c55;
            --bg-bubble-other: #292929;
            --text-primary: #ffffff;
            --text-secondary: #888888;
            --text-input: #ffffff;
            --border-color: #222222;
            --accent-color: #fe2c55;
            --shadow-color: rgba(0,0,0,0.5);
            --nav-bg: rgba(0,0,0,0.9);
        }

        .light-mode {
            --bg-primary: #f0f0f0;
            --bg-secondary: #ffffff;
            --bg-header: #ffffff;
            --bg-input: #e8e8e8;
            --bg-input-focus: #dcdcdc;
            --bg-bubble-me: #fe2c55;
            --bg-bubble-other: #e0e0e0;
            --text-primary: #000000;
            --text-secondary: #666666;
            --text-input: #000000;
            --border-color: #dddddd;
            --accent-color: #fe2c55;
            --shadow-color: rgba(0,0,0,0.1);
            --nav-bg: rgba(255,255,255,0.9);
        }

        /* ===== RESET ===== */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body {
            margin: 0;
            padding: 0;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            height: 100%;
            max-width: 500px;
            margin: 0 auto;
            overflow: hidden;
            transition: background 0.3s, color 0.3s;
        }

        /* ===== CHAT CONTAINER - FLEX COLUMN ===== */
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            height: 100dvh;
            max-width: 500px;
            margin: 0 auto;
            background: var(--bg-primary);
            position: relative;
            transition: background 0.3s;
        }

        /* ===== HEADER - အပေါ်ဆုံး ===== */
        .header {
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
            border-bottom: 1px solid var(--border-color);
            background: var(--bg-header);
            flex-shrink: 0;
            min-height: 60px;
            z-index: 5;
            transition: background 0.3s, border-color 0.3s;
        }
        .header .back { color: var(--text-primary); text-decoration: none; font-size: 20px; }
        .header .info { flex: 1; display: flex; align-items: center; gap: 10px; }
        .header .info .avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            overflow: hidden;
            background: #fe2c55;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 14px;
            font-weight: bold;
            flex-shrink: 0;
        }
        .header .info .avatar img { width: 100%; height: 100%; object-fit: cover; }
        .header .info .name-status .name { font-weight: 600; font-size: 16px; }
        .header .info .name-status .status { font-size: 12px; color: #4CAF50; }
        
        .theme-toggle {
            background: none;
            border: none;
            color: var(--text-primary);
            font-size: 22px;
            cursor: pointer;
            padding: 4px 8px;
            border-radius: 50%;
            transition: background 0.2s;
        }
        .theme-toggle:hover {
            background: rgba(255,255,255,0.1);
        }
        .light-mode .theme-toggle:hover {
            background: rgba(0,0,0,0.1);
        }

        /* ===== MESSAGES AREA - အလယ် (flex: 1) ===== */
        .msg-area {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: 15px 15px 10px 15px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            background: var(--bg-primary);
            transition: background 0.3s;
        }
        .msg-area::-webkit-scrollbar { width: 3px; }
        .msg-area::-webkit-scrollbar-track { background: transparent; }
        .msg-area::-webkit-scrollbar-thumb { background: #333; border-radius: 10px; }
        .light-mode .msg-area::-webkit-scrollbar-thumb { background: #ccc; }

        /* ===== MESSAGES ===== */
        .msg {
            max-width: 85%;
            display: flex;
            align-items: flex-start;
            gap: 8px;
            position: relative;
        }
        .msg .msg-avatar {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            overflow: hidden;
            background: #fe2c55;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 12px;
            font-weight: bold;
            flex-shrink: 0;
        }
        .msg .msg-avatar img { width: 100%; height: 100%; object-fit: cover; }
        .msg .msg-content .bubble {
            padding: 8px 14px;
            border-radius: 16px;
            word-wrap: break-word;
            display: inline-block;
            position: relative;
            transition: background 0.3s;
        }
        .msg.my {
            align-self: flex-end;
            flex-direction: row-reverse;
        }
        .msg.my .msg-content .bubble {
            background: var(--bg-bubble-me);
            border-bottom-right-radius: 4px;
            color: #fff;
        }
        .msg.other {
            align-self: flex-start;
        }
        .msg.other .msg-content .bubble {
            background: var(--bg-bubble-other);
            border-bottom-left-radius: 4px;
            color: var(--text-primary);
        }
        .msg .time {
            font-size: 10px;
            opacity: 0.5;
            margin-top: 2px;
            text-align: right;
        }
        .msg .delete-btn {
            position: absolute;
            top: -8px;
            right: -8px;
            background: rgba(255,0,0,0.8);
            color: #fff;
            border: none;
            border-radius: 50%;
            width: 22px;
            height: 22px;
            font-size: 10px;
            cursor: pointer;
            display: none;
            z-index: 5;
        }
        .msg:hover .delete-btn { display: block; }
        .msg.my .delete-btn { right: auto; left: -8px; }
        
        .typing-indicator {
            color: var(--text-secondary);
            font-size: 13px;
            padding: 4px 0;
            display: none;
        }

        /* ===== ✅ INPUT AREA - Nav ရဲ့အပေါ် (flex-shrink: 0) ===== */
        .input-area {
            padding: 10px 12px;
            border-top: 2px solid var(--accent-color);
            display: flex !important;
            gap: 10px;
            background: var(--bg-secondary);
            flex-shrink: 0;
            min-height: 64px;
            align-items: center;
            transition: background 0.3s, border-color 0.3s;
            position: relative;
            z-index: 10;
        }
        .input-area input {
            flex: 1;
            padding: 12px 18px;
            border-radius: 25px;
            border: 2px solid var(--border-color);
            background: var(--bg-input);
            color: var(--text-input) !important;
            outline: none;
            font-size: 16px;
            min-height: 44px;
            transition: background 0.3s, border-color 0.3s, color 0.3s;
            caret-color: var(--accent-color);
        }
        .input-area input::placeholder { 
            color: var(--text-secondary); 
            opacity: 0.7;
        }
        .input-area input:focus {
            border-color: var(--accent-color);
            background: var(--bg-input-focus);
        }
        .input-area button {
            background: var(--accent-color);
            color: #fff;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-weight: 700;
            cursor: pointer;
            font-size: 15px;
            flex-shrink: 0;
            min-height: 44px;
            transition: transform 0.1s, background 0.3s;
        }
        .input-area button:active { transform: scale(0.95); }
        .input-area button i { margin-right: 4px; }

        /* ===== ✅ BOTTOM NAV - အောက်ဆုံး (flex-shrink: 0) ===== */
        .bottom-nav {
            flex-shrink: 0;
            height: 60px;
            background: var(--nav-bg);
            backdrop-filter: blur(10px);
            border-top: 1px solid rgba(255,255,255,0.1);
            display: flex;
            justify-content: space-around;
            align-items: center;
            position: relative;
            z-index: 5;
            transition: background 0.3s;
        }
        .bottom-nav a {
            color: rgba(255,255,255,0.6);
            text-decoration: none;
            display: flex;
            flex-direction: column;
            align-items: center;
            font-size: 10px;
            transition: color 0.2s;
        }
        .bottom-nav a.active { color: #fff; }
        .bottom-nav a i { font-size: 22px; }
        .bottom-nav .upload-btn {
            background: #fe2c55;
            color: #fff;
            padding: 4px 16px;
            border-radius: 30px;
            font-size: 16px;
            font-weight: 700;
        }
        .light-mode .bottom-nav {
            border-top: 1px solid rgba(0,0,0,0.1);
        }
        .light-mode .bottom-nav a { color: rgba(0,0,0,0.6); }
        .light-mode .bottom-nav a.active { color: #000; }

        /* ===== CHAT LIST VIEW ===== */
        .chat-list-view {
            display: flex;
            flex-direction: column;
            height: 100vh;
            height: 100dvh;
            max-width: 500px;
            margin: 0 auto;
            background: var(--bg-primary);
            overflow: hidden;
            transition: background 0.3s;
        }
        .chat-list-view .chat-list { flex: 1; overflow-y: auto; padding: 10px; }
        .chat-list-view .chat-list::-webkit-scrollbar { width: 3px; }
        .chat-list-view .chat-list::-webkit-scrollbar-thumb { background: #333; border-radius: 10px; }
        .light-mode .chat-list-view .chat-list::-webkit-scrollbar-thumb { background: #ccc; }
        
        .chat-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 12px;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .chat-item:hover { background: var(--bg-secondary); }
        .chat-item .avatar {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 16px;
            font-weight: bold;
            flex-shrink: 0;
            overflow: hidden;
            background: #fe2c55;
        }
        .chat-item .avatar img { width: 100%; height: 100%; object-fit: cover; }
        .chat-item .info { flex: 1; min-width: 0; }
        .chat-item .info .name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
        .chat-item .info .last { font-size: 13px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .chat-item .info .unread { background: #fe2c55; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 8px; color: #fff; }
        .chat-item .time { font-size: 11px; color: var(--text-secondary); flex-shrink: 0; }
        
        .suggestions {
            padding: 10px 16px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            flex-shrink: 0;
            transition: background 0.3s, border-color 0.3s;
        }
        .suggestions .title { font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; }
        .suggestions .items { display: flex; gap: 10px; overflow-x: auto; }
        .suggestions .items .item {
            display: flex;
            flex-direction: column;
            align-items: center;
            cursor: pointer;
            min-width: 60px;
        }
        .suggestions .items .item .avatar {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            background: #fe2c55;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 14px;
            font-weight: bold;
            overflow: hidden;
        }
        .suggestions .items .item .avatar img { width: 100%; height: 100%; object-fit: cover; }
        .suggestions .items .item .name { font-size: 11px; color: var(--text-secondary); margin-top: 4px; text-align: center; }
        
        .empty-chat { text-align: center; padding: 40px; color: var(--text-secondary); }
        .empty-chat i { font-size: 40px; display: block; margin-bottom: 10px; }
        
        .deleted-msg { color: var(--text-secondary); font-style: italic; font-size: 12px; padding: 4px 8px; }
    </style>
</head>
<body>

{% if active_chat_user %}
<!-- ===== CHAT VIEW ===== -->
<div class="chat-container" id="chatContainer">
    
    <!-- ၁. HEADER - အပေါ်ဆုံး -->
    <div class="header">
        <a href="/chat" class="back"><i class="fa-solid fa-arrow-left"></i></a>
        <div class="info">
            <div class="avatar">
                {% if active_chat_user.profile_pic %}
                <img src="/profile_pics/{{ active_chat_user.profile_pic }}">
                {% else %}
                {{ active_chat_user.username[0].upper() }}
                {% endif %}
            </div>
            <div class="name-status">
                <div class="name">@{{ active_chat_user.username }}</div>
                <div class="status"><i class="fa-solid fa-circle" style="font-size:8px;"></i> Active now</div>
            </div>
        </div>
        <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">
            <i class="fa-solid fa-moon"></i>
        </button>
    </div>
    
    <!-- ၂. MESSAGES - အလယ် (flex: 1) -->
    <div class="msg-area" id="msgArea">
        {% for m in chat_messages %}
        <div class="msg {% if m.sender_id == my_id %}my{% else %}other{% endif %}" data-msgid="{{ m.id }}">
            <div class="msg-avatar">
                {% if m.profile_pic %}
                <img src="/profile_pics/{{ m.profile_pic }}">
                {% else %}
                {{ m.username[0].upper() }}
                {% endif %}
            </div>
            <div class="msg-content">
                <div class="bubble">{{ m.message_text }}</div>
                <div class="time">
                    {{ m.created_at[:16] }}
                    {% if m.sender_id == my_id and m.is_seen %}
                    <span style="color:#4CAF50; font-size:10px;"><i class="fa-solid fa-check-double"></i></span>
                    {% elif m.sender_id == my_id %}
                    <span style="font-size:10px;"><i class="fa-solid fa-check"></i></span>
                    {% endif %}
                </div>
            </div>
            <button class="delete-btn" onclick="deleteMessage({{ m.id }})">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        </div>
        {% endfor %}
        <div id="typingIndicator" class="typing-indicator">Someone is typing...</div>
    </div>
    
    <!-- ၃. INPUT FIELD - Nav ရဲ့အပေါ် (flex-shrink: 0) -->
    <form method="POST" class="input-area" id="chatForm">
        <input type="text" name="message" placeholder="Type a message..." required id="msgInput" autocomplete="off">
        <button type="submit"><i class="fa-solid fa-paper-plane"></i> Send</button>
    </form>
    
    <!-- ၄. BOTTOM NAV - အောက်ဆုံး (flex-shrink: 0) -->
    <div class="bottom-nav">
        <a href="/"><i class="fa-solid fa-house"></i></a>
        <a href="/inbox"><i class="fa-solid fa-message"></i></a>
        <a href="/upload" class="upload-btn">+</a>
        <a href="/chat" class="active"><i class="fa-solid fa-envelope"></i></a>
        <a href="/profile"><i class="fa-solid fa-user"></i></a>
    </div>
    
</div>

<script>
// ===== AUTO SCROLL TO BOTTOM =====
var msgArea = document.getElementById('msgArea');
function scrollToBottom() {
    msgArea.scrollTop = msgArea.scrollHeight;
}
scrollToBottom();

// ===== AUTO FOCUS INPUT =====
var msgInput = document.getElementById('msgInput');
msgInput.focus();

// ===== TYPING INDICATOR =====
var typingTimeout;
msgInput.addEventListener('input', function() {
    var indicator = document.getElementById('typingIndicator');
    indicator.style.display = 'block';
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(function() {
        indicator.style.display = 'none';
    }, 2000);
});

// ===== DELETE MESSAGE with CONFIRMATION =====
function deleteMessage(msgId) {
    if (confirm('Delete this message for everyone?')) {
        fetch('/api/message/delete/' + msgId, { method: 'POST' })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.status === 'success') {
                var msgEl = document.querySelector('.msg[data-msgid="' + msgId + '"]');
                if (msgEl) {
                    msgEl.style.display = 'none';
                }
            } else {
                alert('Failed to delete message');
            }
        });
    }
}

// ===== DARK/LIGHT MODE TOGGLE =====
function toggleTheme() {
    var body = document.body;
    var btn = document.getElementById('themeBtn');
    var isLight = body.classList.contains('light-mode');
    
    if (isLight) {
        body.classList.remove('light-mode');
        btn.innerHTML = '<i class="fa-solid fa-moon"></i>';
        fetch('/api/theme', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: 'dark' })
        });
    } else {
        body.classList.add('light-mode');
        btn.innerHTML = '<i class="fa-solid fa-sun"></i>';
        fetch('/api/theme', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: 'light' })
        });
    }
}

// ===== RESTORE THEME FROM SERVER =====
fetch('/api/user/theme')
.then(function(res) { return res.json(); })
.then(function(data) {
    if (data.theme === 'light') {
        document.body.classList.add('light-mode');
        document.getElementById('themeBtn').innerHTML = '<i class="fa-solid fa-sun"></i>';
    }
});

// ===== SCROLL ON NEW MESSAGE =====
setInterval(function() {
    scrollToBottom();
}, 1000);
</script>

{% else %}
<!-- ===== CHAT LIST VIEW ===== -->
<div class="chat-list-view">
    
    <div class="header">
        <a href="/" class="back"><i class="fa-solid fa-arrow-left"></i></a>
        <div class="info"><div class="name-status"><div class="name">Messages</div></div></div>
    </div>
    
    <div class="suggestions">
        <div class="title">Suggested</div>
        <div class="items">
            {% for s in suggestions %}
            <div class="item" onclick="location.href='/chat/{{ s.id }}'">
                <div class="avatar">
                    {% if s.profile_pic %}
                    <img src="/profile_pics/{{ s.profile_pic }}">
                    {% else %}
                    {{ s.username[0].upper() }}
                    {% endif %}
                </div>
                <div class="name">@{{ s.username }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="chat-list">
        {% for c in chat_list %}
        <div class="chat-item" onclick="location.href='/chat/{{ c.id }}'">
            <div class="avatar">
                {% if c.profile_pic %}
                <img src="/profile_pics/{{ c.profile_pic }}">
                {% else %}
                {{ c.username[0].upper() }}
                {% endif %}
            </div>
            <div class="info">
                <div class="name">
                    @{{ c.username }}
                    {% if c.unread > 0 %}
                    <span class="unread">{{ c.unread }}</span>
                    {% endif %}
                </div>
                <div class="last">{{ c.last_message or 'No messages yet' }}</div>
            </div>
            <div class="time">{{ c.last_time[:16] if c.last_time else '' }}</div>
        </div>
        {% else %}
        <div class="empty-chat">
            <i class="fa-solid fa-comment-slash"></i>
            <p>No conversations yet</p>
            <p style="font-size:13px; margin-top:4px;">Follow people or start chatting!</p>
        </div>
        {% endfor %}
    </div>
    
</div>
{% endif %}

</body>
</html>
"""

# ==================== RUN ====================
def main():
    """Android app ရဲ့ MainActivity (Kotlin) က Chaquopy ကနေ ဒီ function ကို
    background thread ထဲမှာ ခေါ်သုံးမှာဖြစ်ပါတယ်။ PC ပေါ်မှာ တိုက်ရိုက် run
    ချင်ရင်လည်း အောက်က __main__ block ကနေ ဒီ function ကိုပဲ ခေါ်ပါတယ်။"""
    # ၁။ Script ထဲက Database ကို ပြန်ဖော်ထုတ် (Restore) — PC/portable mode မှာသာ
    restore_db_from_script()

    # ၂။ Database Table တွေ ရှိမရှိ စစ်ဆေးပြီး မရှိရင် ဖန်တီး
    init_db()

    # ၃။ P2P Threads တွေ စတင် (တခြား ဖုန်း/PC တွေနဲ့ LAN ပေါ်က ချိတ်ဆက်ဖို့)
    # Android ပေါ်မှာ socket errors ကြောင့် crash မဖြစ်အောင် try/except ထည့်ထားတယ်
    try:
        threading.Thread(target=broadcast_presence, daemon=True).start()
    except Exception as e:
        logger.warning(f"broadcast_presence thread failed to start: {e}")
    try:
        threading.Thread(target=listen_for_peers, daemon=True).start()
    except Exception as e:
        logger.warning(f"listen_for_peers thread failed to start: {e}")
    try:
        threading.Thread(target=auto_sync, daemon=True).start()
    except Exception as e:
        logger.warning(f"auto_sync thread failed to start: {e}")

    # ၄။ App ပိတ်တဲ့အခါ Database ကို Script ထဲကို ပြန်ရေးသွင်းဖို့ Register (PC/portable mode မှာသာ)
    atexit.register(embed_db_into_script)

    global local_ip
    local_ip = get_local_ip()

    logger.info("=" * 60)
    logger.info(" P2P OFFLINE TIKTOK - running inside mobile app")
    logger.info(f" Local:   http://127.0.0.1:5000")
    logger.info(f" Network: http://{local_ip}:5000")
    logger.info(f" Device:  {device_id}")
    logger.info(f" Data:    {APP_DATA_DIR}")
    logger.info("=" * 60)

    # WebView က localhost ကနေပဲ ဝင်ကြည့်မှာမို့ 127.0.0.1 ကိုပဲ bind လုပ်ရင်လည်းရတယ်
    # ဒါပေမယ့် LAN peer sync အတွက် 0.0.0.0 ကိုပဲ ဆက်ထားတယ်
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()