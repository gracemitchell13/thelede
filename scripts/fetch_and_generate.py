"""
The Lede — fetch_and_generate.py
Runs via GitHub Actions daily. Fetches news, scores by user preferences
and vote history, generates a newspaper-style HTML page.
"""

import os
import json
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
MAX_STORIES_PER_TOPIC = 8
LOOKBACK_HOURS = 48

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ─────────────────────────────────────
# TOPIC DEFINITIONS
# ─────────────────────────────────────

TOPICS = {
    "civic-tech": {
        "label": "Civic Tech & GovTech",
        "icon": "🏛️",
        "newsapi_queries": ["civic technology government", "govtech digital government services", "code for america"],
        "rss_feeds": [
            "https://statescoop.com/feed/",
            "https://www.govtech.com/rss.xml",
            "https://federalnewsnetwork.com/feed/",
        ],
    },
    "housing": {
        "label": "Housing Policy",
        "icon": "🏘️",
        "newsapi_queries": ["affordable housing policy", "housing crisis zoning", "homelessness policy government"],
        "rss_feeds": [
            "https://shelterforce.org/feed/",
            "https://nlihc.org/feed",
            "https://www.housingwire.com/feed/",
        ],
    },
    "nonprofit": {
        "label": "Nonprofit & Grants",
        "icon": "🤝",
        "newsapi_queries": ["nonprofit sector funding", "foundation grant awards", "philanthropy social impact"],
        "rss_feeds": [
            "https://www.philanthropy.com/feed",
            "https://blog.candid.org/feed/",
        ],
    },
    "ai-tech": {
        "label": "AI & Tech",
        "icon": "🤖",
        "newsapi_queries": ["artificial intelligence policy regulation", "large language models research", "AI ethics governance"],
        "rss_feeds": [
            "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            "https://www.technologyreview.com/feed/",
        ],
    },
    "penguins": {
        "label": "Pittsburgh Penguins",
        "icon": "🐧",
        "newsapi_queries": ["Pittsburgh Penguins NHL hockey"],
        "rss_feeds": [
            "https://www.pensburgh.com/rss/current",
            "https://www.nhl.com/penguins/rss/news.xml",
        ],
    },
    "general": {
        "label": "General News",
        "icon": "📰",
        "newsapi_queries": [],
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


def fetch_newsapi(query: str) -> list:
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
        import re
        feed = feedparser.parse(feed_url)
        stories = []
        for entry in feed.entries[:15]:
            url = entry.get("link", "")
            title = entry.get("title", "")
            description = entry.get("summary", "") or ""
            description = re.sub(r"<[^>]+>", "", description)[:300]
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


# ─────────────────────────────────────
# FETCH ALL
# ─────────────────────────────────────

def fetch_all_stories() -> dict:
    all_stories = {}
    seen_urls = set()

    for slug, topic in TOPICS.items():
        stories = []

        for query in topic["newsapi_queries"]:
            print(f"  NewsAPI: {query}")
            for s in fetch_newsapi(query):
                if s["url"] not in seen_urls:
                    seen_urls.add(s["url"])
                    s["topic_slug"] = slug
                    stories.append(s)

        for feed_url in topic["rss_feeds"]:
            print(f"  RSS: {feed_url}")
            for s in fetch_rss(feed_url):
                if s["url"] not in seen_urls:
                    seen_urls.add(s["url"])
                    s["topic_slug"] = slug
                    stories.append(s)

        all_stories[slug] = stories
        print(f"  [{slug}] {len(stories)} stories fetched")

    return all_stories


# ─────────────────────────────────────
# HTML GENERATION
# ─────────────────────────────────────

def format_date() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%A, %B %-d, %Y").upper()


def story_card(story: dict, featured: bool = False) -> str:
    title = html_lib.escape(story.get("title", ""))
    url = html_lib.escape(story.get("url", ""))
    description = html_lib.escape(story.get("description", ""))[:280]
    source = html_lib.escape(story.get("source_label", story.get("source_domain", "")))
    story_url_escaped = html_lib.escape(story.get("url", ""))
    card_class = "story-card featured" if featured else "story-card"

    return f"""
    <article class="{card_class}" data-url="{story_url_escaped}">
      <h3 class="story-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
      {'<p class="story-desc">' + description + ('…' if len(description) == 280 else '') + '</p>' if description else ''}
      <div class="story-meta">
        <span class="source-label">{source}</span>
        <div class="vote-buttons">
          <button class="vote-btn up" onclick="vote(this, '{story_url_escaped}', 1)" title="Upvote">▲</button>
          <button class="vote-btn down" onclick="vote(this, '{story_url_escaped}', -1)" title="Downvote">▼</button>
        </div>
      </div>
    </article>"""


def topic_section(slug: str, stories: list) -> str:
    topic = TOPICS[slug]
    label = topic["label"]
    cards_html = ""
    for i, s in enumerate(stories):
        cards_html += story_card(s, featured=(i == 0))
    return f"""
  <section class="topic-section" id="{slug}">
    <div class="topic-header-row">
      <h2 class="topic-header">{label}</h2>
    </div>
    <div class="stories-grid">
      {cards_html}
    </div>
  </section>"""


def generate_html(stories_by_topic: dict) -> str:
    date_str = format_date()
    sections = "\n".join(
        topic_section(slug, stories)
        for slug, stories in stories_by_topic.items()
        if stories
    )

    nav_links = "\n".join(
        f'<a href="#{slug}">{TOPICS[slug]["label"]}</a>'
        for slug in stories_by_topic
        if stories_by_topic[slug]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>The Lede — {date_str}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --black:      #0a0a0a;
      --ink:        #1a1a1a;
      --ink-mid:    #444;
      --ink-light:  #777;
      --rule:       #1a1a1a;
      --rule-light: #d0d0d0;
      --gray-100:   #f7f7f7;
      --gray-200:   #eeeeee;
      --gray-800:   #222222;
      --white:      #ffffff;
      --font-serif: 'Georgia', 'Times New Roman', serif;
      --font-sans:  'Franklin Gothic Medium', 'Arial Narrow', Arial, sans-serif;
    }}

    body {{
      background: var(--white);
      color: var(--ink);
      font-family: var(--font-serif);
      font-size: 16px;
      line-height: 1.5;
    }}

    a {{ color: inherit; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* ── MASTHEAD ── */
    .masthead {{
      border-bottom: 1px solid var(--rule);
      padding: 0 1.5rem;
      background: var(--white);
    }}
    .masthead-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--rule-light);
      font-family: var(--font-sans);
      font-size: 0.68rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--ink-light);
    }}
    .masthead-title {{
      text-align: center;
      font-family: var(--font-serif);
      font-size: clamp(3.5rem, 10vw, 7rem);
      font-weight: 900;
      letter-spacing: -0.03em;
      line-height: 1;
      padding: 0.5rem 0 0.4rem;
      color: var(--black);
    }}
    .masthead-bottom {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.4rem 0;
      border-top: 1px solid var(--rule-light);
      font-family: var(--font-sans);
      font-size: 0.65rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--ink-light);
    }}
    .masthead-rule {{
      border: none;
      border-top: 4px double var(--rule);
      margin: 0;
    }}

    /* ── AUTH BAR ── */
    .auth-bar {{
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 0.75rem;
      padding: 0.35rem 1.5rem;
      background: var(--gray-100);
      border-bottom: 1px solid var(--rule-light);
      font-family: var(--font-sans);
      font-size: 0.72rem;
    }}
    #auth-status {{ color: var(--ink-light); }}
    #sign-in-btn, #sign-out-btn {{
      background: var(--black);
      color: var(--white);
      border: none;
      padding: 0.25rem 0.8rem;
      font-family: var(--font-sans);
      font-size: 0.68rem;
      letter-spacing: 0.05em;
      cursor: pointer;
      text-transform: uppercase;
    }}
    #sign-in-btn:hover, #sign-out-btn:hover {{ background: var(--ink-mid); }}

    /* ── SECTION NAV ── */
    .section-nav {{
      background: var(--black);
      padding: 0 1.5rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0;
    }}
    .section-nav a {{
      color: var(--white);
      font-family: var(--font-sans);
      font-size: 0.68rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      padding: 0.55rem 1rem;
      border-right: 1px solid #333;
      display: block;
    }}
    .section-nav a:first-child {{ border-left: 1px solid #333; }}
    .section-nav a:hover {{ background: #222; text-decoration: none; }}

    /* ── MAIN ── */
    main {{
      max-width: 1260px;
      margin: 0 auto;
      padding: 0 1.5rem 3rem;
    }}

    /* ── TOPIC SECTIONS ── */
    .topic-section {{
      padding: 1.75rem 0 1.5rem;
      border-bottom: 3px double var(--rule);
    }}
    .topic-section:last-child {{ border-bottom: none; }}

    .topic-header-row {{
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.25rem;
    }}
    .topic-header-row::before,
    .topic-header-row::after {{
      content: '';
      flex: 1;
      height: 1px;
      background: var(--rule);
    }}
    .topic-header {{
      font-family: var(--font-sans);
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.25em;
      text-transform: uppercase;
      color: var(--black);
      white-space: nowrap;
      padding: 0 0.5rem;
    }}

    /* ── STORIES GRID — newspaper layout ── */
    .stories-grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 0;
      border-top: 2px solid var(--rule);
      border-left: 1px solid var(--rule-light);
    }}

    /* featured card: spans 5 cols, full height of first row */
    .story-card.featured {{
      grid-column: span 5;
      grid-row: span 2;
      border-right: 1px solid var(--rule-light);
      border-bottom: 1px solid var(--rule-light);
      padding: 1.25rem 1.25rem 1rem;
    }}
    .story-card.featured .story-title {{
      font-size: 1.5rem;
      line-height: 1.2;
      margin-bottom: 0.6rem;
    }}
    .story-card.featured .story-desc {{
      font-size: 0.9rem;
      line-height: 1.6;
      -webkit-line-clamp: 6;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    /* secondary cards: span 3-4 cols */
    .story-card:not(.featured):nth-child(2),
    .story-card:not(.featured):nth-child(3) {{
      grid-column: span 4;
    }}
    .story-card:not(.featured):nth-child(4),
    .story-card:not(.featured):nth-child(5) {{
      grid-column: span 3;
    }}
    .story-card:not(.featured):nth-child(n+6) {{
      grid-column: span 4;
    }}

    /* base card */
    .story-card {{
      padding: 1rem 1rem 0.85rem;
      border-right: 1px solid var(--rule-light);
      border-bottom: 1px solid var(--rule-light);
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      background: var(--white);
    }}
    .story-card:hover {{ background: var(--gray-100); }}

    .story-title {{
      font-family: var(--font-serif);
      font-size: 0.95rem;
      font-weight: 700;
      line-height: 1.3;
      color: var(--black);
    }}
    .story-title a:hover {{ text-decoration: underline; }}

    .story-desc {{
      font-size: 0.8rem;
      color: var(--ink-mid);
      line-height: 1.5;
      flex: 1;
      -webkit-line-clamp: 3;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .story-meta {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid var(--rule-light);
      padding-top: 0.45rem;
      margin-top: auto;
    }}
    .source-label {{
      font-family: var(--font-sans);
      font-size: 0.62rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--ink-light);
    }}

    /* ── VOTE BUTTONS ── */
    .vote-buttons {{ display: flex; gap: 2px; }}
    .vote-btn {{
      background: var(--gray-200);
      border: none;
      color: var(--ink-light);
      width: 24px;
      height: 24px;
      cursor: pointer;
      font-size: 0.6rem;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.1s;
    }}
    .vote-btn:hover {{ background: var(--gray-800); color: var(--white); }}
    .vote-btn.voted-up {{ background: #1a5c1a; color: white; }}
    .vote-btn.voted-down {{ background: var(--black); color: white; }}

    /* ── FOOTER ── */
    footer {{
      text-align: center;
      font-family: var(--font-sans);
      font-size: 0.65rem;
      letter-spacing: 0.12em;
      color: var(--ink-light);
      padding: 2rem 1rem;
      border-top: 1px solid var(--rule-light);
      text-transform: uppercase;
    }}

    /* ── TOAST ── */
    #toast {{
      position: fixed;
      bottom: 1.5rem;
      right: 1.5rem;
      background: var(--black);
      color: var(--white);
      font-family: var(--font-sans);
      font-size: 0.78rem;
      padding: 0.6rem 1.2rem;
      opacity: 0;
      transition: opacity 0.3s;
      pointer-events: none;
      letter-spacing: 0.05em;
    }}
    #toast.show {{ opacity: 1; }}

    /* ── RESPONSIVE ── */
    @media (max-width: 768px) {{
      .story-card.featured,
      .story-card:not(.featured):nth-child(n) {{
        grid-column: span 12;
      }}
      .masthead-title {{ font-size: 3rem; }}
      .section-nav {{ overflow-x: auto; flex-wrap: nowrap; }}
    }}
  </style>
</head>
<body>

  <!-- MASTHEAD -->
  <header class="masthead">
    <div class="masthead-top">
      <span>Est. 2026</span>
      <span>{date_str}</span>
      <span>Your Daily Briefing</span>
    </div>
    <h1 class="masthead-title">The Lede</h1>
    <div class="masthead-bottom">
      <span>Civic Tech &bull; Housing &bull; Nonprofits &bull; AI &bull; Penguins</span>
      <span id="auth-status-top"></span>
    </div>
    <hr class="masthead-rule" />
  </header>

  <!-- AUTH BAR -->
  <div class="auth-bar">
    <span id="auth-status">Not signed in — votes won't be saved</span>
    <button id="sign-in-btn" onclick="signIn()">Sign In with Google</button>
    <button id="sign-out-btn" style="display:none" onclick="signOut()">Sign Out</button>
  </div>

  <!-- SECTION NAV -->
  <nav class="section-nav" aria-label="Sections">
    {nav_links}
  </nav>

  <!-- MAIN -->
  <main>
    {sections}
  </main>

  <footer>
    The Lede &mdash; {date_str} &mdash; Powered by NewsAPI &amp; RSS
  </footer>

  <div id="toast"></div>

  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <script>
    const SUPABASE_URL = '__SUPABASE_URL__';
    const SUPABASE_ANON_KEY = '__SUPABASE_ANON_KEY__';
    const {{ createClient }} = supabase;
    const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    let currentUser = null;

    async function signIn() {{
      await sb.auth.signInWithOAuth({{ provider: 'google' }});
    }}
    async function signOut() {{
      await sb.auth.signOut();
      currentUser = null;
      updateAuthUI(null);
    }}

    function updateAuthUI(user) {{
      const status = document.getElementById('auth-status');
      const signInBtn = document.getElementById('sign-in-btn');
      const signOutBtn = document.getElementById('sign-out-btn');
      if (user) {{
        status.textContent = user.email;
        signInBtn.style.display = 'none';
        signOutBtn.style.display = 'inline-block';
        loadVotes(user.id);
      }} else {{
        status.textContent = 'Not signed in — votes won\\'t be saved';
        signInBtn.style.display = 'inline-block';
        signOutBtn.style.display = 'none';
      }}
    }}

    sb.auth.onAuthStateChange(async (event, session) => {{
      currentUser = session?.user ?? null;
      updateAuthUI(currentUser);
      if (currentUser) await ensureUser(currentUser);
    }});

    async function ensureUser(user) {{
      await sb.from('users').upsert({{
        id: user.id,
        email: user.email,
        display_name: user.user_metadata?.full_name ?? null,
      }}, {{ onConflict: 'id' }});
    }}

    async function loadVotes(userId) {{
      const {{ data }} = await sb.from('votes').select('story_url, vote').eq('user_id', userId);
      if (!data) return;
      data.forEach(row => {{
        const card = document.querySelector(`[data-url="${{row.story_url}}"]`);
        if (!card) return;
        if (row.vote === 1) card.querySelector('.vote-btn.up').classList.add('voted-up');
        if (row.vote === -1) card.querySelector('.vote-btn.down').classList.add('voted-down');
      }});
    }}

    async function vote(btn, storyUrl, value) {{
      if (!currentUser) {{ showToast('Sign in to save your votes'); return; }}
      const card = btn.closest('.story-card');
      const title = card.querySelector('.story-title a')?.textContent ?? '';
      const topicSlug = card.closest('.topic-section')?.id ?? '';
      const sourceDomain = (() => {{ try {{ return new URL(storyUrl).hostname.replace('www.',''); }} catch(e) {{ return ''; }} }})();
      const upBtn = card.querySelector('.vote-btn.up');
      const downBtn = card.querySelector('.vote-btn.down');
      const alreadyUp = upBtn.classList.contains('voted-up');
      const alreadyDown = downBtn.classList.contains('voted-down');
      let newVote = value;
      if (value === 1 && alreadyUp) newVote = null;
      if (value === -1 && alreadyDown) newVote = null;
      upBtn.classList.remove('voted-up');
      downBtn.classList.remove('voted-down');
      if (newVote === null) {{
        await sb.from('votes').delete().eq('user_id', currentUser.id).eq('story_url', storyUrl);
        showToast('Vote removed');
      }} else {{
        if (newVote === 1) upBtn.classList.add('voted-up');
        if (newVote === -1) downBtn.classList.add('voted-down');
        await sb.from('votes').upsert({{
          user_id: currentUser.id, story_url: storyUrl, story_title: title,
          topic_slug: topicSlug, source_domain: sourceDomain, vote: newVote,
        }}, {{ onConflict: 'user_id,story_url' }});
        showToast(newVote === 1 ? 'Upvoted' : 'Downvoted');
      }}
      await updateSourceWeight(currentUser.id, sourceDomain);
    }}

    async function updateSourceWeight(userId, domain) {{
      const {{ data }} = await sb.from('votes').select('vote').eq('user_id', userId).eq('source_domain', domain);
      if (!data || !data.length) return;
      const ups = data.filter(r => r.vote === 1).length;
      const weight = parseFloat((0.1 + (ups / data.length) * 1.9).toFixed(3));
      await sb.from('source_weights').upsert({{
        user_id: userId, source_domain: domain, weight,
      }}, {{ onConflict: 'user_id,source_domain' }});
    }}

    function showToast(msg) {{
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 2200);
    }}
  </script>
</body>
</html>"""


# ─────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────

def main():
    print("=== The Lede: Fetch & Generate ===")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")

    print("\n[1] Fetching stories...")
    raw_stories = fetch_all_stories()

    print("\n[2] Building page...")
    stories_by_topic = {
        slug: stories[:MAX_STORIES_PER_TOPIC]
        for slug, stories in raw_stories.items()
    }

    print("\n[3] Generating HTML...")
    page_html = generate_html(stories_by_topic)
    page_html = page_html.replace("__SUPABASE_URL__", SUPABASE_URL)
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    page_html = page_html.replace("__SUPABASE_ANON_KEY__", anon_key)

    output_path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"\n[4] Written to {output_path}")
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
