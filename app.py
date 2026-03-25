from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

API_BASE = 'https://api.tracker.gg/api/v2'

HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Origin': 'https://cod.tracker.gg',
    'Referer': 'https://cod.tracker.gg/',
    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'thb-cod-proxy'})

@app.route('/profile/<game>/<platform>/<username>')
def profile(game, platform, username):
    url = f'{API_BASE}/{game}/standard/profile/{platform}/{requests.utils.quote(username, safe="")}'
    try:
        r = SESSION.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return jsonify(data)
        return jsonify({'error': f'HTTP {r.status_code}'}), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/matches/<game>/<platform>/<username>')
def matches(game, platform, username):
    url = f'{API_BASE}/{game}/standard/matches/{platform}/{requests.utils.quote(username, safe="")}'
    nxt = request.args.get('next')
    if nxt:
        url += f'?next={requests.utils.quote(nxt, safe="")}'
    try:
        r = SESSION.get(url, timeout=15)
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify({'error': f'HTTP {r.status_code}'}), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
