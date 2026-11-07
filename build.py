#!/usr/bin/env python3
"""DROPZONE 公開サイトの生成。Supabase からデータを読み、静的な HTML を _site/ に書き出す。

環境変数:
  SUPABASE_URL, SUPABASE_KEY  … 公開用の URL と publishable key
  SITE_URL                     … 例 https://dropzone-test.senastudio.jp
  SITE_NOINDEX=1               … テスト環境は検索に載せない
  OUT_DIR                      … 出力先（既定 _site）
"""
import html
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
KEY = os.environ.get('SUPABASE_KEY', '')
SITE = os.environ.get('SITE_URL', 'https://dropzone-test.senastudio.jp').rstrip('/')
NOINDEX = os.environ.get('SITE_NOINDEX') == '1'
OUT = Path(os.environ.get('OUT_DIR', '_site'))
HERE = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).date()

TABLES = ['teams', 'players', 'tournaments', 'tournament_stages', 'standings', 'player_stats', 'transfers', 'articles', 'site_state']


# ---------------------------------------------------------------------------
# データ取得
# ---------------------------------------------------------------------------
def fetch(table):
    rows, off = [], 0
    while True:
        q = f'{URL}/rest/v1/{table}?select=*&order=id&limit=1000&offset={off}'
        if table == 'site_state':
            q = f'{URL}/rest/v1/site_state?select=*'
        req = urllib.request.Request(q, headers={'apikey': KEY, 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as r:
            chunk = json.loads(r.read().decode('utf-8'))
        rows += chunk
        if table == 'site_state' or len(chunk) < 1000:
            return rows
        off += 1000


def load():
    if os.environ.get('DATA_JSON'):
        return json.loads(Path(os.environ['DATA_JSON']).read_text(encoding='utf-8'))
    return {t: fetch(t) for t in TABLES}


# ---------------------------------------------------------------------------
# 小物
# ---------------------------------------------------------------------------
def e(v):
    return html.escape('' if v is None else str(v), quote=True)


def d(v):
    """YYYY.MM.DD"""
    if not v:
        return ''
    return str(v)[:10].replace('-', '.')


def dt(v):
    if not v:
        return ''
    try:
        x = datetime.fromisoformat(str(v).replace('Z', '+00:00')).astimezone(JST)
        return x.strftime('%Y.%m.%d')
    except ValueError:
        return d(v)


def period(a, b):
    if not a:
        return ''
    if not b or a == b:
        return d(a)
    if str(a)[:4] == str(b)[:4]:
        return f'{d(a)} — {d(b)[5:]}'
    return f'{d(a)} — {d(b)}'


CAT = {'news': 'NEWS', 'tournament': 'TOURNAMENT', 'result': 'RESULT', 'transfer': 'TRANSFER', 'world': 'WORLD'}
CAT_JA = {'news': 'ニュース', 'tournament': '大会', 'result': '結果', 'transfer': '移籍', 'world': '世界'}
TSTATUS = {'upcoming': '開催予定', 'ongoing': '開催中', 'completed': '終了'}
TEAMST = {'active': '活動中', 'inactive': '休止中', 'disbanded': '解散'}
KIND = {'join': '加入', 'leave': '脱退', 'loan': 'レンタル', 'retire': '引退', 'role': 'ロール変更'}
LINK_NAMES = {'x': 'X', 'youtube': 'YouTube', 'twitch': 'Twitch', 'tiktok': 'TikTok', 'website': 'Webサイト'}


def md(src):
    """編集サイトと同じルールのミニ Markdown（全部エスケープしてから整形）"""
    def inline(s):
        s = e(s)
        s = re.sub(r'!\[([^\]]*)\]\((https?://[^\s)]+)\)', r'<img src="\2" alt="\1" loading="lazy">', s)
        s = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
        s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
        s = re.sub(r'(^|[^*])\*([^*\s][^*]*)\*', r'\1<em>\2</em>', s)
        return s
    out, para, lst = [], [], None

    def flush_p():
        nonlocal para
        if para:
            out.append('<p>' + '<br>'.join(inline(x) for x in para) + '</p>')
            para = []

    def flush_l():
        nonlocal lst
        if lst:
            out.append(f'<{lst[0]}>' + ''.join(f'<li>{inline(i)}</li>' for i in lst[1]) + f'</{lst[0]}>')
            lst = None

    for ln in str(src or '').replace('\r', '').split('\n'):
        if not ln.strip():
            flush_p(); flush_l(); continue
        m = re.match(r'^(#{1,4})\s+(.*)', ln)
        if m:
            flush_p(); flush_l(); lv = min(4, len(m.group(1)) + 1)
            out.append(f'<h{lv}>{inline(m.group(2))}</h{lv}>'); continue
        m = re.match(r'^\s*[-*]\s+(.*)', ln)
        if m:
            flush_p()
            if not lst or lst[0] != 'ul':
                flush_l(); lst = ['ul', []]
            lst[1].append(m.group(1)); continue
        m = re.match(r'^\s*\d+[.)]\s+(.*)', ln)
        if m:
            flush_p()
            if not lst or lst[0] != 'ol':
                flush_l(); lst = ['ol', []]
            lst[1].append(m.group(1)); continue
        m = re.match(r'^>\s?(.*)', ln)
        if m:
            flush_p(); flush_l(); out.append(f'<blockquote>{inline(m.group(1))}</blockquote>'); continue
        if re.match(r'^---+$', ln.strip()):
            flush_p(); flush_l(); out.append('<hr>'); continue
        flush_l(); para.append(ln)
    flush_p(); flush_l()
    return ''.join(out)


def plain(src, n=120):
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', str(src or ''))
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'[#*>`_-]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:n] + ('…' if len(t) > n else '')


# ---------------------------------------------------------------------------
# データの整理
# ---------------------------------------------------------------------------
class DB:
    def __init__(self, raw):
        self.teams = sorted(raw['teams'], key=lambda r: r['name'].lower())
        self.players = sorted(raw['players'], key=lambda r: r['ign'].lower())
        self.tours = sorted(raw['tournaments'], key=lambda r: (r.get('start_date') or '0000'), reverse=True)
        self.stages = sorted(raw['tournament_stages'], key=lambda r: (r.get('sort_order') or 0, r['name']))
        self.standings = raw['standings']
        self.pstats = raw['player_stats']
        self.transfers = sorted(raw['transfers'], key=lambda r: (r['date'], r.get('created_at') or ''))
        now = datetime.now(timezone.utc)
        def ts(v):
            try:
                return datetime.fromisoformat(str(v).replace('Z', '+00:00'))
            except ValueError:
                return now
        self.articles = sorted([a for a in raw['articles'] if ts(a.get('published_at')) <= now],
                               key=lambda r: ts(r['published_at']), reverse=True)
        self.state = (raw.get('site_state') or [{}])[0]
        self.team = {r['id']: r for r in self.teams}
        self.player = {r['id']: r for r in self.players}
        self.tour = {r['id']: r for r in self.tours}
        self.stage = {r['id']: r for r in self.stages}
        self.stages_of = defaultdict(list)
        for s in self.stages:
            self.stages_of[s['tournament_id']].append(s)
        self.stand_of = defaultdict(list)
        for s in self.standings:
            self.stand_of[s['stage_id']].append(s)
        for v in self.stand_of.values():
            v.sort(key=lambda r: (r.get('rank') is None, r.get('rank') or 0, -(r.get('total') or 0)))
        self.ps_of_stage = defaultdict(list)
        self.ps_of_player = defaultdict(list)
        for p in self.pstats:
            self.ps_of_stage[p['stage_id']].append(p)
            if p.get('player_id'):
                self.ps_of_player[p['player_id']].append(p)
        for v in self.ps_of_stage.values():
            v.sort(key=lambda r: -(r.get('kills') or 0))
        self.tr_of_player = defaultdict(list)
        self.tr_of_team = defaultdict(list)
        for t in self.transfers:
            self.tr_of_player[t['player_id']].append(t)
            for k in ('from_team_id', 'to_team_id'):
                if t.get(k):
                    self.tr_of_team[t[k]].append(t)
        # 現所属：今日までの最新の移籍（なければ選手データの所属）
        self.cur_team = {}
        for p in self.players:
            due = [t for t in self.tr_of_player[p['id']] if t['date'] <= TODAY.isoformat() and t.get('kind') != 'role']
            self.cur_team[p['id']] = due[-1].get('to_team_id') if due else p.get('team_id')
        self.roster = defaultdict(list)
        for pid, tid in self.cur_team.items():
            if tid:
                self.roster[tid].append(self.player[pid])

    # リンク
    def team_link(self, tid, fallback=''):
        t = self.team.get(tid)
        if not t:
            return e(fallback) if fallback else '<span class="mut">フリー</span>'
        logo = f'<img class="tl" src="{e(t["logo_url"])}" alt="" loading="lazy">' if t.get('logo_url') else '<span class="tl tl-ph" aria-hidden="true"></span>'
        return f'<a class="tlink" href="/teams/{t["slug"]}/">{logo}<span>{e(t["name"])}</span></a>'

    def team_name(self, tid, fallback=''):
        t = self.team.get(tid)
        return t['name'] if t else (fallback or '')

    def player_link(self, pid):
        p = self.player.get(pid)
        return f'<a href="/players/{p["slug"]}/">{e(p["ign"])}</a>' if p else '<span class="mut">（不明）</span>'

    def tour_link(self, tid, short=False):
        t = self.tour.get(tid)
        if not t:
            return ''
        return f'<a href="/tournaments/{t["slug"]}/">{e((t.get("short_name") if short else None) or t["name"])}</a>'

    def stage_full(self, sid):
        s = self.stage.get(sid)
        if not s:
            return ''
        t = self.tour.get(s['tournament_id'])
        return f'{t["name"]} — {s["name"]}' if t else s['name']


# ---------------------------------------------------------------------------
# HTML の部品
# ---------------------------------------------------------------------------
NAV = [('NEWS', '/news/'), ('TOURNAMENTS', '/tournaments/'), ('TEAMS', '/teams/'), ('PLAYERS', '/players/'), ('TRANSFERS', '/transfers/')]


def page(path, title, body, *, desc='', on='', og_image='', ticker=''):
    full_title = f'{title} | DROPZONE' if title else 'DROPZONE | 日本と世界のPUBG MOBILE eスポーツ情報'
    desc = desc or '日本と世界のPUBG MOBILE eスポーツの大会結果・チーム・選手・移籍情報をまとめるデータベース。'
    url = SITE + path
    nav = ''.join(f'<a href="{h}"{" class=\"on\" aria-current=\"page\"" if on == l else ""}>{l}</a>' for l, h in NAV)
    robots = '<meta name="robots" content="noindex, nofollow">' if NOINDEX else ''
    og = f'<meta property="og:image" content="{e(og_image)}">' if og_image else f'<meta property="og:image" content="{SITE}/assets/ogp.jpg">'
    return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(desc)}">
{robots}
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="{'article' if path.startswith('/news/') and path != '/news/' else 'website'}">
<meta property="og:site_name" content="DROPZONE">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
{og}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@PUBGM_NewsNow">
<meta name="theme-color" content="#0E0F12">
<link rel="icon" href="/assets/favicon.png" type="image/png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Barlow:wght@500;600;700&family=IBM+Plex+Mono:wght@500&family=Noto+Sans+JP:wght@400;500;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">
</head>
<body>
<a class="skip" href="#main">本文へスキップ</a>
<header class="hd"><div class="wrap hd-in">
<a class="logo" href="/" aria-label="DROPZONE トップ"><img src="/assets/logo.webp" alt="DROPZONE — ESPORTS COMMUNITY NEWS PORTAL" width="300" height="68"></a>
<nav class="nav" aria-label="メインメニュー">{nav}</nav>
<form class="search" role="search" action="/search/"><label for="q" class="sr">サイト内検索</label>
<input id="q" name="q" type="search" placeholder="チーム・選手・大会を検索">
<button type="submit" aria-label="検索"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M20 20 L16 16"></path></svg></button></form>
</div></header>
{ticker}
<main id="main" class="wrap main">{body}</main>
<footer class="ft"><div class="wrap ft-in">
<div class="ft-top"><a class="logo" href="/" aria-label="DROPZONE トップ"><img src="/assets/logo.webp" alt="DROPZONE" width="240" height="54" loading="lazy"></a>
<nav aria-label="フッターメニュー">{"".join(f'<a href="{h}">{l}</a>' for l, h in NAV)}<a href="https://x.com/PUBGM_NewsNow" target="_blank" rel="noopener">X @PUBGM_NewsNow</a></nav></div>
<p class="ft-note">※DROPZONEはファンが運営する非公式の情報サイトで、KRAFTON, Inc.とは関係ありません。</p>
<p class="ft-copy">© 2026 DROPZONE. All Rights Reserved. | © 2026 SENA STUDIO.</p>
</div></footer>
<script src="/assets/site.js" defer></script>
</body>
</html>
'''


def crumb(*items):
    parts = ['<a href="/">トップ</a>']
    for label, href in items:
        parts.append(f'<a href="{href}">{e(label)}</a>' if href else f'<span aria-current="page">{e(label)}</span>')
    return '<nav class="crumb" aria-label="パンくず">' + '<span aria-hidden="true">›</span>'.join(parts) + '</nav>'


def badge(cat, solid=False):
    return f'<span class="badge{" solid" if solid else ""}">{e(CAT.get(cat, cat).upper())}</span>'


def h2(title, more=None):
    m = f'<a href="{more[1]}" class="more">{e(more[0])}</a>' if more else ''
    return f'<div class="h2"><h2>{e(title)}</h2>{m}</div>'


def links_html(links):
    if not links:
        return ''
    return ' '.join(f'<a href="{e(u)}" target="_blank" rel="noopener">{LINK_NAMES.get(k, k)}</a>' for k, u in links.items() if u)


def info_box(title, rows):
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return ''
    return f'<aside class="card info"><h2>{e(title)}</h2><dl>' + ''.join(f'<dt>{e(k)}</dt><dd>{v}</dd>' for k, v in rows) + '</dl></aside>'


def standings_table(db, sid, limit=None, cls=''):
    rows = db.stand_of.get(sid, [])
    if limit:
        rows = rows[:limit]
    if not rows:
        return '<p class="mut">順位表はまだありません。</p>'
    out = []
    for i, r in enumerate(rows):
        note = r.get('note') or ''
        rc = ' class="win"' if r.get('rank') == 1 else (' class="down"' if '降格' in note or '敗退' in note else (' class="up"' if '昇格' in note else ''))
        out.append(f'<tr{rc}><td class="num rk">{e(r.get("rank") if r.get("rank") is not None else i + 1)}</td>'
                   f'<td>{db.team_link(r.get("team_id"), r.get("team_name"))}{f" <span class=\"note\">{e(note)}</span>" if note else ""}</td>'
                   f'<td class="num">{e(r.get("wwcd") or 0)}</td><td class="num">{e(r.get("place_pts") or 0)}</td><td class="num">{e(r.get("kill_pts") or 0)}</td><td class="num tot">{e(r.get("total") or 0)}</td></tr>')
    return (f'<div class="tbl {cls}"><table><thead><tr><th class="num">#</th><th>TEAM</th><th class="num">WWCD</th><th class="num">PLACE</th><th class="num">KILL</th><th class="num">TOTAL</th></tr></thead>'
            f'<tbody>{"".join(out)}</tbody></table></div>')


def pstats_table(db, sid, limit=None):
    rows = db.ps_of_stage.get(sid, [])
    if limit:
        rows = rows[:limit]
    if not rows:
        return ''
    out = []
    for i, r in enumerate(rows):
        m = r.get('matches') or 0
        avg = f'{(r.get("kills") or 0) / m:.1f}' if m else '—'
        out.append(f'<tr><td class="num rk">{i + 1}</td><td>{db.player_link(r.get("player_id"))}</td><td>{db.team_link(r.get("team_id")) if r.get("team_id") else ""}</td>'
                   f'<td class="num">{m}</td><td class="num tot">{e(r.get("kills") or 0)}</td><td class="num">{avg}</td></tr>')
    return (f'<div class="tbl"><table><thead><tr><th class="num">#</th><th>PLAYER</th><th>TEAM</th><th class="num">MATCH</th><th class="num">KILL</th><th class="num">AVG</th></tr></thead>'
            f'<tbody>{"".join(out)}</tbody></table></div>')


def news_rows(db, arts):
    if not arts:
        return '<p class="mut pad">記事はまだありません。</p>'
    return ''.join(f'<a class="nrow" href="/news/{a["slug"]}/" data-cat="{e(a["category"])}"><span class="ndate">{dt(a["published_at"])}</span>{badge(a["category"])}<span class="ntitle">{e(a["title"])}</span></a>' for a in arts)


def tour_card(db, t):
    logo = f'<img src="{e(t["logo_url"])}" alt="" loading="lazy">' if t.get('logo_url') else '<span class="ph" aria-hidden="true">LOGO</span>'
    winner = ''
    if t.get('status') == 'completed':
        ws = []
        for s in db.stages_of.get(t['id'], []):
            st = db.stand_of.get(s['id'])
            if st and st[0].get('rank') == 1:
                ws.append(db.team_name(st[0].get('team_id'), st[0].get('team_name')))
        if ws:
            winner = f'<span class="tc-win">優勝 <b>{e(" / ".join(dict.fromkeys(ws)))}</b></span>'
    return (f'<a class="tc" href="/tournaments/{t["slug"]}/"><span class="tc-logo">{logo}</span><span class="tc-body">'
            f'<span class="tc-name">{e(t["name"])}</span><span class="tc-meta">{period(t.get("start_date"), t.get("end_date"))}{" · " + e(t["region"]) if t.get("region") else ""}</span>{winner}</span></a>')


# ---------------------------------------------------------------------------
# ページ
# ---------------------------------------------------------------------------
def build_index(db):
    arts = db.articles
    feat = next((a for a in arts if a.get('featured')), arts[0] if arts else None)
    heads = [a for a in arts if a is not feat][:4]
    upcoming = [t for t in db.tours if t.get('status') in ('upcoming', 'ongoing')]
    upcoming.sort(key=lambda t: t.get('start_date') or '9999')
    completed = [t for t in db.tours if t.get('status') == 'completed'][:4]
    ticker = ''
    nxt = upcoming[0] if upcoming else None
    if nxt:
        lab = 'LIVE' if nxt.get('status') == 'ongoing' else 'NEXT'
        ticker = (f'<div class="ticker"><div class="wrap ticker-in"><span class="tk-lab">{lab}</span>'
                  f'<span class="tk-txt">{e(nxt["name"])}{" — " + period(nxt.get("start_date"), nxt.get("end_date")) if nxt.get("start_date") else ""}</span>'
                  f'<a href="/tournaments/{nxt["slug"]}/">大会ページ →</a></div></div>')
    # 注目
    feat_html = ''
    if feat:
        cover = f'<a class="cover" href="/news/{feat["slug"]}/" tabindex="-1" aria-hidden="true"><img src="{e(feat["cover_url"])}" alt=""></a>' if feat.get('cover_url') else ''
        feat_html = (f'<article class="card feat">{cover}<div class="feat-body"><div class="meta">{badge(feat["category"], True)}<span>{dt(feat["published_at"])}</span><span>{"世界" if feat.get("scope") == "world" else "日本"}</span></div>'
                     f'<h1><a class="blk" href="/news/{feat["slug"]}/">{e(feat["title"])}</a></h1>{f"<p>{e(feat.get('lead'))}</p>" if feat.get("lead") else ""}</div></article>')
    head_html = ''.join(f'<article class="card hl"><div class="meta"><b>{e(CAT.get(a["category"]))}</b><span>{dt(a["published_at"])}</span></div><a class="blk" href="/news/{a["slug"]}/">{e(a["title"])}</a></article>' for a in heads)
    top = (f'<section class="top" aria-label="注目ニュース">{feat_html}<div class="heads">{h2("HEADLINES")}{head_html or "<p class=mut>記事はまだありません。</p>"}</div></section>') if feat else ''
    # 最新ニュース
    filt = ''.join(f'<button type="button" class="fbtn" data-f="{k}" aria-pressed="{"true" if k == "all" else "false"}">{v}</button>' for k, v in [('all', 'すべて'), ('tournament', '大会'), ('result', '結果'), ('transfer', '移籍'), ('world', '世界')])
    latest = f'<section class="col-main">{h2("LATEST NEWS", ("すべて見る →", "/news/"))}<div class="filters" role="group" aria-label="カテゴリ">{filt}</div><div class="card list" data-filter-list>{news_rows(db, arts[:12])}</div></section>'
    # 右カラム
    side = []
    if upcoming:
        side.append(f'<section>{h2("UPCOMING")}<div class="tcs">{"".join(tour_card(db, t) for t in upcoming[:4])}</div></section>')
    if completed:
        side.append(f'<section>{h2("COMPLETED")}<div class="tcs">{"".join(tour_card(db, t) for t in completed)}</div></section>')
    # トップフラッガー：最新の終了大会で選手成績があるステージ
    for t in completed + [t for t in db.tours if t.get('status') == 'completed']:
        stg = [s for s in db.stages_of.get(t['id'], []) if db.ps_of_stage.get(s['id'])]
        if stg:
            s = stg[0]
            rows = db.ps_of_stage[s['id']][:3]
            li = ''.join(f'<li><span class="rk">{i + 1}</span><span class="tf-n">{db.player_link(r["player_id"])}<small>{e(db.team_name(r.get("team_id")))}</small></span><b>{r.get("kills") or 0}</b></li>' for i, r in enumerate(rows))
            side.append(f'<section>{h2("TOP FRAGGERS")}<div class="card tf"><p class="tf-t">{e(t.get("short_name") or t["name"])} {e(s["name"])}</p><ol>{li}</ol></div></section>')
            break
    teams = [t for t in db.teams if t.get('status') == 'active'][:12]
    teams_html = ''.join(f'<a class="tg" href="/teams/{t["slug"]}/">{f"<img src={'"'}{e(t['logo_url'])}{'"'} alt={'"'}{'"'} loading=lazy>" if t.get("logo_url") else "<span class=tg-ph>" + e(t.get("tag") or t["name"][:2]) + "</span>"}<span>{e(t["name"])}</span></a>' for t in teams)
    if teams:
        side.append(f'<section>{h2("TEAMS", ("チーム一覧 →", "/teams/"))}<div class="tgrid">{teams_html}</div></section>')
    hero = ('<section class="hero" aria-label="DROPZONE"><div class="hero-in">'
            '<div class="hero-txt"><p class="hero-kicker"><span aria-hidden="true"></span>INCOMING SUPPLY DROP</p>'
            '<p class="hero-copy">大会も、移籍も、<br>ここに降ってくる。</p>'
            '<p class="hero-sub">日本と世界の大会・チーム・選手・移籍情報をひとつに。<br class="pc">コミュニティ発のeスポーツニュースポータル。</p></div>'
            '<div class="hero-art" aria-hidden="true"><span class="ring"></span><img src="/assets/crate.webp" alt="" width="280" height="338"></div>'
            '</div></section>')
    body = f'{hero}{top}<div class="cols">{latest}<div class="col-side">{"".join(side)}</div></div>'
    if not arts and not db.tours and not db.teams:
        body = '<section class="card pad"><h1 class="pt">DROPZONE</h1><p>まだデータがありません。編集サイトから記事や大会を追加すると、ここに表示されます。</p></section>'
    return page('/', '', body, ticker=ticker)


def build_news_list(db):
    filt = ''.join(f'<button type="button" class="fbtn" data-f="{k}" aria-pressed="{"true" if k == "all" else "false"}">{v}</button>' for k, v in [('all', 'すべて'), ('tournament', '大会'), ('result', '結果'), ('transfer', '移籍'), ('world', '世界'), ('news', 'ニュース')])
    body = f'{crumb(("ニュース", None))}<h1 class="pt">NEWS</h1><div class="filters" role="group" aria-label="カテゴリ">{filt}</div><div class="card list" data-filter-list>{news_rows(db, db.articles)}</div>'
    return page('/news/', 'ニュース', body, on='NEWS')


def build_article(db, a):
    t = db.tour.get(a.get('tournament_id'))
    rel_teams = [db.team[x] for x in (a.get('team_ids') or []) if x in db.team]
    rel_players = [db.player[x] for x in (a.get('player_ids') or []) if x in db.player]
    cover = f'<figure class="art-cover"><img src="{e(a["cover_url"])}" alt=""></figure>' if a.get('cover_url') else ''
    # 関連する大会の順位表（上位5）
    res = ''
    if t:
        stg = [s for s in db.stages_of.get(t['id'], []) if db.stand_of.get(s['id'])]
        if stg and a.get('category') == 'result':
            res = f'<h2 class="sub">最終順位（上位5チーム）</h2>{standings_table(db, stg[-1]["id"], 5)}<p><a href="/tournaments/{t["slug"]}/">大会ページで全順位を見る →</a></p>'
    share = f'https://x.com/intent/post?text={urllib.parse.quote(a["title"])}&url={urllib.parse.quote(SITE + "/news/" + a["slug"] + "/")}'
    related = [x for x in db.articles if x is not a and (
        (a.get('tournament_id') and x.get('tournament_id') == a.get('tournament_id')) or set(x.get('team_ids') or []) & set(a.get('team_ids') or []))][:4]
    if len(related) < 4:
        related += [x for x in db.articles if x is not a and x not in related][:4 - len(related)]
    side = []
    if t:
        side.append(f'<aside class="card side-t"><span class="lab">TOURNAMENT</span>{db.tour_link(t["id"])}<span class="mut small">{period(t.get("start_date"), t.get("end_date"))}{" · " + e(t["team_count"]) + "チーム" if t.get("team_count") and str(t["team_count"]).isdigit() else ""}</span></aside>')
    if rel_teams or rel_players:
        side.append('<aside class="card side-t"><span class="lab">RELATED</span>' + ''.join(f'<div>{db.team_link(x["id"])}</div>' for x in rel_teams) + ''.join(f'<div>{db.player_link(x["id"])}</div>' for x in rel_players) + '</aside>')
    if related:
        side.append(f'<aside class="card side-n"><span class="lab">NEWS</span>' + ''.join(f'<a class="blk" href="/news/{x["slug"]}/"><span class="mut small">{dt(x["published_at"])}</span>{e(x["title"])}</a>' for x in related) + '</aside>')
    body = (f'{crumb(("ニュース", "/news/"), (CAT_JA.get(a["category"], ""), None))}<div class="art-wrap"><article class="card art">'
            f'<div class="meta">{badge(a["category"], True)}<span>{dt(a["published_at"])}</span><span>{"世界" if a.get("scope") == "world" else "日本"}</span>{f"<span>文：{e(a['author_name'])}</span>" if a.get("author_name") else ""}</div>'
            f'<h1>{e(a["title"])}</h1>{f"<p class=lead>{e(a['lead'])}</p>" if a.get("lead") else ""}{cover}<div class="prose">{md(a.get("body"))}</div>{res}'
            f'<p class="share"><a class="btn" href="{e(share)}" target="_blank" rel="noopener">Xでシェア</a></p></article><div class="art-side">{"".join(side)}</div></div>')
    return page(f'/news/{a["slug"]}/', a['title'], body, desc=a.get('lead') or plain(a.get('body')), on='NEWS', og_image=a.get('cover_url') or '')


def build_tour_list(db):
    groups = [('ongoing', '開催中'), ('upcoming', '開催予定'), ('completed', '終了')]
    secs = []
    for k, label in groups:
        ts = [t for t in db.tours if t.get('status') == k]
        if k != 'completed':
            ts.sort(key=lambda t: t.get('start_date') or '9999')
        if ts:
            secs.append(f'<section>{h2(label)}<div class="tcs grid2">{"".join(tour_card(db, t) for t in ts)}</div></section>')
    body = f'{crumb(("大会", None))}<h1 class="pt">TOURNAMENTS</h1>{"".join(secs) or "<p class=mut>大会はまだありません。</p>"}'
    return page('/tournaments/', '大会', body, on='TOURNAMENTS')


def build_tour(db, t):
    stages = db.stages_of.get(t['id'], [])
    tabs, panels = [], []
    for i, s in enumerate(stages):
        ps = pstats_table(db, s['id'])
        panels.append(f'<section class="panel" id="st-{i}" data-panel><h3 class="sub">{e(s["name"])}</h3>'
                      f'{f"<p class='mut small'>{e(s['schedule'])}</p>" if s.get("schedule") else ""}'
                      f'{standings_table(db, s["id"])}{f"<p class='small mut'>{e(s['notes'])}</p>" if s.get("notes") else ""}'
                      f'{"<h3 class=sub>選手成績</h3>" + ps if ps else ""}</section>')
        tabs.append(f'<button type="button" class="tab" data-tab="st-{i}" aria-selected="{"true" if i == 0 else "false"}">{e(s["name"])}</button>')
    fmt = ''
    if stages:
        fmt = '<div class="fmt">' + ''.join(f'<div class="fmt-i"><b>{e(s["name"])}</b>{f"<span>{e(s['schedule'])}</span>" if s.get("schedule") else ""}{f"<span class=mut>{e(s['notes'])}</span>" if s.get("notes") else ""}</div>' for s in stages) + '</div>'
    # 出場チーム
    tids, extra = [], []
    for s in stages:
        for r in db.stand_of.get(s['id'], []):
            if r.get('team_id') and r['team_id'] not in tids:
                tids.append(r['team_id'])
            elif not r.get('team_id') and r.get('team_name') and r['team_name'] not in extra:
                extra.append(r['team_name'])
    teams_html = ''.join(f'<li>{db.team_link(x)}</li>' for x in tids) + ''.join(f'<li>{e(x)}</li>' for x in extra)
    streams = t.get('streams') or []
    streams_html = ''.join(f'<a class="btn line" href="{e(s.get("url"))}" target="_blank" rel="noopener">{e(s.get("label") or "配信")}</a>' for s in streams if s.get('url'))
    winners = []
    for s in stages:
        st = db.stand_of.get(s['id'])
        if st and st[0].get('rank') == 1:
            winners.append(f'{e(s["name"])}：{db.team_link(st[0].get("team_id"), st[0].get("team_name"))}')
    src = ''
    if t.get('liquipedia_url'):
        src = (f'<p class="small mut credit">出典：<a href="{e(t["liquipedia_url"])}" target="_blank" rel="noopener">Liquipedia</a>'
               f'（<a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener">CC BY-SA 3.0</a>）のデータをもとに作成</p>')
    logo = f'<img class="t-logo" src="{e(t["logo_url"])}" alt="">' if t.get('logo_url') else ''
    info = info_box('TOURNAMENT INFO', [
        ('シリーズ', e(t.get('series'))), ('主催', e(t.get('organizer'))), ('運営', e(t.get('operator'))), ('地域', e(t.get('region'))),
        ('形式', e(t.get('format'))), ('期間', period(t.get('start_date'), t.get('end_date'))), ('チーム数', e(t.get('team_count'))),
        ('賞金', e(t.get('prize'))), ('優勝', '<br>'.join(winners)), ('Tier', e(t.get('tier'))),
    ])
    body = (f'{crumb(("大会", "/tournaments/"), (t.get("short_name") or t["name"], None))}'
            f'<div class="phead">{logo}<div><div class="meta">{f"<span class=chip>{e(t['series'])}</span>" if t.get("series") else ""}<span class="st st-{t.get("status")}">{TSTATUS.get(t.get("status"), "")}</span><span>{e(t.get("region"))}</span></div>'
            f'<h1>{e(t["name"])}</h1><p class="mut">{period(t.get("start_date"), t.get("end_date"))}</p></div></div>'
            f'<div class="two"><div class="col-main">'
            f'{f"<section>{h2('概要')}<div class='card pad'><p class=pre>{e(t['description'])}</p>{fmt}</div></section>" if t.get("description") or fmt else ""}'
            f'{f"<section>{h2('順位表')}<div class=tabs role=tablist>{'\n'.join(tabs)}</div>{'\n'.join(panels)}</section>" if stages else "<p class=mut>順位表はまだありません。</p>"}'
            f'{f"<section>{h2('出場チーム')}<ul class='card teams'>{teams_html}</ul></section>" if teams_html else ""}'
            f'{f"<section>{h2('配信アーカイブ')}<div class=btns>{streams_html}</div></section>" if streams_html else ""}'
            f'{src}'
            f'</div><div class="col-side">{info}</div></div>')
    return page(f'/tournaments/{t["slug"]}/', t['name'], body, desc=plain(t.get('description')) or f'{t["name"]}の順位表・出場チーム・選手成績。', on='TOURNAMENTS', og_image=t.get('logo_url') or '')


def team_results(db, tid):
    out = []
    for r in db.standings:
        if r.get('team_id') != tid:
            continue
        s = db.stage.get(r['stage_id'])
        if not s:
            continue
        t = db.tour.get(s['tournament_id'])
        if not t:
            continue
        out.append((t.get('end_date') or t.get('start_date') or '', t, s, r))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def ordinal(n):
    if n is None:
        return '—'
    return f'{n}{"st" if n % 10 == 1 and n % 100 != 11 else "nd" if n % 10 == 2 and n % 100 != 12 else "rd" if n % 10 == 3 and n % 100 != 13 else "th"}'


def build_team_list(db):
    groups = [('active', '活動中'), ('inactive', '休止中'), ('disbanded', '解散')]
    secs = []
    for k, label in groups:
        ts = [t for t in db.teams if t.get('status') == k]
        if ts:
            cards = ''.join(f'<a class="tg big" href="/teams/{t["slug"]}/">{f"<img src={'"'}{e(t['logo_url'])}{'"'} alt={'"'}{'"'} loading=lazy>" if t.get("logo_url") else "<span class=tg-ph>" + e(t.get("tag") or t["name"][:2]) + "</span>"}<span>{e(t["name"])}</span><small>{len(db.roster.get(t["id"], []))}選手</small></a>' for t in ts)
            secs.append(f'<section>{h2(label)}<div class="tgrid big">{cards}</div></section>')
    body = f'{crumb(("チーム", None))}<h1 class="pt">TEAMS</h1>{"".join(secs) or "<p class=mut>チームはまだありません。</p>"}'
    return page('/teams/', 'チーム', body, on='TEAMS')


def build_team(db, t):
    roster = db.roster.get(t['id'], [])
    rows = ''.join(f'<tr><td>{db.player_link(p["id"])}{f" <span class='mut small'>{e(p['full_ign'])}</span>" if p.get("full_ign") and p["full_ign"] != p["ign"] else ""}</td><td>{e(p.get("role"))}</td><td>{e(p.get("nationality"))}</td></tr>' for p in roster)
    roster_html = f'<div class="tbl"><table><thead><tr><th>PLAYER</th><th>ロール</th><th>国籍</th></tr></thead><tbody>{rows}</tbody></table></div>' if roster else '<p class="mut">登録されている選手はいません。</p>'
    res = team_results(db, t['id'])
    res_html = ''.join(f'<tr><td class="small">{d(dd)}</td><td class="num rk">{ordinal(r.get("rank"))}</td><td>{db.tour_link(tt["id"])} — {e(s["name"])}</td><td class="num">{e(r.get("total") or 0)}</td></tr>' for dd, tt, s, r in res)
    res_table = f'<div class="tbl"><table><thead><tr><th>DATE</th><th class="num">順位</th><th>大会</th><th class="num">PTS</th></tr></thead><tbody>{res_html}</tbody></table></div>' if res else '<p class="mut">大会成績はまだありません。</p>'
    trs = sorted(db.tr_of_team.get(t['id'], []), key=lambda x: x['date'], reverse=True)
    tr_html = ''
    for x in trs:
        inn = x.get('to_team_id') == t['id']
        other = x.get('from_team_id') if inn else x.get('to_team_id')
        tr_html += f'<li><span class="dir {"in" if inn else "out"}">{"IN" if inn else "OUT"}</span><span class="small mut">{d(x["date"])}</span>{db.player_link(x["player_id"])} {"←" if inn else "→"} {db.team_link(other) if other else "<span class=mut>フリー</span>"}</li>'
    logo = f'<img class="t-logo" src="{e(t["logo_url"])}" alt="">' if t.get('logo_url') else f'<span class="t-logo ph">{e(t.get("tag") or "")}</span>'
    ach = t.get('achievements') or []
    info = info_box('TEAM INFO', [
        ('地域', e(t.get('region'))), ('タグ', e(t.get('tag'))), ('設立', e(t.get('founded'))), ('マネージャー', e(t.get('manager'))),
        ('主な実績', '<br>'.join(e(a) for a in ach)), ('リンク', links_html(t.get('links'))),
    ])
    body = (f'{crumb(("チーム", "/teams/"), (t["name"], None))}<div class="phead">{logo}<div><div class="meta"><span>{e(t.get("region"))}</span>{f"<span class=chip>{e(t['tag'])}</span>" if t.get("tag") else ""}<span class="st st-{t.get("status")}">{TEAMST.get(t.get("status"), "")}</span></div><h1>{e(t["name"])}</h1></div></div>'
            f'<div class="two"><div class="col-main">'
            f'{f"<section>{h2('概要')}<div class='card pad'><p class=pre>{e(t['description'])}</p></div></section>" if t.get("description") else ""}'
            f'<section>{h2("ロスター")}{roster_html}</section><section>{h2("大会成績")}{res_table}</section>'
            f'{f"<section>{h2('移籍履歴')}<ul class='card trl'>{tr_html}</ul></section>" if tr_html else ""}'
            f'</div><div class="col-side">{info}</div></div>')
    return page(f'/teams/{t["slug"]}/', t['name'], body, desc=plain(t.get('description')) or f'{t["name"]}のロスター・大会成績・移籍履歴。', on='TEAMS', og_image=t.get('logo_url') or '')


def build_player_list(db):
    rows = ''.join(f'<tr><td>{db.player_link(p["id"])}</td><td class="mut small">{e(p.get("full_ign") or "")}</td><td>{db.team_link(db.cur_team.get(p["id"]))}</td><td>{e(p.get("role"))}</td></tr>' for p in db.players)
    body = (f'{crumb(("選手", None))}<h1 class="pt">PLAYERS</h1><p><input class="filter-in" type="search" placeholder="選手名・チーム名で絞り込み" aria-label="選手を絞り込み" data-filter-table="pl"></p>'
            f'<div class="tbl"><table id="pl"><thead><tr><th>PLAYER</th><th>表記</th><th>TEAM</th><th>ロール</th></tr></thead><tbody>{rows}</tbody></table></div>' if db.players else f'{crumb(("選手", None))}<h1 class="pt">PLAYERS</h1><p class="mut">選手はまだいません。</p>')
    return page('/players/', '選手', body, on='PLAYERS')


def build_player(db, p):
    stats = db.ps_of_player.get(p['id'], [])
    rows_data = []
    for r in stats:
        s = db.stage.get(r['stage_id'])
        if not s:
            continue
        t = db.tour.get(s['tournament_id'])
        if not t:
            continue
        team_rank = None
        for st in db.stand_of.get(s['id'], []):
            if st.get('team_id') and st.get('team_id') == r.get('team_id'):
                team_rank = st.get('rank')
        kill_rank = next((i + 1 for i, x in enumerate(db.ps_of_stage[s['id']]) if x['id'] == r['id']), None)
        rows_data.append((t.get('end_date') or t.get('start_date') or '', t, s, r, team_rank, kill_rank, len(db.ps_of_stage[s['id']])))
    rows_data.sort(key=lambda x: x[0], reverse=True)
    summary = ''
    if rows_data:
        _, t, s, r, trk, krk, n = rows_data[0]
        m = r.get('matches') or 0
        avg = f'{(r.get("kills") or 0) / m:.1f}' if m else '—'
        summary = (f'<div class="kpis"><div class="kpi"><span>合計キル</span><b>{r.get("kills") or 0}</b><small>{e(t.get("short_name") or t["name"])}</small></div>'
                   f'<div class="kpi"><span>キル順位</span><b>#{krk}</b><small>大会全選手中（{n}人）</small></div>'
                   f'<div class="kpi"><span>平均キル</span><b>{avg}</b><small>{m}マッチ</small></div>'
                   f'<div class="kpi"><span>最多キル</span><b>{e(r.get("max_kills") if r.get("max_kills") is not None else "—")}</b><small>1マッチ</small></div></div>')
    # マップ別平均（全大会）
    mk = defaultdict(lambda: [0, 0])
    for r in stats:
        for mname, v in (r.get('map_kills') or {}).items():
            if v.get('matches'):
                mk[mname][0] += v.get('kills') or 0
                mk[mname][1] += v['matches']
    maps_html = ''
    if mk:
        mx = max((k / m) for k, m in mk.values() if m) or 1
        maps_html = '<div class="card pad maps">' + ''.join(f'<div class="mp"><span>{e(n)}</span><span class="bar"><i style="width:{(k / m) / mx * 100:.0f}%"></i></span><b>{k / m:.1f}</b></div>' for n, (k, m) in mk.items() if m) + '</div>'
    res_rows = ''.join(f'<tr><td class="small">{d(dd)}</td><td class="num">{ordinal(trk) if trk else "—"}</td><td>{db.tour_link(t["id"])} — {e(s["name"])}</td><td class="num">{r.get("kills") or 0}</td><td class="num">{(f"{(r.get('kills') or 0) / r['matches']:.1f}") if r.get("matches") else "—"}</td></tr>' for dd, t, s, r, trk, krk, n in rows_data)
    res_html = f'<div class="tbl"><table><thead><tr><th>DATE</th><th class="num">チーム順位</th><th>大会</th><th class="num">KILL</th><th class="num">AVG</th></tr></thead><tbody>{res_rows}</tbody></table></div>' if rows_data else '<p class="mut">大会成績はまだありません。</p>'
    # 所属履歴
    hist = []
    trs = [x for x in db.tr_of_player.get(p['id'], []) if x.get('kind') != 'role']
    for i, x in enumerate(trs):
        if not x.get('to_team_id'):
            continue
        end = next((y['date'] for y in trs[i + 1:]), None)
        future = x['date'] > TODAY.isoformat()
        hist.append(f'<li><span class="small mut">{x["date"][:7].replace("-", ".")} — {"予定" if future else (end[:7].replace("-", ".") if end else "現在")}</span>{db.team_link(x["to_team_id"])}</li>')
    hist.reverse()
    cur = db.cur_team.get(p['id'])
    photo = f'<img class="t-logo round" src="{e(p["photo_url"])}" alt="">' if p.get('photo_url') else ''
    info = info_box('PLAYER INFO', [
        ('IGN', e(p.get('full_ign') or p['ign'])), ('所属', db.team_link(cur) if cur else 'フリー'), ('ロール', e(p.get('role'))),
        ('国籍', e(p.get('nationality'))), ('本名', e(p.get('real_name'))), ('リンク', links_html(p.get('links'))),
    ])
    body = (f'{crumb(("選手", "/players/"), (p["ign"], None))}<div class="phead">{photo}<div><div class="meta">{db.team_link(cur) if cur else "<span class=mut>フリー</span>"}</div><h1>{e(p["ign"])}</h1></div></div>'
            f'<div class="two"><div class="col-main">{summary}'
            f'{f"<section>{h2('紹介')}<div class='card pad'><p class=pre>{e(p['bio'])}</p></div></section>" if p.get("bio") else ""}'
            f'{f"<section>{h2('マップ別 平均キル')}{maps_html}</section>" if maps_html else ""}'
            f'<section>{h2("大会成績")}{res_html}</section>'
            f'{f"<section>{h2('所属履歴')}<ul class='card trl'>{'\n'.join(hist)}</ul></section>" if hist else ""}'
            f'</div><div class="col-side">{info}</div></div>')
    return page(f'/players/{p["slug"]}/', p['ign'], body, desc=f'{p["ign"]}（{db.team_name(cur) or "フリー"}）の大会成績・所属履歴。', on='PLAYERS', og_image=p.get('photo_url') or '')


def build_transfers(db):
    trs = sorted(db.transfers, key=lambda x: (x['date'], x.get('created_at') or ''), reverse=True)
    rows = ''.join(f'<tr><td class="small">{d(x["date"])}{" <span class=chip>予定</span>" if x["date"] > TODAY.isoformat() else ""}</td><td>{db.player_link(x["player_id"])}</td><td>{db.team_link(x.get("from_team_id"))}</td><td aria-hidden="true">→</td><td>{db.team_link(x.get("to_team_id"))}</td><td class="small">{KIND.get(x.get("kind"), "")}{f" <a href={'"'}{e(x['source_url'])}{'"'} target=_blank rel=noopener>情報元</a>" if x.get("source_url") else ""}</td></tr>' for x in trs)
    body = (f'{crumb(("移籍", None))}<h1 class="pt">TRANSFERS</h1>' +
            (f'<div class="tbl"><table><thead><tr><th>DATE</th><th>PLAYER</th><th>FROM</th><th></th><th>TO</th><th>種類</th></tr></thead><tbody>{rows}</tbody></table></div>' if trs else '<p class="mut">移籍情報はまだありません。</p>'))
    return page('/transfers/', '移籍', body, on='TRANSFERS')


def build_search(db):
    body = f'{crumb(("検索", None))}<h1 class="pt">SEARCH</h1><div id="sr" class="card list"><p class="mut pad">検索語を入力してください。</p></div>'
    return page('/search/', '検索', body)


def search_index(db):
    idx = []
    for t in db.teams:
        idx.append({'t': 'チーム', 'n': t['name'], 'k': f'{t["name"]} {t.get("tag") or ""}', 'u': f'/teams/{t["slug"]}/'})
    for p in db.players:
        idx.append({'t': '選手', 'n': p['ign'], 'k': f'{p["ign"]} {p.get("full_ign") or ""} {db.team_name(db.cur_team.get(p["id"]))}', 'u': f'/players/{p["slug"]}/'})
    for t in db.tours:
        idx.append({'t': '大会', 'n': t['name'], 'k': f'{t["name"]} {t.get("short_name") or ""} {t.get("series") or ""}', 'u': f'/tournaments/{t["slug"]}/'})
    for a in db.articles[:500]:
        idx.append({'t': 'ニュース', 'n': a['title'], 'k': a['title'], 'u': f'/news/{a["slug"]}/'})
    return idx


# ---------------------------------------------------------------------------
def write(path, text):
    p = OUT / path.lstrip('/')
    if path.endswith('/'):
        p = p / 'index.html'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def main():
    raw = load()
    db = DB(raw)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(HERE / 'assets', OUT / 'assets')
    write('/', build_index(db))
    write('/news/', build_news_list(db))
    for a in db.articles:
        write(f'/news/{a["slug"]}/', build_article(db, a))
    write('/tournaments/', build_tour_list(db))
    for t in db.tours:
        write(f'/tournaments/{t["slug"]}/', build_tour(db, t))
    write('/teams/', build_team_list(db))
    for t in db.teams:
        write(f'/teams/{t["slug"]}/', build_team(db, t))
    write('/players/', build_player_list(db))
    for p in db.players:
        write(f'/players/{p["slug"]}/', build_player(db, p))
    write('/transfers/', build_transfers(db))
    write('/search/', build_search(db))
    (OUT / 'search.json').write_text(json.dumps(search_index(db), ensure_ascii=False), encoding='utf-8')
    (OUT / '404.html').write_text(page('/404.html', 'ページが見つかりません', '<section class="card pad"><h1 class="pt">404</h1><p>ページが見つかりませんでした。</p><p><a href="/">トップへ戻る</a></p></section>'), encoding='utf-8')
    urls = ['/', '/news/', '/tournaments/', '/teams/', '/players/', '/transfers/'] + [f'/news/{a["slug"]}/' for a in db.articles] + [f'/tournaments/{t["slug"]}/' for t in db.tours] + [f'/teams/{t["slug"]}/' for t in db.teams] + [f'/players/{p["slug"]}/' for p in db.players]
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(f'  <url><loc>{SITE}{u}</loc></url>\n' for u in urls) + '</urlset>\n', encoding='utf-8')
    (OUT / 'robots.txt').write_text('User-agent: *\nDisallow: /\n' if NOINDEX else f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n', encoding='utf-8')
    (OUT / 'build.json').write_text(json.dumps({'last_change': db.state.get('last_change'), 'date': TODAY.isoformat(), 'built_at': datetime.now(JST).isoformat()}), encoding='utf-8')
    host = urllib.parse.urlparse(SITE).hostname
    if host:
        (OUT / 'CNAME').write_text(host + '\n')
    (OUT / '.nojekyll').write_text('')
    print(f'built: {len(db.articles)} articles, {len(db.tours)} tournaments, {len(db.teams)} teams, {len(db.players)} players, {len(db.transfers)} transfers')


if __name__ == '__main__':
    if not URL and not os.environ.get('DATA_JSON'):
        sys.exit('SUPABASE_URL is not set')
    main()
