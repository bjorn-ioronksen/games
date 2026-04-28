#!/usr/bin/env python3
import http.server
import socketserver
import urllib.request
import urllib.parse
import ssl
import json
import os
import secrets
import base64
import time

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
with open(CONFIG_PATH) as f:
    config = json.load(f)

OPENAI_KEY = config.get('openai_key', '')
COGNITO_DOMAIN = config.get('cognito_domain', '')
COGNITO_CLIENT_ID = config.get('cognito_client_id', '')
COGNITO_CLIENT_SECRET = config.get('cognito_client_secret', '')
COGNITO_REDIRECT_URI = config.get('cognito_redirect_uri', '')
COGNITO_REGION = config.get('cognito_region', 'eu-west-1')

# session_token -> {expires_at, username}
sessions = {}

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def get_cookie(headers, name):
    for part in headers.get('Cookie', '').split(';'):
        part = part.strip()
        if part.startswith(name + '='):
            return part[len(name) + 1:]
    return None


def decode_jwt_payload(token):
    payload = token.split('.')[1]
    payload += '=' * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def exchange_code(code):
    data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'client_id': COGNITO_CLIENT_ID,
        'code': code,
        'redirect_uri': COGNITO_REDIRECT_URI,
    }).encode()
    auth = base64.b64encode(f'{COGNITO_CLIENT_ID}:{COGNITO_CLIENT_SECRET}'.encode()).decode()
    req = urllib.request.Request(
        f'{COGNITO_DOMAIN}/oauth2/token',
        data=data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth}',
        }
    )
    with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
        return json.loads(resp.read())


def cognito_login_url():
    params = urllib.parse.urlencode({
        'client_id': COGNITO_CLIENT_ID,
        'response_type': 'code',
        'scope': 'openid email profile',
        'redirect_uri': COGNITO_REDIRECT_URI,
    })
    return f'{COGNITO_DOMAIN}/oauth2/authorize?{params}'


def cognito_logout_url():
    params = urllib.parse.urlencode({
        'client_id': COGNITO_CLIENT_ID,
        'logout_uri': COGNITO_REDIRECT_URI.replace('/callback', '/'),
    })
    return f'{COGNITO_DOMAIN}/logout?{params}'


class Handler(http.server.SimpleHTTPRequestHandler):

    def get_session(self):
        token = get_cookie(self.headers, 'session')
        if not token:
            return None
        session = sessions.get(token)
        if not session:
            return None
        if time.time() > session['expires_at']:
            sessions.pop(token, None)
            return None
        return session

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/callback':
            self.handle_callback(parsed)
            return

        if parsed.path == '/logout':
            self.handle_logout()
            return

        if not self.get_session():
            self.redirect(cognito_login_url())
            return

        if parsed.path.startswith('/api/image'):
            self.handle_image()
        else:
            super().do_GET()

    def do_POST(self):
        self.send_response(404)
        self.end_headers()

    def handle_callback(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get('code', [None])[0]

        if not code:
            self.redirect('/')
            return

        try:
            tokens = exchange_code(code)
            claims = decode_jwt_payload(tokens['id_token'])
            session_token = secrets.token_hex(32)
            sessions[session_token] = {
                'expires_at': claims.get('exp', time.time() + 28800),
                'username': claims.get('email', claims.get('cognito:username', 'user')),
            }
            self.send_response(302)
            self.send_header('Set-Cookie', f'session={session_token}; Path=/; HttpOnly; SameSite=Lax')
            self.send_header('Location', '/')
            self.end_headers()
        except Exception as e:
            print(f'Callback error: {e}')
            self.redirect(cognito_login_url())

    def handle_logout(self):
        token = get_cookie(self.headers, 'session')
        if token:
            sessions.pop(token, None)
        self.send_response(302)
        self.send_header('Set-Cookie', 'session=; Path=/; HttpOnly; Max-Age=0')
        self.send_header('Location', cognito_logout_url())
        self.end_headers()

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
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

    def log_message(self, format, *args):
        pass


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    pass


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = ThreadedServer(('', 80), Handler)
    print(f'Server running on http://0.0.0.0:80')
    print(f'Cognito domain: {COGNITO_DOMAIN or "not configured"}')
    server.serve_forever()
