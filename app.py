from flask import Flask, request, jsonify
from flask_cors import CORS
from playwright.sync_api import sync_playwright
import json, time, threading, os

app = Flask(__name__)
CORS(app)

API_BASE = 'https://api.tracker.gg/api/v2'

# Cache
cache = {}
CACHE_TTL = 600  # 10 min

# Browser singleton
browser_lock = threading.Lock()
pw = None
browser = None
context = None

def get_browser():
    global pw, browser, context
    if browser is None:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )
        # Warm up: visit tracker.gg once to get cookies
        page = context.new_page()
        page.goto('https://cod.tracker.gg/warzone', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(3000)
        page.close()
    return context

def fetch_api(url):
    # Check cache
    if url in cache:
        data, ts = cache[url]
        if time.time() - ts < CACHE_TTL:
            return data, 200
        del cache[url]

    with browser_lock:
        try:
            ctx = get_browser()
            page = ctx.new_page()
            resp = page.goto(url, wait_until='domcontentloaded', timeout=15000)
            
            if resp and resp.status == 200:
                body = page.content()
                # Extract JSON from page body
                text = page.evaluate('() => document.body.innerText')
                page.close()
                try:
                    data = json.loads(text)
                    cache[url] = (data, time.time())
                    # Clean old cache
                    if len(cache) > 200:
                        now = time.time()
                        for k in [k for k,(_,t) in cache.items() if now-t > CACHE_TTL]:
                            del cache[k]
                    return data, 200
                except:
                    return {'error': 'Invalid JSON', 'body': text[:300]}, 502
            else:
                status = resp.status if resp else 0
                page.close()
                return {'error': f'HTTP {status}'}, status or 500
        except Exception as e:
            try: page.close()
            except: pass
            return {'error': str(e)}, 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'thb-cod-proxy-pw', 'cache_size': len(cache)})

@app.route('/profile/<game>/<platform>/<path:username>')
def profile(game, platform, username):
    url = f'{API_BASE}/{game}/standard/profile/{platform}/{username}'
    data, code = fetch_api(url)
    return jsonify(data), code

@app.route('/matches/<game>/<platform>/<path:username>')
def matches(game, platform, username):
    url = f'{API_BASE}/{game}/standard/matches/{platform}/{username}'
    nxt = request.args.get('next')
    if nxt:
        url += f'?next={nxt}'
    data, code = fetch_api(url)
    return jsonify(data), code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
