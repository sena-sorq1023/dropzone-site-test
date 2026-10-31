#!/usr/bin/env python3
"""公開サイトの作り直しが必要かを判定して GITHUB_OUTPUT に build=true/false を書く。"""
import json, os, urllib.request
from datetime import datetime, timedelta, timezone

URL = os.environ['SUPABASE_URL'].rstrip('/'); KEY = os.environ['SUPABASE_KEY']; SITE = os.environ['SITE_URL'].rstrip('/')
today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()

def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))

need, why = False, ''
try:
    state = get(f'{URL}/rest/v1/site_state?select=last_change', {'apikey': KEY})[0]['last_change']
except Exception as e:  # データベースに届かない
    state, need, why = None, False, f'database error: {e}'
if state is not None:
    try:
        built = get(f'{SITE}/build.json?t={datetime.now().timestamp():.0f}')
    except Exception:
        built = {}
    if built.get('last_change') != state:
        need, why = True, 'data changed'
    elif built.get('date') != today:
        need, why = True, 'new day'
    else:
        why = 'up to date'
force = os.environ.get('FORCE') == 'true'
print(f'build={need or force} ({"forced" if force else why})')
with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
    f.write(f'build={"true" if (need or force) else "false"}\n')
