#!/usr/bin/env python3
import http.server
import socketserver
import urllib.request
import urllib.parse
import ssl
import json
import os
import secrets
import time
import threading

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
with open(CONFIG_PATH) as f:
    config = json.load(f)

SITE_PASSWORD = config.get('site_password', '')
OPENAI_KEY = config.get('openai_key', '')
CERT_FILE = config.get('cert_file', '')
KEY_FILE = config.get('key_file', '')
HTTPS_MODE = bool(CERT_FILE and KEY_FILE)

# session_token -> expires_at
sessions = {}

SCORES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scores.json')
scores_lock = threading.Lock()

def load_scores():
    if not os.path.exists(SCORES_PATH):
        return {}
    with open(SCORES_PATH) as f:
        return json.load(f)

def save_scores(data):
    with open(SCORES_PATH, 'w') as f:
        json.dump(data, f)

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def get_cookie(headers, name):
    for part in headers.get('Cookie', '').split(';'):
        part = part.strip()
        if part.startswith(name + '='):
            return part[len(name) + 1:]
    return None


class Handler(http.server.SimpleHTTPRequestHandler):

    def is_authed(self):
        if not SITE_PASSWORD:
            return True
        token = get_cookie(self.headers, 'session')
        if not token or token not in sessions:
            return False
        if time.time() > sessions[token]:
            sessions.pop(token, None)
            return False
        return True

    def do_GET(self):
        if self.path in ('/login', '/login?wrong'):
            self.serve_file('login.html')
            return
        if not self.is_authed():
            self.redirect('/login')
            return
        if self.path.startswith('/api/image'):
            self.handle_image()
        elif self.path.startswith('/api/scores'):
            self.handle_get_scores()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/login':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode()
            params = urllib.parse.parse_qs(body)
            password = params.get('password', [''])[0]
            if password == SITE_PASSWORD:
                token = secrets.token_hex(32)
                sessions[token] = time.time() + 86400 * 30  # 30 days
                self.send_response(302)
                secure_flag = '; Secure' if HTTPS_MODE else ''
                self.send_header('Set-Cookie', f'session={token}; Path=/; HttpOnly; SameSite=Lax{secure_flag}')
                self.send_header('Location', '/')
                self.end_headers()
            else:
                self.redirect('/login?wrong')
        elif self.path == '/api/scores':
            self.handle_post_score()
        else:
            self.send_response(404)
            self.end_headers()

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def serve_file(self, filename):
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def handle_image(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        prompt = params.get('prompt', ['dinosaur'])[0]
        seed = params.get('seed', ['1'])[0]

        image_data = None

        if OPENAI_KEY:
            try:
                image_data = self.fetch_openai(prompt)
            except Exception as e:
                print(f'OpenAI failed: {e}, falling back...')

        if image_data is None:
            try:
                encoded = urllib.parse.quote(prompt)
                url = f'https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&seed={seed}&model=turbo'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
                    data = resp.read()
                    if resp.headers.get('Content-Type', '').startswith('image'):
                        image_data = data
            except Exception as e:
                print(f'Pollinations failed: {e}, falling back...')

        if image_data is None:
            url = f'https://loremflickr.com/512/512/dinosaur,prehistoric?random={seed}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                image_data = resp.read()

        self.send_response(200)
        self.send_header('Content-Type', 'image/jpeg')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(image_data)

    def fetch_openai(self, prompt):
        payload = json.dumps({
            'model': 'dall-e-3',
            'prompt': prompt,
            'n': 1,
            'size': '1024x1024',
            'response_format': 'url'
        }).encode()
        req = urllib.request.Request(
            'https://api.openai.com/v1/images/generations',
            data=payload,
            headers={
                'Authorization': f'Bearer {OPENAI_KEY}',
                'Content-Type': 'application/json'
            }
        )
        with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as resp:
            result = json.loads(resp.read())
        image_url = result['data'][0]['url']
        img_req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(img_req, timeout=30, context=ssl_ctx) as img_resp:
            return img_resp.read()

    def handle_get_scores(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        game = params.get('game', [''])[0]
        with scores_lock:
            data = load_scores()
        entries = data.get(game, [])
        body = json.dumps(entries).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def handle_post_score(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode())
        game = str(body.get('game', ''))[:32]
        initials = str(body.get('initials', '???')).upper()[:3]
        score = int(body.get('score', 0))
        if not game:
            self.send_response(400)
            self.end_headers()
            return
        with scores_lock:
            data = load_scores()
            entries = data.get(game, [])
            entries.append({'initials': initials, 'score': score})
            entries.sort(key=lambda x: x['score'], reverse=True)
            data[game] = entries[:10]
            save_scores(data)
        resp = json.dumps(data[game]).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, format, *args):
        pass


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    pass


class RedirectToHTTPSHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get('Host', '').split(':')[0]
        self.send_response(301)
        self.send_header('Location', f'https://{host}{self.path}')
        self.end_headers()

    def do_POST(self):
        host = self.headers.get('Host', '').split(':')[0]
        self.send_response(301)
        self.send_header('Location', f'https://{host}{self.path}')
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    has_openai = '✅ OpenAI DALL-E active' if OPENAI_KEY else '⚠️  No OpenAI key — using fallback images'
    has_auth = '🔒 Password protected' if SITE_PASSWORD else '🔓 No password set'

    if HTTPS_MODE and os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT_FILE, KEY_FILE)

        https_server = ThreadedServer(('', 443), Handler)
        https_server.socket = ctx.wrap_socket(https_server.socket, server_side=True)

        http_server = ThreadedServer(('', 80), RedirectToHTTPSHandler)
        t = threading.Thread(target=http_server.serve_forever, daemon=True)
        t.start()

        print('Server running on https://0.0.0.0:443 (HTTP :80 redirects to HTTPS)')
        print(has_auth)
        print(has_openai)
        https_server.serve_forever()
    else:
        port = int(os.environ.get('PORT', 80))
        server = ThreadedServer(('', port), Handler)
        print(f'Server running on http://0.0.0.0:{port}')
        print(has_auth)
        print(has_openai)
        server.serve_forever()
