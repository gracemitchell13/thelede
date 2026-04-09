# The Lede

A personal news dashboard in broadsheet newspaper style — built for people who read the same beats every day and want one place to do it.

**[→ Live app](https://gracemitchell13.github.io/thelede)**

## What it does

Pulls current stories from RSS feeds and NewsAPI across five curated beats: Civic Tech & GovTech, Housing Policy, Nonprofit & Grants, AI & Tech, and General News. Presents them in a front-page newspaper layout with feature stories, stacks, and briefs.

Signed-in users can upvote and downvote stories. Votes persist to a Supabase database and feed a source-weighting algorithm that adjusts how much each outlet influences your feed over time.

## Tech stack

- HTML / CSS / JavaScript (no framework)
- Python (feed fetching and story processing via `scripts/`)
- Supabase (Google OAuth, vote persistence, source weight storage)
- GitHub Actions (daily automated rebuild)
- Hosted on GitHub Pages

## How it works

A GitHub Action runs daily, triggering a Python script that fetches fresh stories from configured RSS feeds and the NewsAPI, processes and deduplicates them by section, and writes a new `index.html`. The result is a static page that always shows current news with no server required.

User votes are written to Supabase in real time. The source weighting logic recalculates a per-user weight for each outlet after every vote, biasing future feed rankings toward sources the user engages with positively.

## Setup

1. Clone the repo
2. Add your API keys as GitHub Actions secrets: `NEWS_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`
3. Update the Supabase project URL and anon key in `index.html`
4. Enable Google OAuth in your Supabase project
5. Push to main — GitHub Actions will build on schedule

## License

MIT — free to use, fork, and adapt.

Built by Grace Mitchell · [gracemitchellwriting.com](https://gracemitchellwriting.com)
