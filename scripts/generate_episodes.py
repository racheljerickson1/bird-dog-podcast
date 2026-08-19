#!/usr/bin/env python3
"""
generate_episodes.py
--------------------
Checks the Buzzsprout RSS feed for new episodes and generates a full HTML page
for any episode that doesn't already have one.  Also updates episodes.html and
sitemap.xml.  Safe to run repeatedly — never overwrites existing pages.

Usage:
    python3 scripts/generate_episodes.py

Dependencies: standard library only (xml.etree, urllib, re, os, json, time)
"""

import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date

# ── Config ────────────────────────────────────────────────────────────────────
RSS_URL      = 'https://feeds.buzzsprout.com/2157578.rss'
BASE_URL     = 'https://thebirddogpodcast.com'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPISODES_DIR = os.path.join(PROJECT_ROOT, 'episodes')
IMAGES_DIR   = os.path.join(PROJECT_ROOT, 'images')

NS = {
    'itunes':  'http://www.itunes.com/dtds/podcast-1.0.dtd',
    'podcast': 'https://podcastindex.org/namespace/1.0',
}

BOILERPLATE_CUTOFFS = [
    r'Products\s*&\s*Resources',
    r'Have a Question',
    r'Training\s*&\s*Breeding',
    r'Follow Along',
    r'Thanks for listening',
    r'Become a supporter',
    r'Support the show',
]

SKIP_RESOURCE_HOSTS = (
    'buzzsprout.com', 'apple.com', 'spotify.com', 'thebirddogpodcast.com',
    'gunshyfix.com', 'kuranda.com', 'nuvet.com', 'utahbirddogtraining.com',
    'fieldbredgoldenretrievers.com', 'utahpointinglabs.com',
)

STANDARD_RESOURCES = [
    ('https://www.gunshyfix.com', 'The Gunshy Fix', 'Sound conditioning program for gunshy dogs.'),
    ('https://kuranda.com/?partner=26722&amp;utm_medium=affiliate&amp;utm_campaign=KurandaPartnerProgram&amp;utm_source=partners.kuranda.com', 'Kuranda Dog Beds', 'Elevated, chew-proof dog beds built for working dogs.'),
    ('https://www.nuvet.com/56496', 'NuVet', 'Cold-pressed supplements for optimal dog health.'),
    ('https://www.utahbirddogtraining.com', 'Utah Bird Dog Training', "Tyce's professional training services."),
    ('https://www.fieldbredgoldenretrievers.com', 'Field Bred Golden Retrievers', "Tyce and Rachel's golden retriever breeding program."),
    ('https://www.utahpointinglabs.com', 'Utah Pointing Labs', "Tyce's pointing lab breeding program."),
]

FILLER = re.compile(r'\b(um+|uh+|hmm+|mhm+|uh-huh)\b', re.I)

GA_SNIPPET = '''    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-MCTGSD7MPC"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-MCTGSD7MPC');
    </script>'''

FOOTER_HTML = '''    <footer class="site-footer">
      <div class="footer-inner">
        <p class="footer-brand">The Bird Dog Podcast</p>
        <ul class="footer-links">
          <li><a href="../episodes.html">Episodes</a></li>
          <li><a href="../partners.html">Partners</a></li>
          <li><a href="../about.html">About</a></li>
          <li><a href="../contact.html">Contact</a></li>
        </ul>
        <div class="footer-social-row">
          <a href="https://www.instagram.com/thebirddogpodcast/" target="_blank" rel="noopener" class="footer-social-link" aria-label="Instagram">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg>
            Instagram
          </a>
        </div>
        <p class="footer-copy">&copy; 2026 The Bird Dog Podcast with Tyce Erickson. All rights reserved.</p>
      </div>
    </footer>'''


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def unescape(text):
    return (text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                .replace('&nbsp;', ' ').replace('&apos;', "'").replace('&#39;', "'")
                .replace('&quot;', '"'))


def clean_title(raw, ep_num=None):
    """Strip duplicated Ep. N prefixes from Buzzsprout titles."""
    t = re.sub(r'^\s*\(?\s*Ep\.?\s*\d+\s*\)?\s*[:.\-]?\s*', '', raw or '', flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip()
    return t or (raw or f'Episode {ep_num}')


def guess_guest_name(title):
    """If the title ends with '& First Last', use that as the guest speaker label."""
    m = re.search(r'&\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\s*$', title or '')
    if m:
        return m.group(1).strip()
    return None


def clean_description(raw_html):
    """Return episode-only paragraphs, cutting off the standard RSS partner boilerplate."""
    parts = re.findall(r'<p[^>]*>(.*?)</p>', raw_html or '', flags=re.I | re.S)
    if not parts:
        text = unescape(re.sub(r'<[^>]+>', ' ', raw_html or ''))
        text = re.sub(r'\s+', ' ', text).strip()
        return [text] if text else []

    paras = []
    for p in parts:
        text = unescape(re.sub(r'<[^>]+>', ' ', p))
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            continue
        if any(re.search(pat, text, re.I) for pat in BOILERPLATE_CUTOFFS):
            break
        if re.fullmatch(r'https?://\S+', text) or text.lower().startswith('website:'):
            continue
        paras.append(text)
    return paras


def extract_resources(raw_html):
    """Pull unique episode-specific hrefs from the RSS HTML (not partner boilerplate)."""
    hrefs = re.findall(r'''href=['"]([^'"]+)['"]''', raw_html or '')
    resources, seen = [], set()
    for u in hrefs:
        u = unescape(u).strip()
        if not u.startswith('http') or '<' in u or '>' in u:
            continue
        lower = u.lower()
        if any(h in lower for h in SKIP_RESOURCE_HOSTS):
            continue
        if u in seen:
            continue
        seen.add(u)
        resources.append(u)
    return resources


def resource_label(url):
    host = re.sub(r'^https?://(www\.)?', '', url).split('/')[0]
    if 'instagram.com' in host:
        handle = url.rstrip('/').split('/')[-1]
        return f'@{handle} on Instagram' if handle else 'Instagram'
    return host


def parse_date(date_str):
    """Parse RFC-2822 date string → (display_str, iso_str)."""
    for fmt in ('%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S %Z'):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime('%B %d, %Y'), dt.date().isoformat()
        except ValueError:
            continue
    return date_str, date.today().isoformat()


def transcript_to_html(segments, guest_name=None):
    """Convert Buzzsprout JSON transcript segments to HTML paragraphs."""
    paras, cur_speaker, cur_words, cur_end = [], None, [], 0
    for seg in segments:
        speaker = (seg.get('speaker') or 'Tyce').strip() or 'Tyce'
        sl = speaker.lower()
        if sl.startswith('tyce') or sl in ('speaker', 'speaker 1', 'speaker 3'):
            speaker = 'Tyce'
        elif sl in ('speaker 2', 'speaker2') and guest_name:
            speaker = guest_name
        body = FILLER.sub('', seg.get('body', '')).strip()
        body = re.sub(r'\s+,', ',', body)
        body = re.sub(r'  +', ' ', body)
        if not body:
            continue
        start = seg.get('startTime', 0)
        end   = seg.get('endTime', start)
        if speaker != cur_speaker or (cur_words and (start - cur_end) > 2.5):
            if cur_words:
                paras.append({'speaker': cur_speaker, 'text': ' '.join(cur_words)})
            cur_speaker, cur_words = speaker, [body]
        else:
            cur_words.append(body)
        cur_end = end
    if cur_words:
        paras.append({'speaker': cur_speaker, 'text': ' '.join(cur_words)})

    parts, prev_speaker = [], None
    for p in paras:
        if p['speaker'] != prev_speaker:
            parts.append(f'<p class="transcript-speaker">{p["speaker"]}</p>')
            prev_speaker = p['speaker']
        parts.append(f'<p class="transcript-para">{p["text"]}</p>')
    return '\n'.join(parts)


def build_episode_page(ep):
    """Return the full HTML string for one episode."""
    n          = ep['number']
    title      = ep['title']
    date_disp  = ep['date_display']
    date_iso   = ep['date_iso']
    duration   = ep['duration']
    audio_url  = ep['audio_url']
    desc_paras = ep.get('description_paras') or []
    if not desc_paras and ep.get('description'):
        desc_paras = [ep['description']]
    resources  = ep['resources']
    transcript = ep['transcript_html']
    prev_num   = n - 1
    next_num   = ep.get('next_number')
    local_img  = ep.get('local_img_path')

    episode_img_html = (
        f'<figure style="margin:0 0 2rem;">'
        f'<img src="{local_img}" alt="{title}" style="width:100%;border-radius:8px;display:block;" />'
        f'</figure>'
    ) if local_img else ''

    og_image = (
        f'{BASE_URL}/images/{os.path.basename(local_img)}'
        if local_img else f'{BASE_URL}/images/website-logo.png'
    )

    # Short description for meta tags (160 chars max)
    desc_flat = ' '.join(desc_paras)
    meta_desc = (desc_flat[:157] + '…') if len(desc_flat) > 160 else desc_flat
    meta_desc = meta_desc.replace('"', '&quot;')

    page_title = f'Ep. {n}: {title} — The Bird Dog Podcast'

    # Show notes body — episode copy only, plus a training link
    show_notes_html = ''.join(f'          <p>{p}</p>\n' for p in desc_paras)
    show_notes_html += '''          <p>
            Questions about the training topics in this episode? Tyce works with bird dog
            owners and hunters through
            <a href="https://www.utahbirddogtraining.com" target="_blank" rel="noopener">Utah Bird Dog Training</a>.
            Reach out to work with him directly.
          </p>'''

    # Resources: episode-specific links first, then standard partners
    resource_items = []
    for r in resources:
        resource_items.append(
            f'<li><strong><a href="{r}" target="_blank" rel="noopener">{resource_label(r)}</a></strong></li>'
        )
    for href, label, blurb in STANDARD_RESOURCES:
        resource_items.append(
            f'<li><strong><a href="{href}" target="_blank" rel="noopener">{label}</a></strong> — {blurb}</li>'
        )

    # Transcript section
    if transcript:
        transcript_section = f'''      <section class="episode-section">
        <h2>Transcript</h2>
        <div class="episode-body episode-transcript">
          <p class="transcript-notice">
            Full transcript for Episode {n}: <em>{title}</em>.
          </p>
          {transcript}
        </div>
      </section>'''
    else:
        transcript_section = f'''      <section class="episode-section">
        <h2>Transcript</h2>
        <div class="episode-body episode-transcript">
          <p>[Transcript coming soon. Check back after the episode has been live for a few days.]</p>
        </div>
      </section>'''

    # Prev/next nav
    prev_link = f'<a href="episode-{prev_num}.html" class="btn btn-outline">← Episode {prev_num}</a>' if prev_num >= 1 else ''
    next_link = f'<a href="episode-{next_num}.html" class="btn btn-outline">Episode {next_num} →</a>' if next_num else ''

    return f'''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="{meta_desc}" />
    <title>{page_title}</title>
    <link rel="canonical" href="{BASE_URL}/episodes/episode-{n}.html" />
    <!-- Open Graph -->
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="The Bird Dog Podcast" />
    <meta property="og:title" content="{page_title}" />
    <meta property="og:description" content="{meta_desc}" />
    <meta property="og:image" content="{og_image}" />
    <meta property="og:url" content="{BASE_URL}/episodes/episode-{n}.html" />
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{page_title}" />
    <meta name="twitter:description" content="{meta_desc}" />
    <meta name="twitter:image" content="{og_image}" />
    <link rel="stylesheet" href="../styles.css" />
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "PodcastEpisode",
      "name": "{title.replace(chr(34), chr(39))}",
      "episodeNumber": {n},
      "datePublished": "{date_iso}",
      "description": "{meta_desc.replace(chr(34), chr(39))}",
      "partOfSeries": {{
        "@type": "PodcastSeries",
        "name": "The Bird Dog Podcast",
        "url": "{BASE_URL}"
      }},
      "author": {{
        "@type": "Person",
        "name": "Tyce Erickson",
        "url": "https://www.utahbirddogtraining.com"
      }}
    }}
    </script>
{GA_SNIPPET}
  </head>
  <body>
    <nav class="site-nav">
      <div class="nav-inner">
        <a href="../index.html" class="nav-logo">
          <img src="../images/website-logo.png" alt="The Bird Dog Podcast" />
        </a>
        <ul class="nav-links">
          <li><a href="../index.html">Home</a></li>
          <li><a href="../episodes.html" class="active">Episodes</a></li>
          <li><a href="../partners.html">Partners</a></li>
          <li><a href="../about.html">About</a></li>
          <li><a href="../contact.html">Contact</a></li>
        </ul>
      </div>
    </nav>

    <main class="page-main narrow">
      <a href="../episodes.html" class="back-link">← All Episodes</a>

      <header class="episode-header">
        <p class="section-label">Episode {n} &nbsp;·&nbsp; {date_disp} &nbsp;·&nbsp; {duration}</p>
        <h1>{title}</h1>
        <p class="meta">
          Hosted by <a href="../about.html">Tyce Erickson</a> —
          professional bird dog trainer and owner of
          <a href="https://www.utahbirddogtraining.com" target="_blank" rel="noopener">Utah Bird Dog Training</a>.
        </p>
      </header>

      {episode_img_html}

      <div class="episode-player">
        <audio controls style="width:100%;margin-bottom:1.5rem;">
          <source src="{audio_url}" type="audio/mpeg">
        </audio>
      </div>
      <div class="btn-group" style="margin-bottom: 2.5rem">
        <a href="https://podcasts.apple.com/us/podcast/the-bird-dog-podcast/id1685804225" target="_blank" rel="noopener" class="btn btn-secondary">Apple Podcasts</a>
        <a href="https://open.spotify.com/show/53ilsNPxZ7pPlVF27GxyRc" target="_blank" rel="noopener" class="btn btn-secondary">Spotify</a>
      </div>

      <!-- Show Notes -->
      <section class="episode-section">
        <h2>About This Episode</h2>
        <div class="episode-body">
          {show_notes_html}
        </div>
      </section>

      <section class="episode-section">
        <h2>Resources &amp; Links</h2>
        <ul class="episode-resources">
          {''.join(resource_items)}
        </ul>
      </section>

      {transcript_section}

      <!-- About the Host -->
      <section class="episode-section episode-host-block">
        <p class="section-label">About the Host</p>
        <h3>Tyce Erickson</h3>
        <p>
          Tyce Erickson is a professional bird dog trainer and the owner of
          <a href="https://www.utahbirddogtraining.com" target="_blank" rel="noopener">Utah Bird Dog Training</a>
          in Utah. For nearly two decades he has worked with pointing dogs, retrievers, and family
          hunting dogs — helping owners build dogs that are capable and enjoyable in the field.
          The Bird Dog Podcast is an extension of that work: honest conversations on training,
          hunting, breeding, and everything that goes into a life spent working dogs.
        </p>
        <a href="../about.html" class="btn btn-outline" style="margin-top:1rem;display:inline-block;">More About Tyce</a>
      </section>

      <nav style="display:flex; justify-content:space-between; margin-top:2.5rem; gap:1rem; flex-wrap:wrap;">
        {prev_link}
        {next_link}
      </nav>
    </main>

{FOOTER_HTML}
  </body>
</html>'''


def update_episodes_list(all_episodes):
    """Regenerate the <ul class="episode-list"> block in episodes.html."""
    path = os.path.join(PROJECT_ROOT, 'episodes.html')
    with open(path) as f:
        content = f.read()

    total = len(all_episodes)

    # Update count in description and header paragraph
    content = re.sub(
        r'\d+ episodes on bird dog training',
        f'{total} episodes on bird dog training',
        content
    )
    content = re.sub(
        r'All \d+ episodes',
        f'All {total} episodes',
        content
    )
    content = re.sub(
        r'Browse all \d+ episodes',
        f'Browse all {total} episodes',
        content
    )
    content = re.sub(
        r'<meta name="description" content="All \d+ episodes[^"]*"',
        f'<meta name="description" content="All {total} episodes of The Bird Dog Podcast with Tyce Erickson — bird dog training, hunting, breeding, and more."',
        content
    )

    # Rebuild the episode list
    items = []
    for ep in sorted(all_episodes, key=lambda e: -e['number']):
        date_short = ep.get('date_short', ep.get('date_display', ''))
        n = ep['number']
        # Thumbnail: prefer jpg, fall back to png, then logo
        thumb_src = f'images/episode-{n}.jpg'
        items.append(f'''        <li>
          <a href="episodes/episode-{n}.html">
            <img class="episode-thumb" src="{thumb_src}" alt="Episode {n}" onerror="this.onerror=null;this.src=this.src.endsWith('.jpg')?'images/episode-{n}.png':'images/logo.png';" />
            <span class="episode-num">{n}</span>
            <span class="episode-info">
              <h3>{ep['title']}</h3>
              <span class="date">{date_short}</span>
            </span>
            <span class="episode-arrow" aria-hidden="true">→</span>
          </a>
        </li>''')

    new_list = '      <ul class="episode-list">\n' + '\n'.join(items) + '\n      </ul>'
    content = re.sub(
        r'<ul class="episode-list">.*?</ul>',
        new_list,
        content,
        flags=re.DOTALL
    )

    with open(path, 'w') as f:
        f.write(content)


def update_sitemap(all_episodes):
    today = date.today().isoformat()
    urls = [
        (f'{BASE_URL}/', today, 'weekly', '1.0'),
        (f'{BASE_URL}/episodes.html', today, 'weekly', '0.9'),
        (f'{BASE_URL}/about.html', today, 'monthly', '0.8'),
        (f'{BASE_URL}/partners.html', today, 'monthly', '0.7'),
        (f'{BASE_URL}/contact.html', today, 'monthly', '0.7'),
    ]
    for ep in all_episodes:
        urls.append((
            f'{BASE_URL}/episodes/episode-{ep["number"]}.html',
            ep.get('date_iso', today),
            'monthly',
            '0.8',
        ))

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, lastmod, freq, pri in urls:
        sitemap += f'  <url>\n    <loc>{url}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>{freq}</changefreq>\n    <priority>{pri}</priority>\n  </url>\n'
    sitemap += '</urlset>'

    with open(os.path.join(PROJECT_ROOT, 'sitemap.xml'), 'w') as f:
        f.write(sitemap)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('Fetching RSS feed…')
    rss_bytes = fetch(RSS_URL)
    root = ET.fromstring(rss_bytes)

    all_episodes = []
    items = root.findall('.//item')

    # Build sorted list of (ep_number, item) so we can set next/prev links
    numbered = []
    for item in items:
        ep_num_el = item.find('itunes:episode', NS)
        ep_num = ep_num_el.text.strip() if ep_num_el is not None else None
        if not ep_num:
            m = re.search(r'EP\.?\s*(\d+)|#(\d+)', item.findtext('title', ''), re.I)
            ep_num = (m.group(1) or m.group(2)) if m else None
        if ep_num:
            numbered.append((int(ep_num), item))

    numbered.sort(key=lambda x: x[0])

    new_pages = []

    for idx, (ep_num, item) in enumerate(numbered):
        ep_file = os.path.join(EPISODES_DIR, f'episode-{ep_num}.html')

        title     = clean_title((item.findtext('title') or f'Episode {ep_num}').strip(), ep_num)
        pub_date  = item.findtext('pubDate') or ''
        date_disp, date_iso = parse_date(pub_date)
        date_short = datetime.strptime(date_iso, '%Y-%m-%d').strftime('%b %d, %Y') if date_iso else ''

        raw_desc = item.findtext('description') or item.find('itunes:summary', NS) and item.find('itunes:summary', NS).text or ''
        desc_paras = clean_description(raw_desc)
        resources = extract_resources(raw_desc)
        guest_name = guess_guest_name(title)

        duration_el = item.find('itunes:duration', NS)
        raw_dur = duration_el.text.strip() if duration_el is not None else ''
        # Convert raw seconds to MM:SS or HH:MM:SS
        if raw_dur.isdigit():
            secs = int(raw_dur)
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            duration = f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'
        else:
            duration = raw_dur

        enclosure = item.find('enclosure')
        audio_url = enclosure.get('url', '') if enclosure is not None else ''

        # Download episode image from RSS if not already saved locally
        itunes_img_el = item.find('itunes:image', NS)
        rss_img_url = itunes_img_el.get('href') if itunes_img_el is not None else None
        local_img_path = None
        if rss_img_url:
            for ext in ('jpg', 'jpeg', 'png'):
                candidate = os.path.join(IMAGES_DIR, f'episode-{ep_num}.{ext}')
                if os.path.exists(candidate):
                    local_img_path = f'../images/episode-{ep_num}.{ext}'
                    break
            if not local_img_path:
                try:
                    img_bytes = fetch(rss_img_url)
                    ext = 'jpg' if rss_img_url.lower().endswith('.jpg') or b'\xff\xd8' in img_bytes[:4] else 'png'
                    save_path = os.path.join(IMAGES_DIR, f'episode-{ep_num}.{ext}')
                    with open(save_path, 'wb') as f:
                        f.write(img_bytes)
                    local_img_path = f'../images/episode-{ep_num}.{ext}'
                    print(f'    Image downloaded: episode-{ep_num}.{ext}')
                except Exception as e:
                    print(f'    Image download failed: {e}')

        next_num = numbered[idx + 1][0] if idx + 1 < len(numbered) else None

        ep_data = {
            'number':       ep_num,
            'title':        title,
            'date_display': date_disp,
            'date_iso':     date_iso,
            'date_short':   date_short,
            'duration':     duration,
            'audio_url':    audio_url,
            'description':  ' '.join(desc_paras),
            'description_paras': desc_paras,
            'resources':    resources,
            'transcript_html': '',
            'next_number':  next_num,
        }
        all_episodes.append(ep_data)

        # Skip if page already exists
        if os.path.exists(ep_file):
            continue

        print(f'  New episode detected: EP {ep_num} — {title}')

        # Try to fetch transcript
        transcript_html = ''
        for t_el in item.findall('podcast:transcript', NS):
            if t_el.get('type') == 'application/json' and t_el.get('url'):
                try:
                    t_data = json.loads(fetch(t_el.get('url')))
                    segments = t_data.get('segments', [])
                    if segments:
                        transcript_html = transcript_to_html(segments, guest_name=guest_name)
                        print(f'    Transcript downloaded ({len(segments)} segments)')
                except Exception as e:
                    print(f'    Transcript fetch failed: {e}')
                break

        ep_data['transcript_html'] = transcript_html
        ep_data['local_img_path'] = local_img_path

        # Also update the previous episode's "next" nav link
        if ep_num > 1:
            prev_file = os.path.join(EPISODES_DIR, f'episode-{ep_num - 1}.html')
            if os.path.exists(prev_file):
                with open(prev_file) as f:
                    prev_content = f.read()
                # Add next link if it's missing or points nowhere
                if f'episode-{ep_num}.html' not in prev_content:
                    prev_content = prev_content.replace(
                        f'<a href="episode-{ep_num - 2}.html" class="btn btn-outline">← Episode {ep_num - 2}</a>\n        \n      </nav>',
                        f'<a href="episode-{ep_num - 2}.html" class="btn btn-outline">← Episode {ep_num - 2}</a>\n        <a href="episode-{ep_num}.html" class="btn btn-outline">Episode {ep_num} →</a>\n      </nav>',
                    )
                    # Simpler: just append the next link if the closing nav tag is missing it
                    if f'episode-{ep_num}.html' not in prev_content:
                        prev_content = re.sub(
                            r'(<nav[^>]*>.*?)(</nav>)',
                            lambda m: m.group(1) + f'\n        <a href="episode-{ep_num}.html" class="btn btn-outline">Episode {ep_num} →</a>' + m.group(2),
                            prev_content, flags=re.DOTALL
                        )
                    with open(prev_file, 'w') as f:
                        f.write(prev_content)

        html = build_episode_page(ep_data)
        with open(ep_file, 'w') as f:
            f.write(html)
        new_pages.append(ep_num)
        time.sleep(0.2)

    print(f'\nUpdating episodes.html and sitemap.xml…')
    update_episodes_list(all_episodes)
    update_sitemap(all_episodes)

    if new_pages:
        print(f'\n✅ Generated {len(new_pages)} new page(s): episodes {new_pages}')
    else:
        print('\n✅ No new episodes found — all pages up to date.')


if __name__ == '__main__':
    main()
