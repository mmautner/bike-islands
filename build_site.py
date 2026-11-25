"""Build the static site into dist/<base>/ (base from site/config.json).

    python3 build_site.py

Reads data/map_strict.json and data/map_standard.json (from pipeline/export.py). Writes:
  index.html              the map page (site/template.html with the data inlined)
  methodology/index.html  sources and methods (site/methodology.html)
  img/                    quiz photos (site/img/, not in git)
Head tags, the maxmautner.com header and the footer are shared, as in ../san-mateo-speeds.
The 1200x630 preview image (og/index.png) is drawn by site/og/make_og.py, which deploy.sh runs.
"""
import datetime
import html
import json
import os
import shutil
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "site", "config.json")))
BASE = "/" + CFG["base"].strip("/") + "/"
OUT = os.path.join(HERE, "dist", BASE.strip("/"))
DATA = {t: json.load(open(os.path.join(HERE, "data", f"map_{t}.json"))) for t in ("strict", "standard")}
e = html.escape


def headline_share():
    """Same number the page's title computes: strict standard, San Mateo station, both cities."""
    ok = near = 0
    for v in DATA["strict"]["islands"].values():
        near += (v.get("near") or {}).get("San Mateo", 0)
        ok += (v.get("ok") or {}).get("San Mateo", 0)
    return round(near / ok)


TITLE = "Find your bike island: San Mateo and Burlingame"
DESCRIPTION = (f"Only 1 in {headline_share()} homes within 2 miles of San Mateo's Caltrain station has a bike route "
               "there that feels safe for kids and cautious riders. Click near home to see your island and the fixes "
               "that would connect it.")

# the same header as maxmautner.com and the speeds and crashes pages
HEADER = """<header role="banner">
  <a href="/" class="site-title">Max Mautner</a>
  <nav role="navigation"><ul>
    <li><a href="/writing/">Essays</a></li>
    <li><a href="/about/">About</a></li>
    <li><a href="/subscribe/" class="nav-button">Subscribe</a></li>
    <li><button class="dark-mode-toggle" id="darkModeToggle" aria-label="Toggle dark mode">
      <svg class="icon-sun" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
      <svg class="icon-moon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
    </button></li>
  </ul></nav>
</header>
<script>(function(){var t=document.getElementById('darkModeToggle'),r=document.documentElement;t.addEventListener('click',function(){var d=r.getAttribute('data-theme')!=='dark';r.setAttribute('data-theme',d?'dark':'light');try{localStorage.setItem('theme',d?'dark':'light')}catch(e){}});})();</script>"""


def analytics():
    key = CFG.get("google_analytics_key")
    if not key:
        return ""
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={key}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{key}');
  </script>"""


def head(title, description, path):
    page_url = f"{CFG['site_url']}{path}"
    img = f"{CFG['site_url']}{BASE}og/index.png"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script>(function(){{var s=null;try{{s=localStorage.getItem('theme')}}catch(e){{}}var r=document.documentElement;r.setAttribute('data-theme',s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'));}})();</script>
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{e(page_url)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Max Mautner">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(page_url)}">
  <meta property="og:image" content="{e(img)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{e(description)}">
  <meta name="twitter:card" content="summary_large_image">
  {analytics()}
  <link rel="icon" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{CFG['site_css']}">"""


def footer():
    issue = "mailto:" + CFG["contact_email"] + "?" + urllib.parse.urlencode(
        {"subject": "Possible error: bike islands map"}, quote_via=urllib.parse.quote)
    updated = datetime.date.fromisoformat(CFG["updated"])
    return f"""<footer class="bi-foot">
  <p>Streets: OpenStreetMap contributors. Speed limits: City of San Mateo 2026 speed survey, obtained through a public records request. Homes: 2020 Census. <a href="{BASE}methodology/">How this was made</a>.</p>
  <p>Made by <a href="/about/">Max Mautner</a>. <a href="{e(CFG['repo_url'])}">The data and code are public</a>, so anyone can check how each number was reached. <a href="{e(issue)}">Report an error</a>.</p>
  <p>Updated {updated.strftime('%B')} {updated.day}, {updated.year}.</p>
</footer>"""


METHOD_CSS = """<style>
  main.bi { max-width: 720px; margin: 0 auto; padding: 0 20px 40px; font-family: var(--font-sans); color: var(--text-2); }
  main.bi > header { margin-bottom: 18px; }
  .bi-method h1 { font-family: var(--font-serif); color: var(--text); }
  .bi-method ul { padding-left: 22px; }
  .bi-method h2 { font-family: var(--font-serif); font-weight: 600; color: var(--text); font-size: 22px; margin: 28px 0 8px; }
  .bi-method p, .bi-method li { font-size: 16px; line-height: 1.6; }
  .bi-method a { color: var(--accent); }
  .bi-eyebrow { font-size: 13px; margin: 0; }
  footer.bi-foot { font-size: 13px; color: var(--text-3); margin-top: 32px; line-height: 1.5; }
  footer.bi-foot a { color: inherit; }
</style>"""


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "methodology"))
    page = open(os.path.join(HERE, "site", "template.html")).read()
    page = (page.replace("/*HEAD*/", head(TITLE, DESCRIPTION, BASE))
                .replace("/*HEADER*/", HEADER)
                .replace("/*FOOTER*/", footer())
                .replace("/*DATA*/", json.dumps(DATA, separators=(",", ":")))
                .replace("/*FETCHED*/", json.dumps(CFG["osm_fetched"])))
    open(os.path.join(OUT, "index.html"), "w").write(page)

    method = open(os.path.join(HERE, "site", "methodology.html")).read()
    method = (method.replace("/*BASE*/", BASE).replace("/*FETCHED*/", e(CFG["osm_fetched"]))
                    .replace("/*FOOTER*/", footer()))
    mtitle = "How the bike islands map was made"
    open(os.path.join(OUT, "methodology", "index.html"), "w").write(
        head(mtitle, "Sources and methods for the bike islands map of San Mateo and Burlingame.", f"{BASE}methodology/")
        + "\n" + METHOD_CSS + "\n</head>\n<body>\n<main role=\"main\" class=\"bi\">\n" + HEADER + "\n" + method
        + "\n</main>\n</body>\n</html>\n")

    img = os.path.join(HERE, "site", "img")
    if os.path.isdir(img):
        shutil.copytree(img, os.path.join(OUT, "img"))
    print(f"built index and methodology into {OUT} ({os.path.getsize(os.path.join(OUT, 'index.html')) / 1e6:.1f} MB page)")


if __name__ == "__main__":
    main()
