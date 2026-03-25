from flask import Flask, request, jsonify
from flask_cors import CORS
from playwright.sync_api import sync_playwright
import json, time, threading

app = Flask(__name__)
CORS(app)

API_BASE = 'https://api.tracker.gg/api/v2'
SITE_URL = 'https://cod.tracker.gg/warzone'

# Cache
cache = {}
CACHE_TTL = 600

# Browser state
lock = threading.Lock()
pw_instance = None
browser = None
context = None
cf_cookies = None
cf_cookies_time = 0
CF_COOKIE_TTL = 1800  # refresh cookies every 30 min

def init_browser():
    global pw_instance, browser, context
    if browser is None:
        pw_instance = sync_playwright().start()
        browser = pw_instance.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
    if context is None:
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )
    return context

def get_cf_cookies():
    """Visit tracker.gg website to solve Cloudflare challenge and get cookies"""
    global cf_cookies, cf_cookies_time
    
    now = time.time()
    if cf_cookies and (now - cf_cookies_time) < CF_COOKIE_TTL:
        return cf_cookies
    
    ctx = init_browser()
    page = ctx.new_page()
    try:
        print(f"[*] Visiting {SITE_URL} to get CF cookies...")
        page.goto(SITE_URL, wait_until='networkidle', timeout=30000)
        # Wait for Cloudflare challenge to resolve
        page.wait_for_timeout(5000)
        
        cookies = ctx.cookies()
        cf_cookies = {c['name']: c['value'] for c in cookies}
        cf_cookies_time = time.time()
        print(f"[+] Got {len(cf_cookies)} cookies: {list(cf_cookies.keys())}")
        return cf_cookies
    except Exception as e:
        print(f"[!] Cookie fetch error: {e}")
        return {}
    finally:
        page.close()

def fetch_api(url):
    """Fetch API URL using a real browser page (not requests)"""
    # Check cache
    if url in cache:
        data, ts = cache[url]
        if time.time() - ts < CACHE_TTL:
            return data, 200
        del cache[url]

    with lock:
        try:
            ctx = init_browser()
            
            # Make sure we have CF cookies by visiting site first
            get_cf_cookies()
            
            # Now navigate to the API URL directly - browser has the cookies
            page = ctx.new_page()
            resp = page.goto(url, wait_until='domcontentloaded', timeout=20000)
            
            if resp and resp.status == 200:
                text = page.evaluate('() => document.body.innerText')
                page.close()
                try:
                    data = json.loads(text)
                    cache[url] = (data, time.time())
                    # Clean cache
                    if len(cache) > 200:
                        now = time.time()
                        expired = [k for k,(_, t) in cache.items() if now - t > CACHE_TTL]
                        for k in expired:
                            del cache[k]
                    return data, 200
                except:
                    return {'error': 'Invalid JSON', 'body': text[:500]}, 502
            else:
                status = resp.status if resp else 0
                # If 403, try to refresh cookies and retry once
                if status == 403:
                    page.close()
                    global cf_cookies_time
                    cf_cookies_time = 0  # force cookie refresh
                    get_cf_cookies()
                    
                    page = ctx.new_page()
                    resp2 = page.goto(url, wait_until='domcontentloaded', timeout=20000)
                    if resp2 and resp2.status == 200:
                        text = page.evaluate('() => document.body.innerText')
                        page.close()
                        try:
                            data = json.loads(text)
                            cache[url] = (data, time.time())
                            return data, 200
                        except:
                            return {'error': 'Invalid JSON retry'}, 502
                    page.close()
                    return {'error': f'HTTP {resp2.status if resp2 else 0} after retry'}, 403
                
                page.close()
                return {'error': f'HTTP {status}'}, status or 500
        except Exception as e:
            try: page.close()
            except: pass
            return {'error': str(e)}, 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'thb-cod-proxy',
        'cache_size': len(cache),
        'has_cookies': cf_cookies is not None and len(cf_cookies) > 0
    })

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

# Warm up on startup
@app.before_request
def warmup():
    app.before_request_funcs[None].remove(warmup)
    try:
        with lock:
            get_cf_cookies()
    except:
        pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
