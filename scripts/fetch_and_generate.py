"""
The Lede — fetch_and_generate.py
Reads topic/source config from Supabase user settings.
Falls back to defaults if no user settings found.
"""

import os
import re
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from urllib.parse import urlparse
import html as html_lib

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
NEWSAPI_KEY = os.environ["NEWSAPI_KEY"]
NEWSAPI_BASE = "https://newsapi.org/v2/everything"
MAX_STORIES = 4
LOOKBACK_HOURS = 48

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ── SOURCE LABEL CLEANER ──────────────────────────────────────────────────────

SOURCE_LABELS = {
    "statescoop.com":"StateScoop","govtech.com":"GovTech","nextgov.com":"Nextgov",
    "fcw.com":"FCW","route-fifty.com":"Route Fifty","federalnewsnetwork.com":"Federal News Network",
    "govexec.com":"Government Executive","shelterforce.org":"Shelterforce",
    "housingwire.com":"HousingWire","nlihc.org":"NLIHC","strongtowns.org":"Strong Towns",
    "nextcity.org":"Next City","themarshallproject.org":"The Marshall Project",
    "prisonpolicy.org":"Prison Policy Initiative","theappeal.org":"The Appeal",
    "edsurge.com":"EdSurge","chalkbeat.org":"Chalkbeat","the74million.org":"The 74",
    "insidehighered.com":"Inside Higher Ed","healthaffairs.org":"Health Affairs",
    "kffhealthnews.org":"KFF Health News","statnews.com":"STAT News",
    "yaleclimateconnections.org":"Yale Climate Connections",
    "insideclimatenews.org":"Inside Climate News","grist.org":"Grist",
    "eenews.net":"E&E News","carbonbrief.org":"Carbon Brief",
    "immigrationimpact.com":"Immigration Impact","brookings.edu":"Brookings",
    "taxfoundation.org":"Tax Foundation","cbpp.org":"Center on Budget",
    "epi.org":"Economic Policy Institute","streetsblog.net":"Streetsblog",
    "smartcitiesdive.com":"Smart Cities Dive","masstransitmag.com":"Mass Transit",
    "brennancenter.org":"Brennan Center","thehill.com":"The Hill",
    "labornotes.org":"Labor Notes","inthesetimes.com":"In These Times",
    "disabilityscoop.com":"Disability Scoop","colorlines.com":"Colorlines",
    "nonprofit-quarterly.org":"Nonprofit Quarterly","nonprofitquarterly.org":"Nonprofit Quarterly",
    "candid.org":"Candid","ssir.org":"SSIR","insidephilanthropy.com":"Inside Philanthropy",
    "philanthropy.com":"Chronicle of Philanthropy","impactalpha.com":"Impact Alpha",
    "devex.com":"Devex","thenewhumanitarian.org":"The New Humanitarian",
    "technologyreview.com":"MIT Tech Review","theverge.com":"The Verge",
    "venturebeat.com":"VentureBeat","wired.com":"Wired","arstechnica.com":"Ars Technica",
    "krebsonsecurity.com":"Krebs on Security","therecord.media":"The Record",
    "darkreading.com":"Dark Reading","eff.org":"EFF","techcrunch.com":"TechCrunch",
    "github.blog":"GitHub Blog","iapp.org":"IAPP","medcitynews.com":"MedCity News",
    "niemanlab.org":"Nieman Lab","poynter.org":"Poynter","cjr.org":"Columbia Journalism Review",
    "variety.com":"Variety","hollywoodreporter.com":"The Hollywood Reporter",
    "deadline.com":"Deadline","podnews.net":"Podnews","politifact.com":"PolitiFact",
    "pensburgh.com":"PensBurgh","nhl.com":"NHL.com","sportsnet.ca":"Sportsnet",
    "post-gazette.com":"Pittsburgh Post-Gazette","theathletic.com":"The Athletic",
    "espn.com":"ESPN","bleacherreport.com":"Bleacher Report",
    "profootballtalk.nbcsports.com":"Pro Football Talk","baseballamerica.com":"Baseball America",
    "mlssoccer.com":"MLS Soccer","sportsbusinessjournal.com":"Sports Business Journal",
    "frontofficesports.com":"Front Office Sports","apnews.com":"AP News",
    "npr.org":"NPR","nytimes.com":"New York Times","washingtonpost.com":"Washington Post",
    "politico.com":"Politico","bbc.co.uk":"BBC News","theguardian.com":"The Guardian",
    "reuters.com":"Reuters","aljazeera.com":"Al Jazeera","foreignpolicy.com":"Foreign Policy",
    "foreignaffairs.com":"Foreign Affairs","thediplomat.com":"The Diplomat",
    "sciencedaily.com":"Science Daily","nature.com":"Nature","newscientist.com":"New Scientist",
    "scientificamerican.com":"Scientific American","ft.com":"Financial Times",
    "bloomberg.com":"Bloomberg","economist.com":"The Economist","wsj.com":"Wall Street Journal",
    "rollcall.com":"Roll Call","fivethirtyeight.com":"FiveThirtyEight",
    "mongabay.com":"Mongabay","e360.yale.edu":"Yale Environment 360",
    "civileats.com":"Civil Eats","modernfarmer.com":"Modern Farmer","thefern.org":"FERN",
    "space.com":"Space.com","nasa.gov":"NASA","spaceflightnow.com":"Spaceflight Now",
    "lithub.com":"Literary Hub","themillions.com":"The Millions",
    "publishersweekly.com":"Publishers Weekly","bookriot.com":"Book Riot",
    "nybooks.com":"NY Review of Books","rogerebert.com":"RogerEbert.com",
    "indiewire.com":"IndieWire","avclub.com":"The A.V. Club","vulture.com":"Vulture",
    "pitchfork.com":"Pitchfork","rollingstone.com":"Rolling Stone","stereogum.com":"Stereogum",
    "artforum.com":"Artforum","dezeen.com":"Dezeen","hyperallergic.com":"Hyperallergic",
    "artsy.net":"Artsy","americantheatre.org":"American Theatre","howlround.com":"HowlRound",
    "kotaku.com":"Kotaku","ign.com":"IGN","polygon.com":"Polygon",
    "rockpapershotgun.com":"Rock Paper Shotgun","eater.com":"Eater",
    "bonappetit.com":"Bon Appétit","food52.com":"Food52",
    "cntraveler.com":"Condé Nast Traveler","atlasobscura.com":"Atlas Obscura",
    "lonelyplanet.com":"Lonely Planet",
        "glaad.org":"GLAAD","19thnews.org":"The 19th",
    "rewirenewsgroup.com":"Rewire News","msmagazine.com":"Ms. Magazine",
    "them.us":"them.","nwlc.org":"NWLC",
}

def clean_label(source_label, domain):
    if domain in SOURCE_LABELS:
        return SOURCE_LABELS[domain]
    label = source_label or domain
    for suffix in [" - All Content"," - RSS"," | RSS"," Feed"," News"]:
        label = label.replace(suffix,"").replace(suffix.lower(),"")
    return label.strip() or domain

# ── FETCH HELPERS ─────────────────────────────────────────────────────────────

def get_domain(url):
    try: return urlparse(url).netloc.replace("www.","")
    except: return ""

def fetch_newsapi(query, domains=""):
    if not query: return []
    from_date = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"q":query,"from":from_date,"sortBy":"publishedAt",
              "language":"en","apiKey":NEWSAPI_KEY,"pageSize":10}
    if domains: params["domains"] = domains
    try:
        data = requests.get(NEWSAPI_BASE, params=params, timeout=10).json()
        return [{"title":a.get("title",""),"url":a.get("url",""),
                 "description":a.get("description","") or "",
                 "source_domain":get_domain(a.get("url","")),
                 "source_label":clean_label(a.get("source",{}).get("name",""), get_domain(a.get("url","")))}
                for a in data.get("articles",[])
                if a.get("title") and a.get("url") and "[Removed]" not in a.get("title","")]
    except Exception as e:
        print(f"  NewsAPI error: {e}"); return []

def fetch_rss(feed_url):
    try:
        feed = feedparser.parse(feed_url)
        out = []
        for e in feed.entries[:12]:
            if not e.get("link") or not e.get("title"): continue
            desc = re.sub(r"<[^>]+>","", e.get("summary","") or "")[:300]
            domain = get_domain(e["link"])
            out.append({"title":e["title"],"url":e["link"],"description":desc,
                        "source_domain":domain,
                        "source_label":clean_label(feed.feed.get("title",""), domain)})
        return out
    except Exception as e:
        print(f"  RSS error {feed_url}: {e}"); return []

# ── LOAD USER CONFIG FROM SUPABASE ────────────────────────────────────────────

def load_user_config():
    """
    Returns a list of topic dicts:
    [{ slug, label, queries, sources: [{domain, feed_url, label}] }]
    Ordered by sort_order. Only active topics and active sources.
    Uses the first user found (Phase 1 — single user page).
    """
    # Get first user
    users = supabase.table("users").select("id,email").limit(1).execute()
    if not users.data:
        print("  No users found — using empty config")
        return []

    user_id = users.data[0]["id"]
    print(f"  Building feed for: {users.data[0]['email']}")

    # Get active topics
    topics_resp = supabase.table("user_topics").select("*")\
        .eq("user_id", user_id).eq("active", True)\
        .order("sort_order").execute()

    # Get active sources
    sources_resp = supabase.table("user_sources").select("*")\
        .eq("user_id", user_id).eq("active", True).execute()

    # Group sources by topic_slug
    sources_by_topic = {}
    for s in (sources_resp.data or []):
        slug = s["topic_slug"]
        if slug not in sources_by_topic:
            sources_by_topic[slug] = []
        sources_by_topic[slug].append({
            "domain": s.get("domain",""),
            "feed_url": s.get("feed_url",""),
            "label": s.get("label",""),
        })

    # Build config
    config = []
    for t in (topics_resp.data or []):
        slug = t["slug"]
        queries = t.get("queries") or []
        # If queries is a string (shouldn't be but just in case), wrap it
        if isinstance(queries, str):
            queries = [queries]
        config.append({
            "slug": slug,
            "label": t["label"],
            "queries": queries,
            "sources": sources_by_topic.get(slug, []),
        })

    print(f"  {len(config)} active topics loaded from Supabase")
    return config

# ── FETCH ALL STORIES ─────────────────────────────────────────────────────────

def fetch_all(config):
    all_stories = {}
    seen = set()

    for topic in config:
        slug = topic["slug"]
        buckets = {}
        local_seen = set()

        def add_story(s, slug=slug):
            if s["url"] in seen or s["url"] in local_seen: return
            if not s.get("title"): return
            local_seen.add(s["url"])
            s["topic_slug"] = slug
            d = s["source_domain"] or "unknown"
            buckets.setdefault(d, []).append(s)

        # Strict topics use domain filter to avoid noise
        # Broad topics search all of NewsAPI for daily fresh content
        STRICT_SLUGS = {
            "penguins", "nhl", "nba", "nfl", "mlb", "soccer", "college-sports",
            "college-sports", "sports-business",
            "criminal-justice", "immigration", "disability-policy",
            "local-news", "podcasting", "newsletter-industry",
        }
        domains_str = ",".join(s["domain"] for s in topic["sources"] if s.get("domain"))
        use_domains = domains_str if slug in STRICT_SLUGS else ""

        for q in topic["queries"]:
            print(f"  NewsAPI [{slug}]: {q[:55]}")
            for s in fetch_newsapi(q, use_domains):
                add_story(s)

        # RSS feeds
        for src in topic["sources"]:
            if src.get("feed_url"):
                print(f"  RSS [{slug}]: {src['feed_url'][:60]}")
                for s in fetch_rss(src["feed_url"]):
                    add_story(s)

        # Round-robin across source buckets
        # Sports topics: max 1 per source to force variety
        SPORTS_SLUGS = {"penguins","nhl","nba","nfl","mlb","soccer","college-sports","sports-business"}
        max_per_src = MAX_STORIES if slug == "penguins" else (2 if slug in SPORTS_SLUGS else MAX_STORIES)
        stories = []
        bucket_lists = list(buckets.values())
        positions = [0] * len(bucket_lists)
        src_counts = [0] * len(bucket_lists)
        while len(stories) < MAX_STORIES:
            added = False
            for i, bucket in enumerate(bucket_lists):
                if len(stories) >= MAX_STORIES: break
                if positions[i] < len(bucket) and src_counts[i] < max_per_src:
                    stories.append(bucket[positions[i]])
                    positions[i] += 1
                    src_counts[i] += 1
                    added = True
            if not added: break

        for s in stories:
            seen.add(s["url"])

        all_stories[slug] = stories
        src_count = len(set(s["source_domain"] for s in stories))
        print(f"  [{slug}] {len(stories)} stories from {src_count} sources")

    return all_stories

# ── HTML GENERATION ───────────────────────────────────────────────────────────

def fmt_date():
    return datetime.now(timezone.utc).strftime("%A, %B %-d, %Y").upper()

def section(slug, label, stories):
    if not stories: return ""

    hero = stories[0]
    rest = stories[1:]

    h_title = html_lib.escape(hero.get("title",""))
    h_url   = html_lib.escape(hero.get("url",""))
    h_desc  = html_lib.escape(hero.get("description",""))[:320]
    h_src   = html_lib.escape(hero.get("source_label", hero.get("source_domain","")))
    h_du    = html_lib.escape(hero.get("url",""))
    h_desc_html = f'<p class="hero-desc">{h_desc}{"…" if len(h_desc)==320 else ""}</p>' if h_desc else ""

    secondary = ""
    for i, s in enumerate(rest):
        t   = html_lib.escape(s.get("title",""))
        u   = html_lib.escape(s.get("url",""))
        src = html_lib.escape(s.get("source_label", s.get("source_domain","")))
        du  = html_lib.escape(s.get("url",""))
        num = str(i+2).zfill(2)
        s_desc = html_lib.escape(s.get("description",""))[:200]
        s_desc_html = f'<p class="sec-desc">{s_desc}{"…" if len(s_desc)==200 else ""}</p>' if s_desc else ""
        secondary += f'''<article class="sec-item" data-url="{du}">
          <div class="sec-num">{num}</div>
          <div class="sec-body">
            <h3 class="sec-hed"><a href="{u}" target="_blank" rel="noopener">{t}</a></h3>
            {s_desc_html}
            <div class="sec-meta">
              <span class="src">{src}</span>
              <span class="votes">
                <button class="vb up" onclick="vote(this,'{du}',1)">▲</button>
                <button class="vb dn" onclick="vote(this,'{du}',-1)">▼</button>
              </span>
            </div>
          </div>
        </article>'''

    label_escaped = html_lib.escape(label)
    return f'''<section class="topic-sec" id="{slug}">
  <div class="sec-rule"><span class="sec-label">{label_escaped}</span></div>
  <article class="hero" data-url="{h_du}">
    <div class="hero-body">
      <h2 class="hero-hed"><a href="{h_url}" target="_blank" rel="noopener">{h_title}</a></h2>
      {h_desc_html}
      <div class="hero-meta">
        <span class="src">{h_src}</span>
        <span class="votes">
          <button class="vb up" onclick="vote(this,'{h_du}',1)">▲</button>
          <button class="vb dn" onclick="vote(this,'{h_du}',-1)">▼</button>
        </span>
      </div>
    </div>
  </article>
  <div class="sec-grid">{secondary}</div>
</section>'''

def page(config, stories_by_topic):
    date = fmt_date()
    # Only show sections that have stories, in user's preferred order
    secs = "\n".join(
        section(t["slug"], t["label"], stories_by_topic.get(t["slug"], []))
        for t in config
        if stories_by_topic.get(t["slug"])
    )
    nav = "\n".join(
        f'<a href="#{t["slug"]}">{html_lib.escape(t["label"])}</a>'
        for t in config
        if stories_by_topic.get(t["slug"])
    )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>The Lede — {date}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --blk:#0a0a0a;--ink:#1a1a1a;--mid:#555;--lt:#888;
  --rl:#1a1a1a;--rlt:#d0d0d0;--bg:#fff;--bg2:#f6f6f6;
  --serif:'Georgia','Times New Roman',serif;
  --sans:'Franklin Gothic Medium','Arial Narrow',Arial,sans-serif;
}}
body{{background:var(--bg);color:var(--ink);font-family:var(--serif);font-size:16px;line-height:1.5}}
a{{color:inherit;text-decoration:none}}
a:hover{{text-decoration:underline}}
.mast{{border-bottom:4px double var(--rl);padding:0 2rem}}
.mast-top{{display:flex;justify-content:space-between;padding:.5rem 0;
  border-bottom:1px solid var(--rlt);font-family:var(--sans);font-size:.65rem;
  letter-spacing:.12em;text-transform:uppercase;color:var(--lt)}}
.mast-title{{text-align:center;font-family:var(--serif);
  font-size:clamp(3.5rem,10vw,7rem);font-weight:900;
  letter-spacing:-.03em;line-height:1;padding:.4rem 0;color:var(--blk)}}
.mast-bot{{display:flex;justify-content:space-between;padding:.4rem 0;
  border-top:1px solid var(--rlt);font-family:var(--sans);font-size:.63rem;
  letter-spacing:.1em;text-transform:uppercase;color:var(--lt)}}
.auth{{display:flex;justify-content:flex-end;align-items:center;gap:.75rem;
  padding:.35rem 2rem;background:var(--bg2);border-bottom:1px solid var(--rlt);
  font-family:var(--sans);font-size:.7rem}}
#auth-st{{color:var(--lt)}}
#si-btn,#so-btn{{background:var(--blk);color:#fff;border:none;
  padding:.25rem .85rem;font-family:var(--sans);font-size:.67rem;
  letter-spacing:.06em;text-transform:uppercase;cursor:pointer}}
#si-btn:hover,#so-btn:hover{{background:var(--mid)}}
.nav{{background:var(--blk);display:flex;flex-wrap:nowrap;overflow-x:auto;padding:0 2rem;scrollbar-width:none}}
.nav::-webkit-scrollbar{{display:none}}
.nav a{{color:#fff;font-family:var(--sans);font-size:.67rem;letter-spacing:.12em;
  text-transform:uppercase;padding:.55rem 1rem;
  border-right:1px solid #2a2a2a;display:block}}
.nav a:first-child{{border-left:1px solid #2a2a2a}}
.nav a:hover{{background:#1e1e1e;text-decoration:none}}
.nav-settings{{margin-left:auto;border-left:1px solid #2a2a2a!important;border-right:none!important}}
main{{max-width:1100px;margin:0 auto;padding:0 2rem 3rem}}
.topic-sec{{padding:2rem 0 0;border-bottom:3px double var(--rl)}}
.topic-sec:last-child{{border-bottom:none}}
.sec-rule{{display:flex;align-items:center;gap:.75rem;margin-bottom:1.5rem}}
.sec-rule::before,.sec-rule::after{{content:'';flex:1;height:1px;background:var(--rl)}}
.sec-label{{font-family:var(--sans);font-size:.68rem;font-weight:700;
  letter-spacing:.22em;text-transform:uppercase;white-space:nowrap}}
.hero{{border-top:3px solid var(--accent,#c0392b);border-bottom:1px solid var(--rlt);
  padding:1.5rem 0 1.25rem;margin-bottom:0}}
#civic-tech .hero{{border-top-color:#2471a3}}
#housing-policy .hero{{border-top-color:#8e44ad}}
#criminal-justice .hero{{border-top-color:#c0392b}}
#education-policy .hero{{border-top-color:#16a085}}
#health-policy .hero{{border-top-color:#e67e22}}
#climate-policy .hero{{border-top-color:#27ae60}}
#nonprofit .hero{{border-top-color:#f39c12}}
#ai-tech .hero{{border-top-color:#6c3483}}
#penguins .hero{{border-top-color:#fcb514}}
#nhl .hero{{border-top-color:#1a1a2e}}
#racial-equity .hero{{border-top-color:#e74c3c}}
#gender-sexuality .hero{{border-top-color:#e91e8c}}
#politics .hero{{border-top-color:#c0392b}}
#science .hero{{border-top-color:#16a085}}
#books .hero{{border-top-color:#784212}}
#music .hero{{border-top-color:#c0392b}}
.hero-hed{{font-family:var(--serif);font-size:clamp(1.5rem,3vw,2.1rem);
  font-weight:800;line-height:1.15;color:var(--blk);margin-bottom:.6rem}}
.hero-desc{{font-size:.95rem;color:var(--mid);line-height:1.65;
  margin-bottom:.75rem}}
.hero-meta{{display:flex;justify-content:space-between;align-items:center;
  padding-top:.6rem;border-top:1px solid var(--rlt)}}
.sec-grid{{display:grid;grid-template-columns:repeat(3,1fr);
  border-left:1px solid var(--rlt);margin-bottom:2rem}}
.sec-item{{display:flex;gap:.75rem;padding:1rem;
  border-right:1px solid var(--rlt);border-bottom:1px solid var(--rlt)}}
.sec-num{{font-family:var(--sans);font-size:1.6rem;font-weight:700;
  color:#c0392b;line-height:1;min-width:2rem;padding-top:.1rem}}
#civic-tech .sec-num{{color:#2471a3}}
#housing-policy .sec-num{{color:#8e44ad}}
#criminal-justice .sec-num{{color:#c0392b}}
#education-policy .sec-num{{color:#16a085}}
#health-policy .sec-num{{color:#e67e22}}
#climate-policy .sec-num{{color:#27ae60}}
#immigration .sec-num{{color:#d35400}}
#economic-policy .sec-num{{color:#2980b9}}
#transportation .sec-num{{color:#7f8c8d}}
#voting-democracy .sec-num{{color:#8e44ad}}
#labor .sec-num{{color:#c0392b}}
#disability-policy .sec-num{{color:#16a085}}
#racial-equity .sec-num{{color:#e74c3c}}
#gender-sexuality .sec-num{{color:#e91e8c}}
#nonprofit .sec-num{{color:#f39c12}}
#community-development .sec-num{{color:#27ae60}}
#social-enterprise .sec-num{{color:#2ecc71}}
#international-development .sec-num{{color:#3498db}}
#ai-tech .sec-num{{color:#6c3483}}
#cybersecurity .sec-num{{color:#c0392b}}
#tech-policy .sec-num{{color:#2471a3}}
#startups .sec-num{{color:#f39c12}}
#healthtech .sec-num{{color:#16a085}}
#local-news .sec-num{{color:#2c3e50}}
#penguins .sec-num{{color:#fcb514}}
#nhl .sec-num{{color:#1a1a2e}}
#nba .sec-num{{color:#c9082a}}
#nfl .sec-num{{color:#013369}}
#mlb .sec-num{{color:#002d72}}
#soccer .sec-num{{color:#228b22}}
#us-news .sec-num{{color:#2c3e50}}
#world-news .sec-num{{color:#2471a3}}
#science .sec-num{{color:#16a085}}
#business .sec-num{{color:#1a5276}}
#politics .sec-num{{color:#c0392b}}
#health-wellness .sec-num{{color:#e67e22}}
#space .sec-num{{color:#6c3483}}
#books .sec-num{{color:#784212}}
#film-tv .sec-num{{color:#1a252f}}
#music .sec-num{{color:#c0392b}}
#food-culture .sec-num{{color:#ca6f1e}}
#travel .sec-num{{color:#148f77}}
.sec-body{{display:flex;flex-direction:column;gap:.35rem;flex:1}}
.sec-hed{{font-family:var(--serif);font-size:.95rem;font-weight:700;
  line-height:1.3;color:var(--blk)}}
.sec-desc{{font-size:.8rem;color:var(--mid);line-height:1.5;
  overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
.sec-meta{{display:flex;justify-content:space-between;align-items:center;
  margin-top:auto;padding-top:.35rem;border-top:1px solid var(--rlt)}}
.src{{font-family:var(--sans);font-size:.6rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--lt)}}
.votes{{display:flex;gap:2px}}
.vb{{background:var(--bg2);border:none;color:var(--lt);
  width:24px;height:24px;cursor:pointer;font-size:.58rem;
  display:flex;align-items:center;justify-content:center}}
.vb:hover{{background:var(--blk);color:#fff}}
.vb.voted-up{{background:#1a5c1a;color:#fff}}
.vb.voted-dn{{background:var(--blk);color:#fff}}
footer{{text-align:center;font-family:var(--sans);font-size:.63rem;
  letter-spacing:.12em;color:var(--lt);padding:2rem 1rem;
  border-top:1px solid var(--rlt);text-transform:uppercase}}
#toast{{position:fixed;bottom:1.5rem;right:1.5rem;background:var(--blk);
  color:#fff;font-family:var(--sans);font-size:.75rem;
  padding:.55rem 1.1rem;opacity:0;transition:opacity .25s;
  pointer-events:none;letter-spacing:.05em}}
#toast.show{{opacity:1}}
@media(max-width:700px){{
  .sec-grid{{grid-template-columns:1fr}}
  .nav{{overflow-x:auto;flex-wrap:nowrap;padding:0}}
  .mast,.auth{{padding-left:1rem;padding-right:1rem}}
  main{{padding:0 1rem 2rem}}
}}
</style>
</head>
<body>
<header class="mast">
  <div class="mast-top">
    <span>Est. 2026</span><span>readthelede.com</span><span>{date}</span>
  </div>
  <h1 class="mast-title">The Lede</h1>
</header>
<div class="auth">
  <span id="auth-st">Not signed in — votes won't be saved</span>
  <button id="si-btn" onclick="signIn()">Sign In with Google</button>
  <button id="so-btn" style="display:none" onclick="signOut()">Sign Out</button>
</div>
<nav class="nav">
  {nav}
  <a href="settings.html" class="nav-settings">⚙ Settings</a>
</nav>
<main>{secs}</main>
<footer>The Lede &mdash; {date} &mdash; readthelede.com</footer>
<div id="toast"></div>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script>
const SUPABASE_URL='__SUPABASE_URL__';
const SUPABASE_ANON_KEY='__SUPABASE_ANON_KEY__';
const {{createClient}}=supabase;
const sb=createClient(SUPABASE_URL,SUPABASE_ANON_KEY);
let user=null;
async function signIn(){{await sb.auth.signInWithOAuth({{provider:'google',
  options:{{redirectTo:'https://gracemitchell13.github.io/thelede/settings.html'}}}});}}
async function signOut(){{await sb.auth.signOut();user=null;updateUI(null);}}
function updateUI(u){{
  const st=document.getElementById('auth-st');
  const si=document.getElementById('si-btn');
  const so=document.getElementById('so-btn');
  if(u){{st.textContent=u.email;
    si.style.display='none';so.style.display='inline-block';loadVotes(u.id);}}
  else{{st.textContent="Not signed in \u2014 votes won't be saved";mu.textContent='';
    si.style.display='inline-block';so.style.display='none';}}
}}
sb.auth.onAuthStateChange(async(ev,session)=>{{
  user=session?.user??null;updateUI(user);
  if(user)await sb.from('users').upsert({{id:user.id,email:user.email,
    display_name:user.user_metadata?.full_name??null}},{{onConflict:'id'}});
}});
async function loadVotes(uid){{
  const {{data}}=await sb.from('votes').select('story_url,vote').eq('user_id',uid);
  if(!data)return;
  data.forEach(r=>{{
    const c=document.querySelector(`[data-url="${{r.story_url}}"]`);
    if(!c)return;
    if(r.vote===1)c.querySelector('.vb.up').classList.add('voted-up');
    if(r.vote===-1)c.querySelector('.vb.dn').classList.add('voted-dn');
  }});
}}
async function vote(btn,url,val){{
  if(!user){{toast('Sign in to save votes');return;}}
  const c=btn.closest('[data-url]');
  const title=c.querySelector('h2,h3')?.textContent??'';
  const topic=c.closest('.topic-sec')?.id??'';
  const domain=(()=>{{try{{return new URL(url).hostname.replace('www.','');}}catch(e){{return'';}}}} )();
  const up=c.querySelector('.vb.up');
  const dn=c.querySelector('.vb.dn');
  const wasUp=up.classList.contains('voted-up');
  const wasDn=dn.classList.contains('voted-dn');
  let v=val;
  if(val===1&&wasUp)v=null;
  if(val===-1&&wasDn)v=null;
  up.classList.remove('voted-up');dn.classList.remove('voted-dn');
  if(v===null){{
    await sb.from('votes').delete().eq('user_id',user.id).eq('story_url',url);
    toast('Vote removed');
  }}else{{
    if(v===1)up.classList.add('voted-up');
    if(v===-1)dn.classList.add('voted-dn');
    await sb.from('votes').upsert({{user_id:user.id,story_url:url,story_title:title,
      topic_slug:topic,source_domain:domain,vote:v}},{{onConflict:'user_id,story_url'}});
    toast(v===1?'Upvoted':'Downvoted');
  }}
  const {{data}}=await sb.from('votes').select('vote').eq('user_id',user.id).eq('source_domain',domain);
  if(data?.length){{
    const w=parseFloat((0.1+(data.filter(r=>r.vote===1).length/data.length)*1.9).toFixed(3));
    await sb.from('source_weights').upsert({{user_id:user.id,source_domain:domain,weight:w}},
      {{onConflict:'user_id,source_domain'}});
  }}
}}
function toast(msg){{
  const t=document.getElementById('toast');
  t.textContent=msg;t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2200);
}}
</script>
</body>
</html>'''

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=== The Lede ===")
    print(f"Run: {datetime.now(timezone.utc).isoformat()}")

    print("\n[1] Loading user config from Supabase...")
    config = load_user_config()

    if not config:
        print("  No config found — nothing to generate")
        return

    print(f"\n[2] Fetching stories for {len(config)} topics...")
    stories_by_topic = fetch_all(config)

    print("\n[3] Generating HTML...")
    html = page(config, stories_by_topic)
    html = html.replace("__SUPABASE_URL__", SUPABASE_URL)
    html = html.replace("__SUPABASE_ANON_KEY__", os.environ.get("SUPABASE_ANON_KEY",""))

    out = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[4] Written to {out}")
    print("=== Done ===")

if __name__ == "__main__":
    main()
