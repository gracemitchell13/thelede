# The Lede

A personal news dashboard in broadsheet newspaper style — built for people who read the same beats every day and want one place to do it.

**[→ Live app](https://gracemitchell13.github.io/thelede)**

## What it does

Pulls current stories from RSS feeds and NewsAPI across a set of configurable topic sections. Presents them in a front-page newspaper layout with feature stories, stacks, and briefs.

Signed-in users can upvote and downvote stories. Votes persist to a Supabase database and feed a source-weighting algorithm that adjusts how much each outlet influences your feed over time.

## Tech stack

- HTML / CSS / JavaScript (no framework)
- Python (feed fetching and story processing via `scripts/`)
- Supabase (Google OAuth, vote persistence, source weight storage)
- GitHub Actions (daily automated rebuild)
- Hosted on GitHub Pages

## How it works

A GitHub Action runs daily, triggering a Python script that fetches fresh stories from configured RSS feeds and the NewsAPI, processes and deduplicates them by section, and wr
