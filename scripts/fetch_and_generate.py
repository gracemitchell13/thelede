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
LOOKBACK_HOURS = 48  # fetch stories from last 48 hours

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ─────────────────────────────────────
# TOPIC DEFINITIONS
# ─────────────────────────────────────

TOPICS = {
    "civic-tech": {
        "label": "Civic Tech & GovTech",
        "icon": "🏛️",
        "newsapi_queries": ["civic tech", "govtech", "government digital services", "smartcities government"],
        "rss_feeds": [
            "https://statescoop.com/feed/",
            "https://www.govtech.com/rss.xml",
            "https://federalnewsnetwork.com/feed/",
        ],
    },
    "housing": {
        "label": "Housing Policy",
        "icon": "🏘️",
        "newsapi_queries": ["affordable housing policy", "housing crisis", "zoning reform", "homelessness policy"],
        "rss_feeds": [
            "https://shelterforce.org/feed/",
            "https://nlihc.org/feed",
            "https://www.housingwire.com/feed/",
        ],
    },
    "nonprofit": {
        "label": "Nonprofit & Grants",
        "icon": "🤝",
        "newsapi_queries": ["nonprofit sector", "grant funding", "philanthropy", "foundation grants"],
        "rss_feeds": [
            "https://www.philanthropy.com/feed",
            "https://blog.candid.org/feed/",
        ],
    },
    "ai-tech": {
        "label": "AI & Tech",
        "icon": "🤖",
        "newsapi_queries": ["artificial intelligence policy", "machine learning", "AI regulation", "large language models"],
        "rss_feeds": [
            "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            "https://www.technologyreview.com/feed/",
        ],
    },
    "penguins": {
        "label": "Pittsburgh Penguins",
        "icon": "🐧",
        "newsapi_queries": ["Pittsburgh Penguins NHL"],
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


def fetch_newsapi(query: str) -> list[dict]:
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


def fetch_rss(feed_url: str) -> list[dict]:
    try:
        feed = feedparser.parse(feed_url)
        stories = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        for entry in feed.entries[:15]:
            url = entry.get("link", "")
            title = entry.get("title", "")
            description = entry.get("summary", "") or ""
            # Strip HTML from description
            import re
            description = re.sub(r"<[^>]+>", "", description)[:300]
            published = entry.get("published", "") or entry.get("updated", "")
            if not url or not title:
                continue
            stories.append({
                "title": title,
                "url": url,
                "description": description,
                "source_domain": get_domain(url),
                "published_at": published,
                "source_label": feed.feed.get("title", get_domain(feed_url)),
            })
        return stories
    except Exception as e:
        print(f"  RSS error for {feed_url}: {e}")
        return []


# ─────────────────────────────────────
# SCORING
# ─────────────────────────────────────

def build_weight_maps(user_ids: list[str]) -> dict:
    """
    Returns { user_id: { 'topics': {slug: weight}, 'sources': {domain: weight} } }
    """
    weight_maps = {uid: {"topics": {}, "sources": {}} for uid in user_ids}

    # Topic preferences
    prefs = supabase.table("preferences").select("*").in_("user_id", user_ids).execute()
    for row in prefs.data:
        uid = row["user_id"]
        weight_maps[uid]["topics"][row["topic_slug"]] = float(row["weight"])

    # Source weights
    sw = supabase.table("source_weights").select("*").in_("user_id", user_ids).execute()
    for row in sw.data:
        uid = row["user_id"]
        weight_maps[uid]["sources"][row["source_domain"]] = float(row["weight"])

    # Compute source weights from recent votes if not already set
    votes = supabase.table("votes").select("*").in_("user_id", user_ids).execute()
    vote_counts = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # uid -> domain -> [ups, downs]
    for row in votes.data:
        uid = row["user_id"]
        domain = row.get("source_domain", "")
        if domain:
            if row["vote"] == 1:
                vote_counts[uid][domain][0] += 1
            else:
                vote_counts[uid][domain][1] += 1

    for uid, domains in vote_counts.items():
        for domain, (ups, downs) in domains.items():
            total = ups + downs
            if total > 0:
                # Simple Wilson-like score: baseline 1.0, range 0.1–2.0
                ratio = ups / total
                weight = 0.1 + (ratio * 1.9)
                weight_maps[uid]["sources"][domain] = round(weight, 3)

    return weight_maps


def score_story(story: dict, topic_slug: str, topic_weight: float, source_weight: float) -> float:
    """Score a story for a user. Higher is better."""
    base = 1.0
    score = base * topic_weight * source_weight
    return round(score, 4)


# ─────────────────────────────────────
# MAIN FETCH + SCORE
# ─────────────────────────────────────

def fetch_all_stories() -> dict[str, list[dict]]:
    """Returns { topic_slug: [story, ...] } with deduplication."""
    all_stories = {}
    seen_urls = set()

    for slug, topic in TOPICS.items():
        stories = []

        # NewsAPI
        for query in topic["newsapi_queries"]:
            print(f"  NewsAPI: {query}")
            fetched = fetch_newsapi(query)
            for s in fetched:
                if s["url"] not in seen_urls:
                    seen_urls.add(s["url"])
                    s["topic_slug"] = slug
                    stories.append(s)

        # RSS
        for feed_url in topic["rss_feeds"]:
            print(f"  RSS: {feed_url}")
            fetched = fetch_rss(feed_url)
            for s in fetched:
                if s["url"] not in seen_urls:
                    seen_urls.add(s["url"])
                    s["topic_slug"] = slug
                    stories.append(s)

        all_stories[slug] = stories
        print(f"  [{slug}] {len(stories)} stories fetched")

    return all_stories


def get_all_users() -> list[dict]:
    result = supabase.table("users").select("id, email, display_name").execute()
    return result.data


def score_and_rank(stories: list[dict], topic_slug: str, weight_map: dict) -> list[dict]:
    topic_weight = weight_map["topics"].get(topic_slug, 1.0)
    scored = []
    for story in stories:
        source_weight = weight_map["sources"].get(story["source_domain"], 1.0)
        story["score"] = score_story(story, topic_slug, topic_weight, source_weight)
        scored.append(story)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:MAX_STORIES_PER_TOPIC]


# ─────────────────────────────────────
# HTML GENERATION
# ─────────────────────────────────────

def format_date() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%A, %B %-d, %Y").upper()


def story_card(story: dict) -> str:
    title = html_lib.escape(story.get("title", ""))
    url = html_lib.escape(story.get("url", ""))
    description = html_lib.escape(story.get("description", ""))[:200]
    source = html_lib.escape(story.get("source_label", story.get("source_domain", "")))
    story_url_escaped = html_lib.escape(story.get("url", ""))

    return f"""
    <article class="story-card" data-url="{story_url_escaped}">
      <h3 class="story-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
      {'<p class="story-desc">' + description + ('…' if len(description) == 200 else '') + '</p>' if description else ''}
      <div class="story-meta">
        <span class="source-label">{source}</span>
        <div class="vote-buttons">
          <button class="vote-btn up" onclick="vote(this, '{story_url_escaped}', 1)" title="Upvote">▲</button>
          <button class="vote-btn down" onclick="vote(this, '{story_url_escaped}', -1)" title="Downvote">▼</button>
        </div>
      </div>
    </article>"""


def topic_section(slug: str, stories: list[dict]) -> str:
    topic = TOPICS[slug]
    label = topic["label"]
    icon = topic["icon"]
    cards = "\n".join(story_card(s) for s in stories)
    return f"""
  <section class="topic-section" id="{slug}">
    <h2 class="topic-header">{icon} {label}</h2>
    <div class="stories-grid">
      {cards}
    </div>
  </section>"""


def generate_html(stories_by_topic: dict[str, list[dict]]) -> str:
    date_str = format_date()
    sections = "\n".join(
        topic_section(slug, stories)
        for slug, stories in stories_by_topic.items()
        if stories
    )

    # Nav links
    nav_links = " | ".join(
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
    /* ── RESET ── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    /* ── TOKENS ── */
    :root {{
      --ink:        #1a1a1a;
      --ink-light:  #444;
      --rule:       #1a1a1a;
      --rule-light: #ccc;
      --paper:      #f5f0e8;
      --paper-dark: #ede8de;
      --accent:     #8b0000;
      --font-serif: 'Georgia', 'Times New Roman', serif;
      --font-sans:  'Franklin Gothic Medium', 'Arial Narrow', Arial, sans-serif;
      --font-mono:  'Courier New', monospace;
    }}

    /* ── BASE ── */
    body {{
      background: var(--paper);
      color: var(--ink);
      font-family: var(--font-serif);
      font-size: 16px;
      line-height: 1.5;
    }}

    a {{ color: var(--ink); text-decoration: none; }}
    a:hover {{ color: var(--accent); text-decoration: underline; }}

    /* ── MASTHEAD ── */
    .masthead {{
      text-align: center;
      border-bottom: 4px double var(--rule);
      padding: 1.5rem 1rem 1rem;
      background: var(--paper);
    }}
    .masthead-tagline {{
      font-family: var(--font-sans);
      font-size: 0.7rem;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--ink-light);
      margin-bottom: 0.25rem;
    }}
    .masthead-title {{
      font-family: var(--font-serif);
      font-size: clamp(3rem, 8vw, 6rem);
      font-weight: 900;
      letter-spacing: -0.02em;
      line-height: 1;
      color: var(--ink);
    }}
    .masthead-date {{
      font-family: var(--font-sans);
      font-size: 0.7rem;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--ink-light);
      margin-top: 0.4rem;
      padding-top: 0.4rem;
      border-top: 1px solid var(--rule-light);
    }}

    /* ── SECTION NAV ── */
    .section-nav {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 0 1rem;
      padding: 0.5rem 1rem;
      background: var(--ink);
      color: #f5f0e8;
      font-family: var(--font-sans);
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .section-nav a {{
      color: #f5f0e8;
      padding: 0.2rem 0;
    }}
    .section-nav a:hover {{ color: #ccc; text-decoration: none; border-bottom: 1px solid #ccc; }}

    /* ── AUTH BAR ── */
    .auth-bar {{
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 1.5rem;
      background: var(--paper-dark);
      border-bottom: 1px solid var(--rule-light);
      font-family: var(--font-sans);
      font-size: 0.75rem;
    }}
    #auth-status {{ color: var(--ink-light); }}
    #sign-in-btn, #sign-out-btn {{
      background: var(--ink);
      color: var(--paper);
      border: none;
      padding: 0.25rem 0.75rem;
      font-family: var(--font-sans);
      font-size: 0.72rem;
      cursor: pointer;
      letter-spacing: 0.05em;
    }}
    #sign-in-btn:hover, #sign-out-btn:hover {{ background: var(--accent); }}

    /* ── MAIN LAYOUT ── */
    main {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 1.5rem 1rem;
    }}

    /* ── TOPIC SECTIONS ── */
    .topic-section {{
      margin-bottom: 2.5rem;
      padding-bottom: 2rem;
      border-bottom: 3px double var(--rule);
    }}
    .topic-section:last-child {{ border-bottom: none; }}

    .topic-header {{
      font-family: var(--font-sans);
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--paper);
      background: var(--ink);
      padding: 0.35rem 0.75rem;
      margin-bottom: 1.25rem;
      display: inline-block;
    }}

    /* ── STORIES GRID ── */
    .stories-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1.25rem;
    }}

    /* ── STORY CARD ── */
    .story-card {{
      background: var(--paper);
      border: 1px solid var(--rule-light);
      border-top: 3px solid var(--ink);
      padding: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    .story-title {{
      font-family: var(--font-serif);
      font-size: 1.0rem;
      font-weight: 700;
      line-height: 1.3;
    }}
    .story-desc {{
      font-size: 0.85rem;
      color: var(--ink-light);
      line-height: 1.5;
      flex: 1;
    }}
    .story-meta {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid var(--rule-light);
      padding-top: 0.5rem;
      margin-top: auto;
    }}
    .source-label {{
      font-family: var(--font-sans);
      font-size: 0.68rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--ink-light);
    }}

    /* ── VOTE BUTTONS ── */
    .vote-buttons {{ display: flex; gap: 0.25rem; }}
    .vote-btn {{
      background: none;
      border: 1px solid var(--rule-light);
      color: var(--ink-light);
      width: 28px;
      height: 28px;
      cursor: pointer;
      font-size: 0.7rem;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s;
    }}
    .vote-btn:hover {{ background: var(--ink); color: var(--paper); border-color: var(--ink); }}
    .vote-btn.voted-up {{ background: #2d6a2d; color: white; border-color: #2d6a2d; }}
    .vote-btn.voted-down {{ background: var(--accent); color: white; border-color: var(--accent); }}

    /* ── FOOTER ── */
    footer {{
      text-align: center;
      font-family: var(--font-sans);
      font-size: 0.7rem;
      letter-spacing: 0.1em;
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
      background: var(--ink);
      color: var(--paper);
      font-family: var(--font-sans);
      font-size: 0.8rem;
      padding: 0.6rem 1.2rem;
      opacity: 0;
      transition: opacity 0.3s;
      pointer-events: none;
    }}
    #toast.show {{ opacity: 1; }}
  </style>
</head>
<body>

  <!-- MASTHEAD -->
  <header class="masthead">
    <p class="masthead-tagline">Your daily curated briefing</p>
    <h1 class="masthead-title">The Lede</h1>
    <p class="masthead-date">{date_str}</p>
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

  <!-- MAIN CONTENT -->
  <main>
    {sections}
  </main>

  <footer>
    The Lede &mdash; Generated {date_str} &mdash; Powered by NewsAPI &amp; RSS
  </footer>

  <div id="toast"></div>

  <!-- SUPABASE JS -->
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <script>
    // ── CONFIG ──
    const SUPABASE_URL = '__SUPABASE_URL__';
    const SUPABASE_ANON_KEY = '__SUPABASE_ANON_KEY__';
    const {{ createClient }} = supabase;
    const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    let currentUser = null;

    // ── AUTH ──
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

    // ── VOTES ──
    async function loadVotes(userId) {{
      const {{ data }} = await sb.from('votes').select('story_url, vote').eq('user_id', userId);
      if (!data) return;
      data.forEach(row => {{
        const card = document.querySelector(`[data-url="${{row.story_url}}"]`);
        if (!card) return;
        const up = card.querySelector('.vote-btn.up');
        const down = card.querySelector('.vote-btn.down');
        if (row.vote === 1) up.classList.add('voted-up');
        if (row.vote === -1) down.classList.add('voted-down');
      }});
    }}

    async function vote(btn, storyUrl, value) {{
      if (!currentUser) {{
        showToast('Sign in to save your votes');
        return;
      }}

      const card = btn.closest('.story-card');
      const title = card.querySelector('.story-title a')?.textContent ?? '';
      const topicSection = card.closest('.topic-section');
      const topicSlug = topicSection?.id ?? '';
      const sourceDomain = new URL(storyUrl).hostname.replace('www.', '');

      // Toggle logic
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
          user_id: currentUser.id,
          story_url: storyUrl,
          story_title: title,
          topic_slug: topicSlug,
          source_domain: sourceDomain,
          vote: newVote,
        }}, {{ onConflict: 'user_id,story_url' }});
        showToast(newVote === 1 ? 'Upvoted — this source gets a boost tomorrow' : 'Downvoted — this source gets suppressed tomorrow');
      }}

      await updateSourceWeight(currentUser.id, sourceDomain);
    }}

    async function updateSourceWeight(userId, domain) {{
      const {{ data }} = await sb.from('votes')
        .select('vote')
        .eq('user_id', userId)
        .eq('source_domain', domain);
      if (!data || data.length === 0) return;
      const ups = data.filter(r => r.vote === 1).length;
      const total = data.length;
      const weight = parseFloat((0.1 + (ups / total) * 1.9).toFixed(3));
      await sb.from('source_weights').upsert({{
        user_id: userId,
        source_domain: domain,
        weight,
      }}, {{ onConflict: 'user_id,source_domain' }});
    }}

    // ── TOAST ──
    function showToast(msg) {{
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 2500);
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

    # Fetch all stories
    print("\n[1] Fetching stories...")
    raw_stories = fetch_all_stories()

    # For now: generate a single page (Phase 1 — solo/template mode)
    # When we go multi-user hosted, this becomes per-user generation
    print("\n[2] Building default page (no user scoring yet)...")
    stories_by_topic = {
        slug: stories[:MAX_STORIES_PER_TOPIC]
        for slug, stories in raw_stories.items()
    }

    # Inject Supabase config into HTML
    print("\n[3] Generating HTML...")
    page_html = generate_html(stories_by_topic)
    page_html = page_html.replace("__SUPABASE_URL__", SUPABASE_URL)
    # Note: we use the anon key in the HTML (safe for client-side)
    # The service key never touches the HTML
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    page_html = page_html.replace("__SUPABASE_ANON_KEY__", anon_key)

    # Write output
    output_path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"\n[4] Written to {output_path}")
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
