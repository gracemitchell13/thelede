"""
The Lede — fetch_and_generate.py v6 — Magazine layout
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
MAX_STORIES = 7
LOOKBACK_HOURS = 48

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

TOPICS = {
    "civic-tech": {
        "label": "Civic Tech & GovTech",
        "queries": ['"civic tech" OR "govtech" OR "government technology"',
                    '"digital government" OR "government software" OR "public sector technology"'],
        "domains": "statescoop.com,govtech.com,nextgov.com,federalnewsnetwork.com,route-fifty.com",
        "feeds":   ["https://statescoop.com/feed/", "https://www.govtech.com/rss.xml"],
    },
    "housing": {
        "label": "Housing Policy",
        "queries": ['"affordable housing" OR "housing policy" OR "zoning reform"',
                    '"housing crisis" OR "homelessness" OR "rent control"'],
        "domains": "shelterforce.org,housingwire.com,nlihc.org",
        "feeds":   ["https://shelterforce.org/feed/", "https://www.housingwire.com/feed/"],
    },
    "nonprofit": {
        "label": "Nonprofit & Grants",
        "queries": ['"nonprofit" AND ("grant" OR "funding" OR "philanthropy")',
                    '"foundation" AND ("awards grant" OR "social impact")'],
        "domains": "philanthropy.com,nonprofitquarterly.org,candid.org",
        "feeds":   ["https://nonprofitquarterly.org/feed/", "https://blog.candid.org/feed/"],
    },
    "ai-tech": {
        "label": "AI & Tech",
        "queries": ['"artificial intelligence" AND ("policy" OR "regulation" OR "governance")',
                    '"large language model" OR "generative AI" OR "AI ethics"'],
        "domains": "technologyreview.com,wired.com,theverge.com,arstechnica.com",
        "feeds":   ["https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
                    "https://www.technologyreview.com/feed/"],
    },
    "penguins": {
        "label": "Pittsburgh Penguins",
        "queries": ['"Pittsburgh Penguins"'],
        "domains": "nhl.com,pensburgh.com,post-gazette.com",
        "feeds":   ["https://www.pensburgh.com/rss/current"],
    },
    "general": {
        "label": "General News",
        "queries": [],
        "domains": "",
        "feeds":   ["https://feeds.bbci.co.uk/news/rss.xml",
                    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"],
    },
}

def get_domain(url):
    try: return urlparse(url).netloc.replace("www.", "")
    except: return ""

def fetch_newsapi(query, domains=""):
    if not query: return []
    from_date = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"q": query, "from": from_date, "sortBy": "publishedAt",
              "language": "en", "apiKey": NEWSAPI_KEY, "pageSize": 10}
    if domains: params["domains"] = domains
    try:
        data = requests.get(NEWSAPI_BASE, params=params, timeout=10).json()
        return [{"title": a.get("title",""), "url": a.get("url",""),
                 "description": a.get("description","") or "",
                 "source_domain": get_domain(a.get("url","")),
                 "source_label": a.get("source",{}).get("name","")}
                for a in data.get("articles",[])
                if a.get("title") and a.get("url") and "[Removed]" not in a.get("title","")]
    except Exception as e:
        print(f"  NewsAPI error: {e}"); return []

def fetch_rss(url):
    try:
        feed = feedparser.parse(url)
        out = []
        for e in feed.entries[:12]:
            if not e.get("link") or not e.get("title"): continue
            desc = re.sub(r"<[^>]+>", "", e.get("summary","") or "")[:300]
            out.append({"title": e["title"], "url": e["link"], "description": desc,
                        "source_domain": get_domain(e["link"]),
                        "source_label": feed.feed.get("title", get_domain(url))})
        return out
    except Exception as e:
        print(f"  RSS error {url}: {e}"); return []

MAX_PER_SOURCE = 2  # max stories from any single domain per section

def fetch_all():
    all_stories, seen = {}, set()
    for slug, topic in TOPICS.items():
        stories = []
        source_counts = {}
        for q in topic["queries"]:
            for s in fetch_newsapi(q, topic["domains"]):
                d = s["source_domain"]
                if s["url"] not in seen and source_counts.get(d, 0) < MAX_PER_SOURCE:
                    seen.add(s["url"]); s["topic_slug"] = slug
                    source_counts[d] = source_counts.get(d, 0) + 1
                    stories.append(s)
        for feed_url in topic["feeds"]:
            for s in fetch_rss(feed_url):
                d = s["source_domain"]
                if s["url"] not in seen and source_counts.get(d, 0) < MAX_PER_SOURCE:
                    seen.add(s["url"]); s["topic_slug"] = slug
                    source_counts[d] = source_counts.get(d, 0) + 1
                    stories.append(s)
        all_stories[slug] = stories[:MAX_STORIES]
        print(f"  [{slug}] {len(all_stories[slug])} stories from {len(source_counts)} sources")
    return all_stories

def fmt_date():
    return datetime.now(timezone.utc).strftime("%A, %B %-d, %Y").upper()

def section(slug, stories):
    if not stories: return ""
    label = html_lib.escape(TOPICS[slug]["label"])
    hero = stories[0]
    rest = stories[1:]

    h_title = html_lib.escape(hero.get("title",""))
    h_url   = html_lib.escape(hero.get("url",""))
    h_desc  = html_lib.escape(hero.get("description",""))[:320]
    h_src   = html_lib.escape(hero.get("source_label", hero.get("source_domain","")))
    h_du    = html_lib.escape(hero.get("url",""))
    h_desc_str = f'<p class="hero-desc">{h_desc}{"…" if len(h_desc)==320 else ""}</p>' if h_desc else ""

    secondary = ""
    for i, s in enumerate(rest):
        t   = html_lib.escape(s.get("title",""))
        u   = html_lib.escape(s.get("url",""))
        src = html_lib.escape(s.get("source_label", s.get("source_domain","")))
        du  = html_lib.escape(s.get("url",""))
        num = str(i + 2).zfill(2)
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

    return f'''<section class="topic-sec" id="{slug}">
  <div class="sec-rule"><span class="sec-label">{label}</span></div>
  <article class="hero" data-url="{h_du}">
    <div class="hero-body">
      <h2 class="hero-hed"><a href="{h_url}" target="_blank" rel="noopener">{h_title}</a></h2>
      {h_desc_str}
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

def page(stories_by_topic):
    date = fmt_date()
    secs = "\n".join(section(slug, st) for slug, st in stories_by_topic.items() if st)
    nav  = "\n".join(f'<a href="#{s}">{TOPICS[s]["label"]}</a>'
                     for s in stories_by_topic if stories_by_topic[s])
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

.nav{{background:var(--blk);display:flex;flex-wrap:wrap;padding:0 2rem}}
.nav a{{color:#fff;font-family:var(--sans);font-size:.67rem;letter-spacing:.12em;
  text-transform:uppercase;padding:.55rem 1rem;
  border-right:1px solid #2a2a2a;display:block}}
.nav a:first-child{{border-left:1px solid #2a2a2a}}
.nav a:hover{{background:#1e1e1e;text-decoration:none}}

main{{max-width:1100px;margin:0 auto;padding:0 2rem 3rem}}

.topic-sec{{padding:2rem 0 0;border-bottom:3px double var(--rl)}}
.topic-sec:last-child{{border-bottom:none}}

.sec-rule{{display:flex;align-items:center;gap:.75rem;margin-bottom:1.5rem}}
.sec-rule::before,.sec-rule::after{{content:'';flex:1;height:1px;background:var(--rl)}}
.sec-label{{font-family:var(--sans);font-size:.68rem;font-weight:700;
  letter-spacing:.22em;text-transform:uppercase;white-space:nowrap}}

/* HERO */
.hero{{border-top:2px solid var(--blk);border-bottom:1px solid var(--rlt);
  padding:1.5rem 0 1.25rem;margin-bottom:0}}
.hero-hed{{font-family:var(--serif);font-size:clamp(1.5rem,3vw,2.1rem);
  font-weight:800;line-height:1.15;color:var(--blk);margin-bottom:.6rem}}
.hero-desc{{font-size:.95rem;color:var(--mid);line-height:1.65;
  max-width:72ch;margin-bottom:.75rem}}
.hero-meta{{display:flex;justify-content:space-between;align-items:center;
  padding-top:.6rem;border-top:1px solid var(--rlt)}}

/* SECONDARY GRID */
.sec-grid{{display:grid;grid-template-columns:repeat(3,1fr);
  border-left:1px solid var(--rlt);margin-bottom:2rem}}
.sec-item{{display:flex;gap:.75rem;padding:1rem;
  border-right:1px solid var(--rlt);border-bottom:1px solid var(--rlt)}}
.sec-item:nth-child(3n+1){{border-left:none}}
.sec-num{{font-family:var(--sans);font-size:1.6rem;font-weight:700;
  line-height:1;min-width:2rem;padding-top:.1rem}}
.sec-body{{display:flex;flex-direction:column;gap:.35rem;flex:1}}
.sec-hed{{font-family:var(--serif);font-size:.95rem;font-weight:700;
  line-height:1.3;color:var(--blk)}}
.sec-desc{{font-size:.8rem;color:var(--mid);line-height:1.5;
  overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
#civic-tech .sec-num{{color:#1a6b3c}}
#housing .sec-num{{color:#7b2d8b}}
#nonprofit .sec-num{{color:#c45c1a}}
#ai-tech .sec-num{{color:#1a4fa0}}
#penguins .sec-num{{color:#c4a01a}}
#general .sec-num{{color:#8b1a1a}}
.sec-meta{{display:flex;justify-content:space-between;align-items:center;
  margin-top:auto;padding-top:.35rem;border-top:1px solid var(--rlt)}}

/* SHARED */
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
    <span>Est. 2026</span><span>{date}</span><span>Your Daily Briefing</span>
  </div>
  <h1 class="mast-title">The Lede</h1>
  <div class="mast-bot">
    <span>Civic Tech &bull; Housing &bull; Nonprofits &bull; AI &bull; Penguins</span>
    <span>readthelede.com</span>
  </div>
</header>
<div class="auth">
  <span id="auth-st">Not signed in — votes won't be saved</span>
  <button id="si-btn" onclick="signIn()">Sign In with Google</button>
  <button id="so-btn" style="display:none" onclick="signOut()">Sign Out</button>
</div>
<nav class="nav">{nav}</nav>
<main>{secs}</main>
<footer>The Lede &mdash; {date} &mdash; Powered by NewsAPI &amp; RSS</footer>
<div id="toast"></div>

<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script>
const SUPABASE_URL='__SUPABASE_URL__';
const SUPABASE_ANON_KEY='__SUPABASE_ANON_KEY__';
const {{createClient}}=supabase;
const sb=createClient(SUPABASE_URL,SUPABASE_ANON_KEY);
let user=null;

async function signIn(){{await sb.auth.signInWithOAuth({{provider:'google'}});}}
async function signOut(){{await sb.auth.signOut();user=null;updateUI(null);}}

function updateUI(u){{
  const st=document.getElementById('auth-st');
  const si=document.getElementById('si-btn');
  const so=document.getElementById('so-btn');
  if(u){{st.textContent=u.email;si.style.display='none';so.style.display='inline-block';loadVotes(u.id);}}
  else{{st.textContent="Not signed in \u2014 votes won't be saved";si.style.display='inline-block';so.style.display='none';}}
}}

sb.auth.onAuthStateChange(async(ev,session)=>{{
  user=session?.user??null;updateUI(user);
  if(user) await sb.from('users').upsert({{id:user.id,email:user.email,
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

def main():
    print("=== The Lede v6 ===")
    print(f"Run: {datetime.now(timezone.utc).isoformat()}")
    print("\n[1] Fetching...")
    stories = fetch_all()
    print("\n[2] Generating HTML...")
    html = page(stories)
    html = html.replace("__SUPABASE_URL__", SUPABASE_URL)
    html = html.replace("__SUPABASE_ANON_KEY__", os.environ.get("SUPABASE_ANON_KEY",""))
    out = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[3] Written to {out}")
    print("=== Done ===")

if __name__ == "__main__":
    main()
