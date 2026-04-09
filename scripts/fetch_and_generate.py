       """
The Lede — fetch_and_generate.py v3
"""

import os
import re
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from urllib.parse import urlparse
from collections import defaultdict
import html as html_lib

# ─────────────────────────────────────
# CONFIG
# ─────────────────────────────────────

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
NEWSAPI_KEY = os.environ["NEWSAPI_KEY"]

NEWSAPI_BASE = "https://newsapi.org/v2/everything"
MAX_STORIES_PER_TOPIC = 7
LOOKBACK_HOURS = 48

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ─────────────────────────────────────
# TOPIC DEFINITIONS
# ─────────────────────────────────────

TOPICS = {
    "civic-tech": {
        "label": "Civic Tech & GovTech",
        "newsapi_queries": [
            '"civic tech" OR "govtech" OR "government technology"',
            '"digital government" OR "government software" OR "public sector technology"',
        ],
        "newsapi_domains": "statescoop.com,govtech.com,nextgov.com,federalnewsnetwork.com,route-fifty.com",
        "rss_feeds": [
            "https://statescoop.com/feed/",
            "https://www.govtech.com/rss.xml",
            "https://www.route-fifty.com/rss.xml",
        ],
    },
    "housing": {
        "label": "Housing Policy",
        "newsapi_queries": [
            '"affordable housing" OR "housing policy" OR "zoning reform"',
            '"housing crisis" OR "homelessness" OR "rent control" OR "housing voucher"',
        ],
        "newsapi_domains": "shelterforce.org,housingwire.com,nlihc.org,bisnow.com",
        "rss_feeds": [
            "https://shelterforce.org/feed/",
            "https://www.housingwire.com/feed/",
        ],
    },
    "nonprofit": {
        "label": "Nonprofit & Grants",
        "newsapi_queries": [
            '"nonprofit" AND ("grant" OR "funding" OR "philanthropy")',
            '"foundation" AND ("awards grant" OR "announces funding" OR "social impact")',
        ],
        "newsapi_domains": "philanthropy.com,nonprofitquarterly.org,candid.org",
        "rss_feeds": [
            "https://nonprofitquarterly.org/feed/",
            "https://blog.candid.org/feed/",
        ],
    },
    "ai-tech": {
        "label": "AI & Tech",
        "newsapi_queries": [
            '"artificial intelligence" AND ("policy" OR "regulation" OR "governance")',
            '"large language model" OR "generative AI" OR "AI ethics"',
        ],
        "newsapi_domains": "technologyreview.com,wired.com,theverge.com,arstechnica.com",
        "rss_feeds": [
            "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            "https://www.technologyreview.com/feed/",
        ],
    },
    "penguins": {
        "label": "Pittsburgh Penguins",
        "newsapi_queries": [
            '"Pittsburgh Penguins"',
        ],
        "newsapi_domains": "nhl.com,pensburgh.com,pittsburghpost-gazette.com,theathletic.com",
        "rss_feeds": [
            "https://www.pensburgh.com/rss/current",
        ],
    },
    "general": {
        "label": "General News",
        "newsapi_queries": [],
        "newsapi_domains": "",
        "rss_feeds": [
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        ],
    },
}

# ─────────────────────────────────────
# FETCH HELPERS
# ─────────────────────────────────────

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def fetch_newsapi(query: str, domains: str = "") -> list:
    if not query:
        return []
    from_date = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": NEWSAPI_KEY,
        "pageSize": 10,
    }
    if domains:
        params["domains"] = domains
    try:
        resp = requests.get(NEWSAPI_BASE, params=params, timeout=10)
        data = resp.json()
        articles = data.get("articles", [])
        return [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "description": a.get("description", "") or "",
                "source_domain": get_domain(a.get("url", "")),
                "published_at": a.get("publishedAt", ""),
                "source_label": a.get("source", {}).get("name", ""),
            }
            for a in articles
            if a.get("title") and a.get("url") and "[Removed]" not in a.get("title", "")
        ]
    except Exception as e:
        print(f"  NewsAPI error for '{query}': {e}")
        return []


def fetch_rss(feed_url: str) -> list:
    try:
        feed = feedparser.parse(feed_url)
        stories = []
        for entry in feed.entries[:12]:
            url = entry.get("link", "")
            title = entry.get("title", "")
            description = re.sub(r"<[^>]+>", "", entry.get("summary", "") or "")[:300]
            if not url or not title:
                continue
            stories.append({
                "title": title,
                "url": url,
                "description": description,
                "source_domain": get_domain(url),
                "published_at": entry.get("published", "") or entry.get("updated", ""),
                "source_label": feed.feed.get("title", get_domain(feed_url)),
            })
        return stories
    except Exception as e:
        print(f"  RSS error for {feed_url}: {e}")
        return []


def fetch_all_stories() -> dict:
    all_stories = {}
    seen_urls = set()

    for slug, topic in TOPICS.items():
        stories = []
        domains = topic.get("newsapi_domains", "")

        for query in topic["newsapi_queries"]:
            print(f"  NewsAPI [{slug}]: {query[:60]}")
            for s in fetch_newsapi(query, domains):
                if s["url"] not in seen_urls:
                    seen_urls.add(s["url"])
                    s["topic_slug"] = slug
                    stories.append(s)

        for feed_url in topic["rss_feeds"]:
            print(f"  RSS [{slug}]: {feed_url}")
            for s in fetch_rss(feed_url):
                if s["url"] not in seen_urls:
                    seen_urls.add(s["url"])
                    s["topic_slug"] = slug
                    stories.append(s)

        all_stories[slug] = stories[:MAX_STORIES_PER_TOPIC]
        print(f"  [{slug}] {len(all_stories[slug])} stories kept")

    return all_stories


# ─────────────────────────────────────
# HTML GENERATION
# ─────────────────────────────────────

def format_date() -> str:
    return datetime.now(timezone.utc).strftime("%A, %B %-d, %Y").upper()


def story_card_html(story: dict, size: str = "sm", grid_style: str = "") -> str:
    """size: 'lg' | 'md' | 'sm'"""
    title = html_lib.escape(story.get("title", ""))
    url = html_lib.escape(story.get("url", ""))
    desc = html_lib.escape(story.get("description", ""))[:300]
    source = html_lib.escape(story.get("source_label", story.get("source_domain", "")))
    data_url = html_lib.escape(story.get("url", ""))
    style_attr = f' style="{grid_style}"' if grid_style else ""

    desc_html = f'<p class="story-desc">{desc}{"…" if len(desc)==300 else ""}</p>' if desc else ""

    return f"""<article class="story-card size-{size}"{style_attr} data-url="{data_url}">
      <h3 class="story-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
      {desc_html}
      <div class="story-meta">
        <span class="source-label">{source}</span>
        <span class="vote-buttons">
          <button class="vote-btn up" onclick="vote(this,'{data_url}',1)" title="Upvote">▲</button>
          <button class="vote-btn down" onclick="vote(this,'{data_url}',-1)" title="Downvote">▼</button>
        </span>
      </div>
    </article>"""


def topic_section_html(slug: str, stories: list) -> str:
    label = TOPICS[slug]["label"]
    if not stories:
        return ""

    # Flat 4-column grid. Explicit grid positions per slot:
    #  Row 1-2, Col 1-2 : Story 0 (lg) — big feature
    #  Row 1,   Col 3   : Story 1 (md)
    #  Row 1,   Col 4   : Story 2 (md)
    #  Row 2,   Col 3-4 : Story 3 (md) — spans two cols
    #  Row 3,   Col 1-2 : Story 4 (sm) — wider small
    #  Row 3,   Col 3   : Story 5 (sm)
    #  Row 3,   Col 4   : Story 6 (sm)
    # No row-spanning — width only. Each row auto-sizes to its content.
    # lg = wide column span + big font. No empty space possible.
    LAYOUT_A = [  # Row1: 3+1 | Row2: 1+2+1 | Row3: 2+2
        ("lg", "grid-column:1/4;"),
        ("md", "grid-column:4/5;"),
        ("sm", "grid-column:1/2;"),
        ("md", "grid-column:2/4;"),
        ("sm", "grid-column:4/5;"),
        ("sm", "grid-column:1/3;"),
        ("sm", "grid-column:3/5;"),
    ]
    LAYOUT_B = [  # Row1: 2+2 | Row2: 1+3 | Row3: 1+1+2
        ("md", "grid-column:1/3;"),
        ("md", "grid-column:3/5;"),
        ("sm", "grid-column:1/2;"),
        ("lg", "grid-column:2/5;"),
        ("sm", "grid-column:1/2;"),
        ("sm", "grid-column:2/4;"),
        ("sm", "grid-column:4/5;"),
    ]
    LAYOUT_C = [  # Row1: 1+1+2 | Row2: 3+1 | Row3: 2+1+1
        ("sm", "grid-column:1/2;"),
        ("sm", "grid-column:2/3;"),
        ("md", "grid-column:3/5;"),
        ("lg", "grid-column:1/4;"),
        ("sm", "grid-column:4/5;"),
        ("sm", "grid-column:1/3;"),
        ("sm", "grid-column:3/4;"),
    ]
    LAYOUT_D = [  # Row1: 4 banner | Row2: 2+1+1 | Row3: 1+2+1
        ("lg", "grid-column:1/5;"),
        ("md", "grid-column:1/3;"),
        ("sm", "grid-column:3/4;"),
        ("sm", "grid-column:4/5;"),
        ("sm", "grid-column:1/2;"),
        ("md", "grid-column:2/4;"),
        ("sm", "grid-column:4/5;"),
    ]
    LAYOUT_E = [  # Row1: 1+3 | Row2: 2+2 | Row3: 1+1+1+1
        ("sm", "grid-column:1/2;"),
        ("lg", "grid-column:2/5;"),
        ("md", "grid-column:1/3;"),
        ("md", "grid-column:3/5;"),
        ("sm", "grid-column:1/2;"),
        ("sm", "grid-column:2/3;"),
        ("sm", "grid-column:3/5;"),
    ]
    LAYOUT_F = [  # Row1: 2+1+1 | Row2: 1+2+1 | Row3: 3+1
        ("md", "grid-column:1/3;"),
        ("sm", "grid-column:3/4;"),
        ("sm", "grid-column:4/5;"),
        ("sm", "grid-column:1/2;"),
        ("lg", "grid-column:2/4;"),
        ("sm", "grid-column:4/5;"),
        ("md", "grid-column:1/4;"),
    ]

    TOPIC_LAYOUTS = {
        "civic-tech": LAYOUT_A,
        "housing":    LAYOUT_B,
        "nonprofit":  LAYOUT_C,
        "ai-tech":    LAYOUT_D,
        "penguins":   LAYOUT_E,
        "general":    LAYOUT_F,
    }
    SLOTS = TOPIC_LAYOUTS.get(slug, LAYOUT_A)

    cards = ""
    for i, story in enumerate(stories[:7]):
        size, gs = SLOTS[i] if i < len(SLOTS) else ("sm", "")
        cards += story_card_html(story, size, gs)

    return f"""<section class="topic-section" id="{slug}">
    <div class="section-rule"><span class="section-label">{label}</span></div>
    <div class="topic-grid">{cards}</div>
  </section>"""


def generate_html(stories_by_topic: dict) -> str:
    date_str = format_date()
    sections = "\n".join(
        topic_section_html(slug, stories)
        for slug, stories in stories_by_topic.items()
        if stories
    )
    nav_links = "\n".join(
        f'<a href="#{slug}">{TOPICS[slug]["label"]}</a>'
        for slug in stories_by_topic if stories_by_topic[slug]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>The Lede — {date_str}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --black:     #0a0a0a;
      --ink:       #1a1a1a;
      --ink-mid:   #555;
      --ink-light: #888;
      --rule:      #1a1a1a;
      --rule-lt:   #d4d4d4;
      --bg:        #ffffff;
      --bg-alt:    #f6f6f6;
      --serif: 'Georgia','Times New Roman',serif;
      --sans:  'Franklin Gothic Medium','Arial Narrow',Arial,sans-serif;
    }}
    body {{ background: var(--bg); color: var(--ink); font-family: var(--serif); font-size: 16px; line-height: 1.5; }}
    a {{ color: inherit; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* MASTHEAD */
    .masthead {{ border-bottom: 4px double var(--rule); padding: 0 2rem; background: var(--bg); }}
    .mast-top {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 0.5rem 0; border-bottom: 1px solid var(--rule-lt);
      font-family: var(--sans); font-size: 0.65rem; letter-spacing: 0.12em;
      text-transform: uppercase; color: var(--ink-light);
    }}
    .mast-title {{
      text-align: center; font-family: var(--serif);
      font-size: clamp(3.5rem, 10vw, 7rem); font-weight: 900;
      letter-spacing: -0.03em; line-height: 1; padding: 0.4rem 0;
      color: var(--black);
    }}
    .mast-bottom {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 0.4rem 0; border-top: 1px solid var(--rule-lt);
      font-family: var(--sans); font-size: 0.63rem; letter-spacing: 0.1em;
      text-transform: uppercase; color: var(--ink-light);
    }}

    /* AUTH */
    .auth-bar {{
      display: flex; justify-content: flex-end; align-items: center; gap: 0.75rem;
      padding: 0.35rem 2rem; background: var(--bg-alt);
      border-bottom: 1px solid var(--rule-lt);
      font-family: var(--sans); font-size: 0.7rem;
    }}
    #auth-status {{ color: var(--ink-light); }}
    #sign-in-btn, #sign-out-btn {{
      background: var(--black); color: #fff; border: none;
      padding: 0.25rem 0.85rem; font-family: var(--sans); font-size: 0.67rem;
      letter-spacing: 0.06em; text-transform: uppercase; cursor: pointer;
    }}
    #sign-in-btn:hover, #sign-out-btn:hover {{ background: var(--ink-mid); }}

    /* NAV */
    .section-nav {{
      background: var(--black); display: flex; flex-wrap: wrap;
      padding: 0 2rem;
    }}
    .section-nav a {{
      color: #fff; font-family: var(--sans); font-size: 0.67rem;
      letter-spacing: 0.12em; text-transform: uppercase;
      padding: 0.55rem 1rem; border-right: 1px solid #2a2a2a; display: block;
    }}
    .section-nav a:first-child {{ border-left: 1px solid #2a2a2a; }}
    .section-nav a:hover {{ background: #1e1e1e; text-decoration: none; }}

    /* MAIN */
    main {{ max-width: 1280px; margin: 0 auto; padding: 0 2rem 3rem; }}

    /* SECTION */
    .topic-section {{ padding: 1.75rem 0 0; border-bottom: 3px double var(--rule); margin-bottom: 0; }}
    .topic-section:last-child {{ border-bottom: none; }}

    .section-rule {{
      display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem;
    }}
    .section-rule::before, .section-rule::after {{
      content: ''; flex: 1; height: 1px; background: var(--rule);
    }}
    .section-label {{
      font-family: var(--sans); font-size: 0.68rem; font-weight: 700;
      letter-spacing: 0.22em; text-transform: uppercase; white-space: nowrap;
    }}

    /* TOPIC GRID — flat 4-column newspaper grid */
    .topic-grid {{
      display: grid;
      grid-template-columns: 3fr 2fr 2fr 2fr;
      grid-template-rows: auto auto auto;
      border-top: 2px solid var(--rule);
      border-left: 1px solid var(--rule-lt);
      margin-bottom: 1.75rem;
    }}

    /* CARDS */
    .story-card {{
      padding: 1rem 1.1rem 0.9rem;
      border-right: 1px solid var(--rule-lt);
      border-bottom: 1px solid var(--rule-lt);
      display: flex; flex-direction: column; gap: 0.45rem;
      background: var(--bg);
      transition: background 0.1s;
    }}
    .story-card:hover {{ background: var(--bg-alt); }}

    /* sizes */
    .size-lg .story-title {{ font-size: 1.55rem; line-height: 1.2; font-weight: 800; }}
    .size-lg .story-desc  {{ font-size: 0.88rem; line-height: 1.7; flex: 1; -webkit-line-clamp: unset; display: block; overflow: visible; }}

    .size-md .story-title {{ font-size: 1.05rem; line-height: 1.25; font-weight: 700; }}
    .size-md .story-desc  {{ font-size: 0.8rem; }}

    .size-sm .story-title {{ font-size: 0.9rem; line-height: 1.3; font-weight: 700; }}
    .size-sm .story-desc  {{ -webkit-line-clamp: 2; }}

    .story-title {{ font-family: var(--serif); color: var(--black); }}
    .story-desc  {{ color: var(--ink-mid); font-size: 0.82rem; line-height: 1.5;
                    overflow: hidden; display: -webkit-box;
                    -webkit-line-clamp: 4; -webkit-box-orient: vertical; flex: 1; }}

    .story-meta {{
      display: flex; justify-content: space-between; align-items: center;
      border-top: 1px solid var(--rule-lt); padding-top: 0.45rem; margin-top: auto;
    }}
    .source-label {{
      font-family: var(--sans); font-size: 0.6rem; letter-spacing: 0.1em;
      text-transform: uppercase; color: var(--ink-light);
    }}
    .vote-buttons {{ display: flex; gap: 2px; }}
    .vote-btn {{
      background: var(--bg-alt); border: none; color: var(--ink-light);
      width: 24px; height: 24px; cursor: pointer; font-size: 0.58rem;
      display: flex; align-items: center; justify-content: center;
    }}
    .vote-btn:hover {{ background: var(--black); color: #fff; }}
    .vote-btn.voted-up {{ background: #1a5c1a; color: #fff; }}
    .vote-btn.voted-down {{ background: var(--black); color: #fff; }}

    /* FOOTER */
    footer {{
      text-align: center; font-family: var(--sans); font-size: 0.63rem;
      letter-spacing: 0.12em; color: var(--ink-light); padding: 2rem 1rem;
      border-top: 1px solid var(--rule-lt); text-transform: uppercase;
    }}

    /* TOAST */
    #toast {{
      position: fixed; bottom: 1.5rem; right: 1.5rem; background: var(--black);
      color: #fff; font-family: var(--sans); font-size: 0.75rem;
      padding: 0.55rem 1.1rem; opacity: 0; transition: opacity 0.25s;
      pointer-events: none; letter-spacing: 0.05em;
    }}
    #toast.show {{ opacity: 1; }}

    @media (max-width: 700px) {{
      .topic-grid {{ grid-template-columns: 1fr; }}
      .col-stack {{ grid-template-rows: auto; }}
      .section-nav {{ overflow-x: auto; flex-wrap: nowrap; padding: 0; }}
      .masthead {{ padding: 0 1rem; }}
      main {{ padding: 0 1rem 2rem; }}
    }}
  </style>
</head>
<body>

<header class="masthead">
  <div class="mast-top">
    <span>Est. 2026</span>
    <span>{date_str}</span>
    <span>Your Daily Briefing</span>
  </div>
  <h1 class="mast-title">The Lede</h1>
  <div class="mast-bottom">
    <span>Civic Tech &bull; Housing &bull; Nonprofits &bull; AI &bull; Penguins</span>
    <span>gracemitchell13.github.io/thelede</span>
  </div>
</header>

<div class="auth-bar">
  <span id="auth-status">Not signed in — votes won't be saved</span>
  <button id="sign-in-btn" onclick="signIn()">Sign In with Google</button>
  <button id="sign-out-btn" style="display:none" onclick="signOut()">Sign Out</button>
</div>

<nav class="section-nav">{nav_links}</nav>

<main>{sections}</main>

<footer>The Lede &mdash; {date_str} &mdash; Powered by NewsAPI &amp; RSS</footer>
<div id="toast"></div>

<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script>
  const SUPABASE_URL = '__SUPABASE_URL__';
  const SUPABASE_ANON_KEY = '__SUPABASE_ANON_KEY__';
  const {{ createClient }} = supabase;
  const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  let currentUser = null;

  async function signIn() {{ await sb.auth.signInWithOAuth({{ provider: 'google' }}); }}
  async function signOut() {{ await sb.auth.signOut(); currentUser = null; updateAuthUI(null); }}

  function updateAuthUI(user) {{
    const st = document.getElementById('auth-status');
    const si = document.getElementById('sign-in-btn');
    const so = document.getElementById('sign-out-btn');
    if (user) {{
      st.textContent = user.email; si.style.display = 'none'; so.style.display = 'inline-block';
      loadVotes(user.id);
    }} else {{
      st.textContent = "Not signed in \u2014 votes won't be saved";
      si.style.display = 'inline-block'; so.style.display = 'none';
    }}
  }}

  sb.auth.onAuthStateChange(async (event, session) => {{
    currentUser = session?.user ?? null;
    updateAuthUI(currentUser);
    if (currentUser) {{
      await sb.from('users').upsert({{
        id: currentUser.id, email: currentUser.email,
        display_name: currentUser.user_metadata?.full_name ?? null,
      }}, {{ onConflict: 'id' }});
    }}
  }});

  async function loadVotes(userId) {{
    const {{ data }} = await sb.from('votes').select('story_url,vote').eq('user_id', userId);
    if (!data) return;
    data.forEach(row => {{
      const card = document.querySelector(`[data-url="${{row.story_url}}"]`);
      if (!card) return;
      if (row.vote === 1) card.querySelector('.vote-btn.up').classList.add('voted-up');
      if (row.vote === -1) card.querySelector('.vote-btn.down').classList.add('voted-down');
    }});
  }}

  async function vote(btn, storyUrl, value) {{
    if (!currentUser) {{ showToast('Sign in to save votes'); return; }}
    const card = btn.closest('.story-card');
    const title = card.querySelector('.story-title a')?.textContent ?? '';
    const topicSlug = card.closest('.topic-section')?.id ?? '';
    const domain = (() => {{ try {{ return new URL(storyUrl).hostname.replace('www.',''); }} catch(e) {{ return ''; }} }})();
    const up = card.querySelector('.vote-btn.up');
    const dn = card.querySelector('.vote-btn.down');
    const wasUp = up.classList.contains('voted-up');
    const wasDn = dn.classList.contains('voted-down');
    let newVote = value;
    if (value === 1 && wasUp) newVote = null;
    if (value === -1 && wasDn) newVote = null;
    up.classList.remove('voted-up'); dn.classList.remove('voted-down');
    if (newVote === null) {{
      await sb.from('votes').delete().eq('user_id', currentUser.id).eq('story_url', storyUrl);
      showToast('Vote removed');
    }} else {{
      if (newVote === 1) up.classList.add('voted-up');
      if (newVote === -1) dn.classList.add('voted-down');
      await sb.from('votes').upsert({{
        user_id: currentUser.id, story_url: storyUrl, story_title: title,
        topic_slug: topicSlug, source_domain: domain, vote: newVote,
      }}, {{ onConflict: 'user_id,story_url' }});
      showToast(newVote === 1 ? 'Upvoted' : 'Downvoted');
    }}
    const {{ data }} = await sb.from('votes').select('vote').eq('user_id', currentUser.id).eq('source_domain', domain);
    if (data?.length) {{
      const ups = data.filter(r => r.vote === 1).length;
      const w = parseFloat((0.1 + (ups/data.length)*1.9).toFixed(3));
      await sb.from('source_weights').upsert({{ user_id: currentUser.id, source_domain: domain, weight: w }}, {{ onConflict: 'user_id,source_domain' }});
    }}
  }}

  function showToast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2200);
  }}
</script>
</body>
</html>"""


# ─────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────

def main():
    print("=== The Lede: Fetch & Generate v3 ===")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("\n[1] Fetching stories...")
    stories_by_topic = fetch_all_stories()
    print("\n[2] Generating HTML...")
    page_html = generate_html(stories_by_topic)
    page_html = page_html.replace("__SUPABASE_URL__", SUPABASE_URL)
    page_html = page_html.replace("__SUPABASE_ANON_KEY__", os.environ.get("SUPABASE_ANON_KEY", ""))
    output_path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"\n[3] Written to {output_path}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
