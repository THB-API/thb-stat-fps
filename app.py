from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper
import json
import time
import threading

app = Flask(__name__)
CORS(app)

API_BASE = 'https://api.tracker.gg/api/v2'

# Create cloudscraper session (bypasses Cloudflare)
scraper_lock = threading.Lock()
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True,
    }
)
scraper.headers.update({
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://cod.tracker.gg',
    'Referer': 'https://cod.tracker.gg/',
})

# Simple in-memory cache
cache = {}
CACHE_TTL = 300  # 5 min

def get_cached(key):
    if key in cache:
        data, ts = cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del cache[key]
    return None

def set_cached(key, data):
    cache[key] = (data, time.time())
    # Clean old entries if too many
    if len(cache) > 500:
        now = time.time()
        expired = [k for k, (_, t) in cache.items() if now - t > CACHE_TTL]
        for k in expired:
            del cache[k]

def do_request(url):
    cached = get_cached(url)
    if cached:
        return cached, 200

    with scraper_lock:
        try:
            r = scraper.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                set_cached(url, data)
                return data, 200
            return {'error': f'HTTP {r.status_code}', 'detail': r.text[:200]}, r.status_code
        except Exception as e:
            return {'error': str(e)}, 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'thb-cod-proxy', 'cache_size': len(cache)})

@app.route('/profile/<game>/<platform>/<path:username>')
def profile(game, platform, username):
    url = f'{API_BASE}/{game}/standard/profile/{platform}/{username}'
    data, code = do_request(url)
    return jsonify(data), code

@app.route('/matches/<game>/<platform>/<path:username>')
def matches(game, platform, username):
    url = f'{API_BASE}/{game}/standard/matches/{platform}/{username}'
    nxt = request.args.get('next')
    if nxt:
        url += f'?next={nxt}'
    data, code = do_request(url)
    return jsonify(data), code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
