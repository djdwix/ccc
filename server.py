import os
import json
import time
import hashlib
import random
import asyncio
import aiohttp
import ssl
import signal
from aiohttp import web
from aiohttp_cors import setup as setup_cors, ResourceOptions
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import shutil
import socket
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import jwt

HTTP_PORT = 8084
HTTPS_PORT = 8449
API_BASE = 'http://sdk.gaz.tw:96/iapi'
SECRET_KEY = 'd7a3f4c6e5b81290de4f3c2a1b0987654321fedcba0987654321abcdef567890'
SESSION_EXPIRY = 15 * 60 * 1000
MAX_LOG_ENTRIES = 1000
CDK_COOLDOWN_MINUTES = 6

# 加密相关
ENCRYPTION_KEY_FILE = Path(__file__).parent / 'data' / 'encryption_key.key'
JWT_SECRET_KEY = 'd7a3f4c6e5b81290de4f3c2a1b0987654321fedcba0987654321abcdef567890'
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION = 15 * 60  # 15分钟

# 确保数据目录存在
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)

# 生成或加载加密密钥
def get_encryption_key():
    if ENCRYPTION_KEY_FILE.exists():
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, 'wb') as f:
            f.write(key)
        return key

ENCRYPTION_KEY = get_encryption_key()
FERNET = Fernet(ENCRYPTION_KEY)

# 生成 JWT 令牌
def generate_jwt_token(account, token, username):
    payload = {
        'account': account,
        'token': token,
        'username': username,
        'authCode': generate_auth_code(),
        'authCodeUsed': False,
        'iat': int(time.time()),
        'exp': int(time.time()) + JWT_EXPIRATION
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

# 验证 JWT 令牌
def verify_jwt_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# 加密函数
def encrypt_data(data):
    if isinstance(data, str):
        data = data.encode()
    elif isinstance(data, dict) or isinstance(data, list):
        data = json.dumps(data).encode()
    return FERNET.encrypt(data).decode()

# 解密函数
def decrypt_data(encrypted_data):
    try:
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.encode()
        decrypted = FERNET.decrypt(encrypted_data).decode()
        try:
            return json.loads(decrypted)
        except:
            return decrypted
    except:
        return encrypted_data

LOGS_DIR = Path(__file__).parent / 'logs'
SSL_DIR = Path(__file__).parent / 'ssl'
DESK_DIR = Path(__file__).parent / 'desk'

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DESK_DIR.mkdir(exist_ok=True)

LOGIN_FAIL_FILE = DATA_DIR / 'login_fail.json'
LOGIN_FAIL_BACKUP_FILE = DATA_DIR / 'login_fail.backup.json'
SESSIONS_FILE = DATA_DIR / 'sessions.json'
CDK_REDEEM_COOLDOWN_FILE = DATA_DIR / 'cdk_cooldown.json'

codesData = [
    {"LC":"","key":"VIP111"},{"LC":"","key":"bc0318"},{"LC":"","key":"VIP222"},{"LC":"","key":"VIP333"},
    {"LC":"","key":"VIP555"},{"LC":"","key":"VIP666"},{"LC":"","key":"vip777"},
    {"LC":"","key":"Vip888"},{"LC":"","key":"VIP999"},{"LC":"","key":"VIP1000"},
    {"LC":"","key":"VIP2000"},{"LC":"","key":"VIP0112"},{"LC":"","key":"VIP0127"},{"LC":"","key":"vip0210"},
    {"LC":"","key":"VIP0212"},{"LC":"","key":"VIP0218"},{"LC":"","key":"vip0223"},
    {"LC":"","key":"vip0304"},{"LC":"","key":"vip0318"},{"LC":"","key":"vip0412"},
    {"LC":"","key":"FL0501"},{"LC":"","key":"vip0511"},{"LC":"","key":"FL0531"},
    {"LC":"","key":"vip0615"},{"LC":"","key":"vip0718"},{"LC":"","key":"VIP0810"},{"LC":"","key":"VIP0818"},
    {"LC":"","key":"vip1001"},
    {"LC":"","key":"bc1007"},
    {"LC":"","key":"vip1205"},{"LC":"","key":"wn1223"},
    {"LC":"","key":"vip0122"},{"LC":"","key":"wn2026"},
    {"LC":"","key":"yx0303"},
    {"LC":"","key":"bf0331"}
]

serverList = [
    {"id": "1", "name": "一区"},
    {"id": "2", "name": "二区"},
    {"id": "3", "name": "三区"},
    {"id": "4", "name": "四区"},
    {"id": "5", "name": "五区"},
    {"id": "6", "name": "六区"},
    {"id": "7", "name": "七区"},
    {"id": "8", "name": "八区"},
    {"id": "9", "name": "九区"},
    {"id": "10", "name": "十区"}
]

executionLogs = []

def get_server_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return 'localhost'

def format_utc8_time(date=None):
    if date is None:
        date = datetime.now(timezone.utc)
    utc8_date = datetime.fromtimestamp(date.timestamp() + 8 * 3600, tz=timezone.utc)
    return utc8_date.strftime('%Y-%m-%d %H:%M:%S')

def mask_account(account):
    if not account:
        return ''
    account_str = str(account)
    if len(account_str) <= 4:
        return '*' * len(account_str)
    visible_start = account_str[:2]
    visible_end = account_str[-2:]
    masked = '*' * min(9, len(account_str) - 4)
    return visible_start + masked + visible_end

def add_log_entry(entry, account=None):
    timestamp = format_utc8_time()
    if account:
        log_entry = f"[{timestamp}] {entry.replace(account, mask_account(account))}"
    else:
        log_entry = f"[{timestamp}] {entry}"
    executionLogs.append(log_entry)
    if len(executionLogs) > MAX_LOG_ENTRIES:
        executionLogs[:] = executionLogs[-MAX_LOG_ENTRIES:]
    today = datetime.now(timezone.utc)
    utc8_today = datetime.fromtimestamp(today.timestamp() + 8 * 3600, tz=timezone.utc)
    date_str = utc8_today.strftime('%Y-%m-%d')
    log_file = LOGS_DIR / f'execution_{date_str}.log'
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    except Exception:
        pass
    return log_entry

def generate_hash(data):
    return hashlib.sha256((json.dumps(data) + SECRET_KEY).encode()).hexdigest()

def verify_hash(data, hash_val):
    return generate_hash(data) == hash_val

def get_client_ip(request):
    ip = None
    headers = request.headers
    if 'x-forwarded-for' in headers:
        ip = headers['x-forwarded-for'].split(',')[0].strip()
    elif 'x-real-ip' in headers:
        ip = headers['x-real-ip'].strip()
    if ip:
        if ip.startswith('::ffff:'):
            ip = ip[7:]
        if ':' in ip and ip.count('.') == 3:
            ip = ip.split(':')[0]
        ip_match = ip.split('.')
        if len(ip_match) == 4:
            ip = '.'.join(ip_match)
        if ip in ('::1', '127.0.0.1', 'localhost'):
            ip = '127.0.0.1'
    return ip or '0.0.0.0'

def load_login_fail_data():
    try:
        if not LOGIN_FAIL_FILE.exists():
            empty_data = {'records': {}, 'hash': generate_hash({'records': {}})}
            save_login_fail_data(empty_data)
            return empty_data
        with open(LOGIN_FAIL_FILE, 'r', encoding='utf-8') as f:
            encrypted_data = json.load(f)
        data = decrypt_data(encrypted_data)
        if 'hash' in data and 'records' in data:
            if verify_hash(data['records'], data['hash']):
                return data
            else:
                if LOGIN_FAIL_BACKUP_FILE.exists():
                    with open(LOGIN_FAIL_BACKUP_FILE, 'r', encoding='utf-8') as bf:
                        backup_encrypted = json.load(bf)
                    backup_data = decrypt_data(backup_encrypted)
                    if 'hash' in backup_data and 'records' in backup_data:
                        if verify_hash(backup_data['records'], backup_data['hash']):
                            with open(LOGIN_FAIL_FILE, 'w', encoding='utf-8') as f:
                                json.dump(encrypt_data(backup_data), f)
                            return backup_data
                default_data = {'records': {}, 'hash': generate_hash({'records': {}})}
                save_login_fail_data(default_data)
                return default_data
        records = data.get('records', data)
        new_hash = generate_hash(records)
        new_data = {'records': records, 'hash': new_hash}
        save_login_fail_data(new_data)
        return new_data
    except Exception:
        if LOGIN_FAIL_BACKUP_FILE.exists():
            try:
                with open(LOGIN_FAIL_BACKUP_FILE, 'r', encoding='utf-8') as bf:
                    backup_encrypted = json.load(bf)
                backup_data = decrypt_data(backup_encrypted)
                if 'hash' in backup_data and 'records' in backup_data:
                    if verify_hash(backup_data['records'], backup_data['hash']):
                        with open(LOGIN_FAIL_FILE, 'w', encoding='utf-8') as f:
                            json.dump(encrypt_data(backup_data), f)
                        return backup_data
            except Exception:
                pass
        default_data = {'records': {}, 'hash': generate_hash({'records': {}})}
        save_login_fail_data(default_data)
        return default_data

def save_login_fail_data(data):
    try:
        records = data.get('records', data)
        hash_val = generate_hash(records)
        save_data = {'records': records, 'hash': hash_val}
        if LOGIN_FAIL_FILE.exists():
            shutil.copy(LOGIN_FAIL_FILE, LOGIN_FAIL_BACKUP_FILE)
        with open(LOGIN_FAIL_FILE, 'w', encoding='utf-8') as f:
            json.dump(encrypt_data(save_data), f, indent=2)
    except Exception:
        pass

def cleanup_login_fail_records():
    try:
        data = load_login_fail_data()
        now = int(time.time() * 1000)
        has_changes = False
        records = data.get('records', {})
        for account in list(records.keys()):
            record = records[account]
            if record.get('lockedUntil') and record['lockedUntil'] <= now:
                del records[account]
                has_changes = True
        if has_changes:
            data['records'] = records
            save_login_fail_data(data)
    except Exception:
        pass

def get_random_lock_time():
    min_time = 3 * 60 * 1000
    max_time = 18 * 60 * 1000
    return random.randint(min_time, max_time)

def check_account_login_fail(account):
    cleanup_login_fail_records()
    data = load_login_fail_data()
    now = int(time.time() * 1000)
    records = data.get('records', {})
    if account in records:
        account_record = records[account]
        if account_record.get('lockedUntil') and account_record['lockedUntil'] > now:
            minutes_remaining = (account_record['lockedUntil'] - now) // 60000
            return {'locked': True, 'minutesRemaining': minutes_remaining, 'lockedUntil': account_record['lockedUntil']}
    return {'locked': False}

def record_account_login_fail(account):
    data = load_login_fail_data()
    now = int(time.time() * 1000)
    records = data.get('records', {})
    if account not in records:
        records[account] = {
            'account': account,
            'failCount': 1,
            'lastFailTime': now,
            'lockedUntil': None
        }
    else:
        record = records[account]
        record['failCount'] += 1
        record['lastFailTime'] = now
        if record['failCount'] >= 2:
            lock_time = get_random_lock_time()
            record['lockedUntil'] = now + lock_time
    data['records'] = records
    save_login_fail_data(data)

def load_cdk_cooldown():
    try:
        if not CDK_REDEEM_COOLDOWN_FILE.exists():
            return {}
        with open(CDK_REDEEM_COOLDOWN_FILE, 'r', encoding='utf-8') as f:
            encrypted_data = json.load(f)
        return decrypt_data(encrypted_data)
    except Exception:
        return {}

def save_cdk_cooldown(cooldown):
    try:
        with open(CDK_REDEEM_COOLDOWN_FILE, 'w', encoding='utf-8') as f:
            json.dump(encrypt_data(cooldown), f, indent=2)
    except Exception:
        pass

def check_cdk_cooldown(account):
    if not account:
        return {'can_redeem': True}
    cooldown = load_cdk_cooldown()
    now = int(time.time() * 1000)
    last_redeem = cooldown.get(account, 0)
    cooldown_ms = CDK_COOLDOWN_MINUTES * 60 * 1000
    if last_redeem and (now - last_redeem) < cooldown_ms:
        elapsed = now - last_redeem
        remaining_ms = cooldown_ms - elapsed
        minutes_remaining = int(remaining_ms / 60000)
        seconds_remaining = int((remaining_ms % 60000) / 1000)
        return {
            'can_redeem': False,
            'minutes_remaining': minutes_remaining,
            'seconds_remaining': seconds_remaining,
            'last_redeem': last_redeem
        }
    return {'can_redeem': True}

def update_cdk_cooldown(account):
    if not account:
        return
    cooldown = load_cdk_cooldown()
    cooldown[account] = int(time.time() * 1000)
    save_cdk_cooldown(cooldown)

def load_sessions():
    try:
        if not SESSIONS_FILE.exists():
            return {}
        with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
            encrypted_data = json.load(f)
        decrypted_sessions = {}
        for session_id, encrypted_session in encrypted_data.items():
            decrypted_sessions[session_id] = decrypt_data(encrypted_session)
        return decrypted_sessions
    except Exception:
        return {}

def save_sessions(sessions):
    try:
        encrypted_sessions = {}
        for session_id, session_data in sessions.items():
            encrypted_sessions[session_id] = encrypt_data(session_data)
        with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(encrypted_sessions, f, indent=2)
    except Exception:
        pass

def generate_auth_code():
    return ''.join(random.choices('0123456789', k=6))

def create_session(account, token, username):
    sessions = load_sessions()
    session_id = uuid.uuid4().hex
    expires_at = int(time.time() * 1000) + SESSION_EXPIRY
    auth_code = generate_auth_code()
    sessions[session_id] = {
        'account': account,
        'token': token,
        'username': username,
        'authCode': auth_code,
        'authCodeUsed': False,
        'createdAt': int(time.time() * 1000),
        'expiresAt': expires_at
    }
    save_sessions(sessions)
    return {'sessionId': session_id, 'expiresAt': expires_at, 'authCode': auth_code}

def get_session(session_id):
    sessions = load_sessions()
    session = sessions.get(session_id)
    if not session:
        return None
    if session['expiresAt'] < int(time.time() * 1000):
        del sessions[session_id]
        save_sessions(sessions)
        return None
    return session

def verify_auth_code(session_id, auth_code):
    sessions = load_sessions()
    session = sessions.get(session_id)
    if not session:
        return False
    if session['expiresAt'] < int(time.time() * 1000):
        del sessions[session_id]
        save_sessions(sessions)
        return False
    if session.get('authCode') != auth_code:
        return False
    if session.get('authCodeUsed'):
        return False
    return True

def mark_auth_code_used(session_id):
    sessions = load_sessions()
    session = sessions.get(session_id)
    if session:
        session['authCodeUsed'] = True
        save_sessions(sessions)

def cleanup_expired_sessions():
    sessions = load_sessions()
    now = int(time.time() * 1000)
    has_changes = False
    expired_sessions = []
    for session_id in list(sessions.keys()):
        if sessions[session_id]['expiresAt'] < now:
            expired_sessions.append(session_id)
            del sessions[session_id]
            has_changes = True
    if has_changes:
        save_sessions(sessions)
    for session_id in expired_sessions:
        try:
            session_file = DATA_DIR / f'session_{session_id}.json'
            if session_file.exists():
                session_file.unlink()
        except Exception:
            pass

redeemProgress = {
    'isRunning': False,
    'total': 0,
    'current': 0,
    'success': 0,
    'fail': 0,
    'startTime': None
}

async def safe_json_response(resp):
    try:
        return await resp.json()
    except aiohttp.client_exceptions.ContentTypeError:
        text = await resp.text()
        try:
            return json.loads(text)
        except:
            return {'code': 500, 'msg': f'服务器响应格式错误: {text[:200]}'}
    except Exception as e:
        return {'code': 500, 'msg': f'解析响应失败: {str(e)}'}

async def handle_progress_get(request):
    return web.json_response({'code': 200, 'data': redeemProgress, 'msg': '获取成功'})

async def handle_progress_start(request):
    try:
        data = await request.json()
        total = data.get('total', 0)
        global redeemProgress
        redeemProgress = {
            'isRunning': True,
            'total': total,
            'current': 0,
            'success': 0,
            'fail': 0,
            'startTime': int(time.time() * 1000)
        }
        add_log_entry(f"开始批量领取任务，总计 {total} 个福利码")
        return web.json_response({'code': 200, 'msg': '进度已初始化'})
    except Exception:
        return web.json_response({'code': 500, 'msg': '启动失败'}, status=500)

async def handle_progress_update(request):
    try:
        data = await request.json()
        if redeemProgress['isRunning']:
            if 'current' in data:
                redeemProgress['current'] = data['current']
            if 'success' in data:
                redeemProgress['success'] = data['success']
            if 'fail' in data:
                redeemProgress['fail'] = data['fail']
        return web.json_response({'code': 200, 'msg': '进度已更新'})
    except Exception:
        return web.json_response({'code': 500, 'msg': '更新失败'}, status=500)

async def handle_progress_stop(request):
    global redeemProgress
    if redeemProgress['isRunning']:
        add_log_entry('批量领取任务被手动停止')
    redeemProgress['isRunning'] = False
    return web.json_response({'code': 200, 'msg': '已停止'})

async def handle_progress_reset(request):
    global redeemProgress
    redeemProgress = {
        'isRunning': False,
        'total': 0,
        'current': 0,
        'success': 0,
        'fail': 0,
        'startTime': None
    }
    return web.json_response({'code': 200, 'msg': '进度已重置'})

async def handle_servers(request):
    return web.json_response({'code': 200, 'data': serverList, 'msg': '获取成功'})

async def handle_login(request):
    try:
        data = await request.json()
        account = data.get('account')
        password = data.get('password')
        jwt_token = request.cookies.get('jwt_token')
        
        if jwt_token:
            payload = verify_jwt_token(jwt_token)
            if payload:
                response = web.json_response({
                    'code': 200,
                    'data': {
                        'token': payload['token'],
                        'username': payload['username'],
                        'account': payload['account'],
                        'expiresAt': payload['exp'] * 1000,
                        'authCode': payload.get('authCode', ''),
                        'authCodeUsed': payload.get('authCodeUsed', False)
                    },
                    'msg': '会话恢复成功'
                })
                response.set_cookie('jwt_token', jwt_token, max_age=JWT_EXPIRATION, httponly=True, samesite='Lax', path='/')
                return response
        
        if not account or not password:
            return web.json_response({'code': 400, 'msg': '账号和密码不能为空'}, status=400)
        
        account_check = check_account_login_fail(account)
        if account_check['locked']:
            return web.json_response({
                'code': 403,
                'msg': f"该账号登录失败次数过多，已被封禁{account_check['minutesRemaining']}分钟",
                'locked': True,
                'minutesRemaining': account_check['minutesRemaining'],
                'lockedUntil': account_check['lockedUntil']
            }, status=403)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=login", params={'account': account, 'password': password}) as resp:
                response_data = await safe_json_response(resp)
        
        if not response_data:
            record_account_login_fail(account)
            return web.json_response({'code': 500, 'msg': '服务器返回空响应'}, status=500)
        
        if response_data.get('code') != 200:
            record_account_login_fail(account)
            return web.json_response(response_data)
        
        if response_data.get('code') == 200 and response_data.get('data', {}).get('token'):
            jwt_token = generate_jwt_token(account, response_data['data']['token'], response_data['data'].get('username', account))
            payload = verify_jwt_token(jwt_token)
            response = web.json_response({
                'code': 200,
                'data': {
                    'token': response_data['data']['token'],
                    'username': response_data['data'].get('username', account),
                    'expiresAt': payload['exp'] * 1000,
                    'authCode': payload.get('authCode', ''),
                    'authCodeUsed': payload.get('authCodeUsed', False)
                },
                'msg': response_data.get('msg', '登录成功')
            })
            response.set_cookie('jwt_token', jwt_token, max_age=JWT_EXPIRATION, httponly=True, samesite='Lax', path='/')
            add_log_entry(f"账号登录成功", account)
            return response
        
        return web.json_response(response_data)
        
    except asyncio.TimeoutError:
        status = 408
        message = '登录请求超时'
        try:
            data = await request.json()
            account = data.get('account')
            if account:
                record_account_login_fail(account)
        except:
            pass
        return web.json_response({'code': status, 'msg': message}, status=status)
    except aiohttp.client_exceptions.ClientConnectorError:
        status = 503
        message = '服务器无响应'
        try:
            data = await request.json()
            account = data.get('account')
            if account:
                record_account_login_fail(account)
        except:
            pass
        return web.json_response({'code': status, 'msg': message}, status=status)
    except Exception as e:
        try:
            data = await request.json()
            account = data.get('account')
            if account:
                record_account_login_fail(account)
        except:
            pass
        status = 500
        message = '登录请求失败'
        return web.json_response({'code': status, 'msg': message, 'error': str(e)}, status=status)

async def handle_logout(request):
    try:
        response = web.json_response({'code': 200, 'msg': '登出成功'})
        response.del_cookie('jwt_token', path='/')
        response.del_cookie('sessionId', path='/')  # 兼容旧的会话管理
        return response
    except Exception:
        return web.json_response({'code': 500, 'msg': '登出失败'}, status=500)

async def handle_verify_auth_code(request):
    try:
        data = await request.json()
        auth_code = data.get('authCode')
        session_id = request.cookies.get('sessionId')
        
        if not session_id or not auth_code:
            return web.json_response({'code': 400, 'msg': '缺少必要参数', 'valid': False}, status=400)
        
        valid = verify_auth_code(session_id, auth_code)
        if valid:
            mark_auth_code_used(session_id)
            return web.json_response({'code': 200, 'msg': '授权码验证成功', 'valid': True})
        else:
            return web.json_response({'code': 403, 'msg': '授权码无效或已使用', 'valid': False}, status=403)
    except Exception as e:
        return web.json_response({'code': 500, 'msg': '服务器错误', 'valid': False}, status=500)

async def handle_verify_session(request):
    try:
        jwt_token = request.cookies.get('jwt_token')
        if not jwt_token:
            # 兼容旧的会话管理
            session_id = request.cookies.get('sessionId')
            if not session_id:
                return web.json_response({'code': 401, 'valid': False, 'msg': '无会话'})
            session = get_session(session_id)
            if session:
                max_age = session['expiresAt'] - int(time.time() * 1000)
                if max_age > 0:
                    response = web.json_response({
                        'code': 200,
                        'valid': True,
                        'data': {
                            'account': session['account'],
                            'username': session['username'],
                            'token': session['token'],
                            'expiresAt': session['expiresAt']
                        },
                        'msg': '会话有效'
                    })
                    response.set_cookie('sessionId', session_id, max_age=int(max_age/1000), httponly=True, samesite='Lax', path='/')
                    return response
            response = web.json_response({'code': 401, 'valid': False, 'msg': '会话已过期'})
            response.del_cookie('sessionId', path='/')
            return response
        
        payload = verify_jwt_token(jwt_token)
        if payload:
            response = web.json_response({
                'code': 200,
                'valid': True,
                'data': {
                    'account': payload['account'],
                    'username': payload['username'],
                    'token': payload['token'],
                    'expiresAt': payload['exp'] * 1000
                },
                'msg': '会话有效'
            })
            response.set_cookie('jwt_token', jwt_token, max_age=JWT_EXPIRATION, httponly=True, samesite='Lax', path='/')
            return response
        
        response = web.json_response({'code': 401, 'valid': False, 'msg': '会话已过期'})
        response.del_cookie('jwt_token', path='/')
        return response
    except Exception:
        return web.json_response({'code': 500, 'msg': '验证会话失败'}, status=500)

async def handle_codes(request):
    return web.json_response({'code': 200, 'data': codesData, 'msg': '获取成功'})

async def handle_check_cooldown(request):
    try:
        # 优先使用 JWT 令牌
        jwt_token = request.cookies.get('jwt_token')
        if jwt_token:
            session = verify_jwt_token(jwt_token)
            if session:
                account = session['account']
                cooldown_status = check_cdk_cooldown(account)
                return web.json_response({'code': 200, 'data': cooldown_status, 'msg': '获取成功'})
            return web.json_response({'code': 401, 'valid': False, 'msg': '会话无效'})
        
        # 兼容旧的会话管理
        session_id = request.cookies.get('sessionId')
        if not session_id:
            return web.json_response({'code': 401, 'valid': False, 'msg': '未登录'})
        session = get_session(session_id)
        if not session:
            return web.json_response({'code': 401, 'valid': False, 'msg': '会话无效'})
        account = session['account']
        cooldown_status = check_cdk_cooldown(account)
        return web.json_response({'code': 200, 'data': cooldown_status, 'msg': '获取成功'})
    except Exception as e:
        return web.json_response({'code': 500, 'msg': f'获取冷却状态失败: {str(e)}'}, status=500)

async def handle_shopdata(request):
    try:
        token = request.query.get('token')
        sid = request.query.get('sid')
        
        if not token or not sid:
            return web.json_response({'code': 400, 'msg': '缺少token或sid参数'}, status=400)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=profile", headers={'Authorization': token}, params={'sid': sid}) as resp:
                profile_data = await safe_json_response(resp)
        
        if profile_data.get('code') != 200:
            return web.json_response({'code': profile_data.get('code', 500), 'msg': profile_data.get('msg', '获取商品数据失败')})
        
        profile_data['data']['shopdata'] = profile_data.get('data', {}).get('shopdata', {})
        
        return web.json_response({'code': 200, 'data': profile_data.get('data', {}), 'msg': '获取成功'})
    except Exception as e:
        return web.json_response({'code': 500, 'msg': f'获取商品数据失败: {str(e)}'}, status=500)

async def handle_role(request):
    try:
        token = request.query.get('token')
        sid = request.query.get('sid')
        if not token or not sid:
            return web.json_response({'code': 400, 'msg': '缺少必要参数'}, status=400)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=getRole", headers={'Authorization': token}, params={'sid': sid}) as resp:
                response_data = await safe_json_response(resp)
        if response_data.get('code') == 200 and response_data.get('data'):
            role_array = []
            data_field = response_data['data']
            if isinstance(data_field, list):
                for role in data_field:
                    role_array.append({
                        'title': role.get('name') or role.get('title') or role.get('rolename') or '未知角色',
                        'value': role.get('uid') or role.get('id') or role.get('value') or ''
                    })
            elif isinstance(data_field, dict):
                role_values = [v for v in data_field.values() if v and isinstance(v, dict)]
                if role_values:
                    for role in role_values:
                        role_array.append({
                            'title': role.get('name') or role.get('title') or role.get('rolename') or '未知角色',
                            'value': role.get('uid') or role.get('id') or role.get('value') or ''
                        })
            if role_array:
                return web.json_response({'code': 200, 'data': role_array, 'msg': '获取成功'})
            return web.json_response({'code': 404, 'data': [], 'msg': '该区服无角色'})
        return web.json_response(response_data)
    except Exception:
        return web.json_response({'code': 500, 'msg': '获取角色失败'}, status=500)

async def handle_profile(request):
    try:
        token = request.query.get('token')
        sid = request.query.get('sid')
        if not token or not sid:
            return web.json_response({'code': 400, 'msg': '缺少必要参数'}, status=400)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=profile", headers={'Authorization': token}, params={'sid': sid}) as resp:
                response_data = await safe_json_response(resp)
        if response_data.get('code') == 200 and response_data.get('data'):
            profile_data = response_data['data']
            if isinstance(profile_data, dict) and 'paydata' not in profile_data:
                profile_data = {'paydata': {'total': 0, 'todaytotal': 0}, **profile_data}
            return web.json_response({'code': 200, 'data': profile_data, 'msg': '获取成功'})
        return web.json_response(response_data)
    except Exception:
        return web.json_response({'code': 500, 'msg': '获取资料失败'}, status=500)

async def handle_redeem_lc(request):
    try:
        data = await request.json()
        token = data.get('token')
        sid = data.get('sid')
        packid = data.get('packid')
        if not token or not sid or not packid:
            return web.json_response({'code': 400, 'msg': '缺少必要参数'}, status=400)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=getGiftRewards", headers={'Authorization': token}, params={'sid': sid, 'packid': packid}) as resp:
                response_data = await safe_json_response(resp)
        if response_data.get('code') == 200:
            add_log_entry(f"LC {packid} 领取成功")
        else:
            add_log_entry(f"LC {packid} 领取失败: {response_data.get('msg', '未知错误')}")
        return web.json_response(response_data)
    except Exception as e:
        try:
            data = await request.json()
            packid = data.get('packid')
        except:
            packid = None
        add_log_entry(f"LC {packid} 领取异常: {str(e)}")
        return web.json_response({'code': 500, 'msg': 'LC领取失败'}, status=500)

async def handle_redeem_cdk(request):
    try:
        data = await request.json()
        token = data.get('token')
        sid = data.get('sid')
        cdk = data.get('cdk')
        uid = data.get('uid')
        account = data.get('account')
        if not token or not sid or not cdk or not uid:
            return web.json_response({'code': 400, 'msg': '缺少必要参数'}, status=400)
        
        if account:
            cooldown_status = check_cdk_cooldown(account)
            if not cooldown_status['can_redeem']:
                return web.json_response({
                    'code': 429,
                    'msg': f"领取过于频繁，请等待{cooldown_status['minutes_remaining']}分{cooldown_status['seconds_remaining']}秒后再试",
                    'cooldown': cooldown_status
                }, status=429)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=getCDKGifts", headers={'Authorization': token}, params={'sid': sid, 'cdk': cdk, 'uid': uid}) as resp:
                response_data = await safe_json_response(resp)
        
        if account and response_data.get('code') == 200:
            update_cdk_cooldown(account)
            add_log_entry(f"CDK {cdk} 领取成功", account)
        elif response_data.get('code') == 200:
            add_log_entry(f"CDK {cdk} 领取成功")
        else:
            add_log_entry(f"CDK {cdk} 领取失败: {response_data.get('msg', '未知错误')}", account)
        return web.json_response(response_data)
    except Exception as e:
        try:
            data = await request.json()
            cdk = data.get('cdk')
        except:
            cdk = None
        add_log_entry(f"CDK {cdk} 领取异常: {str(e)}")
        return web.json_response({'code': 500, 'msg': 'CDK领取失败'}, status=500)

async def handle_logs(request):
    return web.json_response({'code': 200, 'data': executionLogs, 'msg': '获取成功'})

async def handle_logs_list(request):
    try:
        files = []
        for file in LOGS_DIR.glob('execution_*.log'):
            stat = file.stat()
            files.append({
                'name': file.name,
                'date': file.name.replace('execution_', '').replace('.log', ''),
                'size': stat.st_size,
                'modified': stat.st_mtime
            })
        files.sort(key=lambda x: x['date'], reverse=True)
        return web.json_response({'code': 200, 'data': files, 'msg': '获取成功'})
    except Exception:
        return web.json_response({'code': 500, 'msg': '获取日志列表失败'}, status=500)

async def handle_image(request):
    try:
        image_name = request.match_info.get('name', '')
        if not image_name:
            return web.Response(status=404)
        image_path = DESK_DIR / image_name
        if not image_path.exists():
            return web.Response(status=404)
        return web.FileResponse(image_path)
    except Exception:
        return web.Response(status=404)

async def handle_index(request):
    public_dir = Path(__file__).parent / 'public'
    index_file = public_dir / 'cdk.html'
    if index_file.exists():
        return web.FileResponse(index_file)
    return web.Response(text='CDK页面未找到', status=404)

async def handle_shop_page(request):
    public_dir = Path(__file__).parent / 'public'
    shop_file = public_dir / 'shop.html'
    if shop_file.exists():
        return web.FileResponse(shop_file)
    return web.Response(text='商城页面未找到', status=404)

async def handle_lc_page(request):
    public_dir = Path(__file__).parent / 'public'
    lc_file = public_dir / 'LC.html'
    if lc_file.exists():
        return web.FileResponse(lc_file)
    return web.Response(text='累充页面未找到', status=404)

async def handle_create_payment(request):
    try:
        data = await request.json()
        token = data.get('token')
        sid = data.get('sid')
        uid = data.get('uid')
        item_id = data.get('item_id')
        amount = data.get('amount')
        phone = data.get('phone')
        
        if not token or not sid or not uid or not item_id or not amount:
            return web.json_response({'code': 400, 'msg': '缺少必要参数'}, status=400)
        
        if not phone:
            return web.json_response({'code': 400, 'msg': '请填写手机号'}, status=400)
        
        session_id = request.cookies.get('sessionId')
        if session_id:
            session = get_session(session_id)
            if session and session.get('account'):
                login_account = session.get('account')
                if phone != login_account:
                    return web.json_response({'code': 400, 'msg': '手机号必须与登录账号一致'}, status=400)
        
        import base64
        
        extend_data = {
            'uid': uid,
            'serverid': int(sid),
            'item': item_id
        }
        extend_str = base64.b64encode(json.dumps(extend_data).encode()).decode()
        
        amount_in_cents = int(float(amount) * 100)
        
        payment_url = f"http://sdk.gaz.tw:9919/pay/wappay.html?extend={extend_str}&Amount={amount_in_cents}&deviceID={phone}"
        
        return web.json_response({
            'code': 200,
            'data': {'payment_url': payment_url},
            'msg': '获取支付链接成功'
        })
    except Exception as e:
        return web.json_response({'code': 500, 'msg': f'创建支付失败: {str(e)}'}, status=500)

async def handle_ptb_recharge(request):
    try:
        data = await request.json()
        amount = data.get('amount')
        phone = data.get('phone')
        
        if not amount or not phone:
            return web.json_response({'code': 400, 'msg': '缺少金额或手机号'}, status=400)
        
        try:
            amount_int = int(amount)
            if amount_int < 10:
                return web.json_response({'code': 400, 'msg': '平台币充值最低10元'}, status=400)
            if amount_int > 3000:
                return web.json_response({'code': 400, 'msg': '平台币充值单次最高3000元'}, status=400)
        except:
            return web.json_response({'code': 400, 'msg': '金额格式错误'}, status=400)
        
        if not phone or len(phone) < 1:
            return web.json_response({'code': 400, 'msg': '手机号不能为空'}, status=400)
        
        ptb_url = f"http://sdk.gaz.tw:9919/pay/ptb.html?a={amount_int}&b={phone}"
        
        return web.json_response({
            'code': 200,
            'data': {'payment_url': ptb_url},
            'msg': '平台币充值链接已生成'
        })
    except Exception as e:
        return web.json_response({'code': 500, 'msg': f'平台币充值失败: {str(e)}'}, status=500)

claimed_packs_file = DATA_DIR / 'claimed_packs.json'

def load_claimed_packs():
    try:
        if not claimed_packs_file.exists():
            return {}
        with open(claimed_packs_file, 'r', encoding='utf-8') as f:
            encrypted_data = json.load(f)
        return decrypt_data(encrypted_data)
    except Exception:
        return {}

def save_claimed_packs(claimed):
    try:
        with open(claimed_packs_file, 'w', encoding='utf-8') as f:
            json.dump(encrypt_data(claimed), f, indent=2)
    except Exception:
        pass

async def handle_redeem_accumulate(request):
    try:
        data = await request.json()
        token = data.get('token')
        sid = data.get('sid')
        pack_id = data.get('pack_id')
        
        if not token or not sid or not pack_id:
            return web.json_response({'code': 400, 'msg': '缺少必要参数'}, status=400)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=profile", headers={'Authorization': token}, params={'sid': sid}) as resp:
                profile_data = await safe_json_response(resp)
        
        if profile_data.get('code') != 200:
            return web.json_response({'code': 500, 'msg': '获取充值信息失败'}, status=500)
        
        total_pay = profile_data.get('data', {}).get('paydata', {}).get('total', 0)
        
        packs_data = profile_data.get('data', {}).get('packsdata', {})
        
        target_pack = None
        need_pay = 0
        rewards_list = None
        for key, value in packs_data.items():
            try:
                if isinstance(value, str):
                    pack = json.loads(value)
                else:
                    pack = value
                if isinstance(pack, dict):
                    pack_id_str = str(pack.get('id')) if pack.get('id') is not None else str(key)
                    if pack_id_str == str(pack_id):
                        target_pack = pack
                        need_pay = int(pack.get('needpay', 0)) if pack.get('needpay') else 0
                        rewards = pack.get('rewards')
                        if isinstance(rewards, str):
                            try:
                                rewards = json.loads(rewards)
                            except:
                                rewards = []
                        elif not isinstance(rewards, list):
                            if rewards is not None:
                                rewards = [rewards] if isinstance(rewards, (int, str)) else []
                            else:
                                rewards = []
                        rewards_list = rewards
                        break
            except:
                pass
        
        if not target_pack:
            return web.json_response({'code': 404, 'msg': '礼包不存在'}, status=404)
        
        if total_pay < need_pay:
            return web.json_response({'code': 400, 'msg': f'累计充值不足，需要累计充值{need_pay}元，当前累计充值{total_pay}元'})
        
        claimed = load_claimed_packs()
        account = profile_data.get('data', {}).get('account', '')
        if not account:
            return web.json_response({'code': 400, 'msg': '无法获取账号信息'})
        
        claim_key = f"{account}_{sid}_{pack_id}"
        
        if claimed.get(claim_key, False):
            return web.json_response({'code': 400, 'msg': '该礼包已领取过'})
        
        if rewards_list and isinstance(rewards_list, list) and len(rewards_list) > 0:
            success_all = True
            async with aiohttp.ClientSession() as session:
                for reward in rewards_list:
                    item_id = reward.get('item')
                    if not item_id:
                        continue
                    async with session.get(f"{API_BASE}/?do=getGiftRewards", headers={'Authorization': token}, params={'sid': sid, 'packid': item_id}) as resp:
                        reward_result = await safe_json_response(resp)
                    if reward_result.get('code') != 200:
                        success_all = False
                        add_log_entry(f"累充礼包{pack_id}领取奖励{item_id}失败: {reward_result.get('msg', '未知错误')}")
                        break
            if not success_all:
                return web.json_response({'code': 500, 'msg': '部分奖励领取失败，请重试'})
        elif rewards_list:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE}/?do=getGiftRewards", headers={'Authorization': token}, params={'sid': sid, 'packid': rewards_list}) as resp:
                    result = await safe_json_response(resp)
            if result.get('code') != 200:
                return web.json_response(result)
        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE}/?do=getGiftRewards", headers={'Authorization': token}, params={'sid': sid, 'packid': pack_id}) as resp:
                    result = await safe_json_response(resp)
            if result.get('code') != 200:
                return web.json_response(result)
        
        claimed[claim_key] = True
        save_claimed_packs(claimed)
        
        add_log_entry(f"累充礼包{pack_id}领取成功，累计充值{total_pay}元，需要{need_pay}元")
        return web.json_response({'code': 200, 'msg': '领取成功'})
        
    except Exception as e:
        add_log_entry(f"累充礼包领取异常: {str(e)}")
        return web.json_response({'code': 500, 'msg': f'领取失败: {str(e)}'}, status=500)

async def handle_accumulate_packs(request):
    try:
        token = request.query.get('token')
        sid = request.query.get('sid')
        
        if not token or not sid:
            return web.json_response({'code': 400, 'msg': '缺少token或sid参数'}, status=400)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/?do=profile", headers={'Authorization': token}, params={'sid': sid}) as resp:
                profile_data = await safe_json_response(resp)
        
        if profile_data.get('code') != 200:
            return web.json_response({'code': profile_data.get('code', 500), 'msg': profile_data.get('msg', '获取充值信息失败')})
        
        total_pay = profile_data.get('data', {}).get('paydata', {}).get('total', 0)
        account = profile_data.get('data', {}).get('account', '')
        
        packs_data = profile_data.get('data', {}).get('packsdata', {})
        
        accumulate_packs = []
        if isinstance(packs_data, dict):
            for key, value in packs_data.items():
                try:
                    if isinstance(value, str):
                        pack = json.loads(value)
                    else:
                        pack = value
                    if isinstance(pack, dict):
                        pack_id = pack.get('id')
                        if pack_id is None:
                            pack_id = int(key) if key.isdigit() else key
                        pack['id'] = pack_id
                        
                        rewards = pack.get('rewards')
                        if isinstance(rewards, str):
                            try:
                                rewards = json.loads(rewards)
                            except:
                                rewards = []
                        elif not isinstance(rewards, list):
                            if rewards is not None:
                                rewards = [rewards] if isinstance(rewards, (int, str)) else []
                            else:
                                rewards = []
                        pack['rewards'] = rewards
                        
                        accumulate_packs.append(pack)
                except Exception:
                    pass
        
        accumulate_packs.sort(key=lambda x: int(x.get('needpay', 0)) if x.get('needpay') else 0)
        
        claimed = load_claimed_packs()
        
        result_packs = []
        for pack in accumulate_packs:
            pack_id = pack.get('id')
            claim_key = f"{account}_{sid}_{pack_id}"
            pack_needpay = int(pack.get('needpay', 0)) if pack.get('needpay') else 0
            
            rewards = pack.get('rewards', [])
            if not isinstance(rewards, list):
                rewards = []
            
            result_packs.append({
                'id': pack_id,
                'name': pack.get('name', '未知礼包'),
                'needpay': pack_needpay,
                'desc': pack.get('desc', ''),
                'icon': pack.get('icon', 'fa-gift'),
                'iconcolor': pack.get('iconcolor', 'text-yellow'),
                'limit': pack.get('limit', 1),
                'type': pack.get('type', 2),
                'rewards': rewards,
                'claimed': claimed.get(claim_key, False),
                'can_claim': total_pay >= pack_needpay and not claimed.get(claim_key, False)
            })
        
        return web.json_response({
            'code': 200,
            'data': {
                'packs': result_packs,
                'user_total': total_pay
            },
            'msg': '获取成功'
        })
    except Exception as e:
        add_log_entry(f"获取累充礼包异常: {str(e)}")
        return web.json_response({'code': 500, 'msg': f'获取失败: {str(e)}'}, status=500)

def setup_routes(app):
    app.router.add_get('/api/progress', handle_progress_get)
    app.router.add_post('/api/progress/start', handle_progress_start)
    app.router.add_post('/api/progress/update', handle_progress_update)
    app.router.add_post('/api/progress/stop', handle_progress_stop)
    app.router.add_post('/api/progress/reset', handle_progress_reset)
    app.router.add_get('/api/servers', handle_servers)
    app.router.add_post('/api/login', handle_login)
    app.router.add_post('/api/logout', handle_logout)
    app.router.add_post('/api/verify-session', handle_verify_session)
    app.router.add_get('/api/codes', handle_codes)
    app.router.add_get('/api/check-cooldown', handle_check_cooldown)
    app.router.add_get('/api/shopdata', handle_shopdata)
    app.router.add_get('/api/role', handle_role)
    app.router.add_get('/api/profile', handle_profile)
    app.router.add_post('/api/redeem-lc', handle_redeem_lc)
    app.router.add_post('/api/redeem-cdk', handle_redeem_cdk)
    app.router.add_get('/api/logs', handle_logs)
    app.router.add_get('/api/logs/list', handle_logs_list)
    app.router.add_post('/api/create-payment', handle_create_payment)
    app.router.add_post('/api/ptb-recharge', handle_ptb_recharge)
    app.router.add_post('/api/redeem-accumulate', handle_redeem_accumulate)
    app.router.add_get('/api/accumulate-packs', handle_accumulate_packs)
    app.router.add_post('/api/verify-auth-code', handle_verify_auth_code)
    app.router.add_get('/api/image/{name}', handle_image)
    app.router.add_get('/', handle_index)
    app.router.add_get('/shop.html', handle_shop_page)
    app.router.add_get('/LC.html', handle_lc_page)
    app.router.add_static('/', Path(__file__).parent / 'public')

async def background_tasks():
    while True:
        await asyncio.sleep(60)
        cleanup_login_fail_records()
        cleanup_expired_sessions()

async def start_background(app):
    asyncio.create_task(background_tasks())

async def main():
    print("开始启动服务器...")
    app = web.Application()
    print("创建应用实例成功")
    
    setup_routes(app)
    print("设置路由成功")
    
    cors = setup_cors(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })
    for route in app.router.routes():
        cors.add(route)
    print("设置 CORS 成功")
    
    app.on_startup.append(start_background)
    print("添加后台任务成功")
    
    runner = web.AppRunner(app)
    await runner.setup()
    print("设置 AppRunner 成功")
    
    server_ip = get_server_ip()
    print(f"获取服务器 IP 地址: {server_ip}")
    
    print(f"正在启动 HTTP 服务器在 0.0.0.0:{HTTP_PORT}...")
    site = web.TCPSite(runner, '0.0.0.0', HTTP_PORT)
    await site.start()
    print(f"HTTP 服务器运行在 http://{server_ip}:{HTTP_PORT}")
    print(f"本地访问: http://localhost:{HTTP_PORT}")
    print(f"其他设备访问: http://{server_ip}:{HTTP_PORT}")
    
    if SSL_DIR.exists():
        print(f"SSL 目录存在: {SSL_DIR}")
        key_file = SSL_DIR / 'server.key'
        cert_file = SSL_DIR / 'server.crt'
        if key_file.exists() and cert_file.exists():
            print(f"SSL 证书文件存在: {key_file} 和 {cert_file}")
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(cert_file, key_file)
            print("创建 SSL 上下文成功")
            ssl_site = web.TCPSite(runner, '0.0.0.0', HTTPS_PORT, ssl_context=ssl_context)
            await ssl_site.start()
            print(f"HTTPS 服务器运行在 https://{server_ip}:{HTTPS_PORT}")
            print(f"本地访问: https://localhost:{HTTPS_PORT}")
            print(f"其他设备访问: https://unrepentant12.cloud:{HTTPS_PORT}")
        else:
            print(f"SSL证书文件不存在: {key_file} 或 {cert_file}")
    else:
        print(f"SSL证书目录不存在: {SSL_DIR}")
    
    print("服务器已启动，按 Ctrl+C 停止")
    
    stop_event = asyncio.Event()
    
    def signal_handler():
        print("\n正在停止服务器...")
        stop_event.set()
    
    loop = asyncio.get_event_loop()
    import platform
    if platform.system() != 'Windows':
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
    else:
        print("Windows 系统不支持信号处理器，使用 Ctrl+C 停止服务器")
    
    await stop_event.wait()
    
    print("服务器已停止")
    await runner.cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已被用户中断")