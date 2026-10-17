#!/usr/bin/env python3
"""Generate an animated terminal card (boot sequence + language stats) as SVG.

Reads language byte counts from the GitHub API and writes a dark and a light
variant. No runtime dependencies beyond the standard library; the output is a
self-contained SVG animated with CSS keyframes, so it renders inside a README.

Usage:
    python3 scripts/gen_stats_card.py --user Just-Martin-Really --out dist
"""
import argparse
import json
import os
import random
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"

# Repos whose byte counts are generated or vendored rather than written by hand.
# Add names here to keep them out of the chart.
EXCLUDE_REPOS = set()

W = 740
CHARW = 7.81
FS = 13
LH = 19.5
X0 = 26
T = 20.0  # the animation plays once over this window, then holds

THEMES = {
    "dark": dict(
        bg="#282a36", chrome="#21222c", border="#44475a", fg="#f8f8f2",
        dim="#6272a4", green="#50fa7b", cyan="#8be9fd",
        yellow="#f1fa8c", purple="#bd93f9", track="#44475a",
    ),
    "light": dict(
        bg="#ffffff", chrome="#f6f8fa", border="#d0d7de", fg="#1f2328",
        dim="#6e7781", green="#1a7f37", cyan="#0969da",
        yellow="#9a6700", purple="#8250df", track="#eaeef2",
    ),
}

LANG_COLOR = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "HTML": "#e34c26",
    "Java": "#b07219", "Zig": "#ec915c", "C": "#8b949e", "Shell": "#89e051",
    "CSS": "#663399", "Pug": "#a86454", "Dockerfile": "#384d54",
    "TypeScript": "#3178c6", "Swift": "#F05138", "Makefile": "#427819",
}


def api(path):
    req = urllib.request.Request(f"{API}{path}", headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-stats-card",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect(user, include_private=False):
    """Total language bytes across the user's own, non-archived repos.

    Private repos need a token with `repo` scope; the token a workflow gets by
    default only sees public ones.
    """
    repos = []
    page = 1
    while True:
        if include_private:
            path = f"/user/repos?per_page=100&affiliation=owner&visibility=all&page={page}"
        else:
            path = f"/users/{user}/repos?per_page=100&type=owner&page={page}"
        batch = api(path)
        repos += batch
        if len(batch) < 100:
            break
        page += 1

    langs = {}
    counted = 0
    for repo in repos:
        if repo["fork"] or repo["archived"] or repo["name"] in EXCLUDE_REPOS:
            continue
        counted += 1
        for name, size in api(f"/repos/{repo['full_name']}/languages").items():
            langs[name] = langs.get(name, 0) + size

    ordered = dict(sorted(langs.items(), key=lambda kv: -kv[1]))
    return {"repos": counted, "langs": ordered}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pct(t):
    return round(t / T * 100, 3)


class Card:
    def __init__(self, theme):
        self.th = THEMES[theme]
        self.body = []
        self.css = []
        self.n = 0
        self.height = 486  # overwritten once the rows are laid out

    def uid(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def text(self, x, y, s, fill=None):
        f = f' fill="{fill}"' if fill else ""
        tl = f' textLength="{len(s) * CHARW:.2f}" lengthAdjust="spacingAndGlyphs"' if s else ""
        self.body.append(f'<text x="{x}" y="{y}"{f}{tl}>{esc(s)}</text>')

    def typed(self, x, y, s, t0, dur, fill=None, cursor=True):
        """Reveal text character by character behind a growing clip rect."""
        cid = self.uid("clip")
        n = max(len(s), 1)
        wpx = n * CHARW
        # the static width is the full one: a renderer that ignores the
        # animation shows the finished card rather than an empty window
        self.body.append(
            f'<clipPath id="{cid}"><rect x="{x}" y="{y - FS}" height="{FS + 6}"'
            f' width="{wpx:.2f}"/></clipPath>'
        )
        self.css.append(
            f"#{cid} rect{{animation:{cid} {T}s steps({n}) forwards}}"
            f"@keyframes {cid}{{0%,{pct(t0)}%{{width:0}}{pct(t0 + dur)}%,100%{{width:{wpx:.2f}px}}}}"
        )
        self.body.append(f'<g clip-path="url(#{cid})">')
        self.text(x, y, s, fill=fill)
        self.body.append("</g>")
        if cursor:
            kid = self.uid("cur")
            self.body.append(
                f'<rect id="{kid}" x="{x}" y="{y - FS + 2}" width="{CHARW:.2f}"'
                f' height="{FS + 2}" fill="{self.th["fg"]}" opacity="0"/>'
            )
            self.css.append(
                f"#{kid}{{animation:{kid} {T}s steps({n}) forwards}}"
                f"@keyframes {kid}{{0%,{pct(t0)}%{{opacity:.9;transform:translateX(0)}}"
                f"{pct(t0 + dur)}%{{opacity:.9;transform:translateX({wpx:.2f}px)}}"
                f"{pct(t0 + dur + .01)}%,100%{{opacity:0;transform:translateX({wpx:.2f}px)}}}}"
            )

    def fade(self, t0, inner, dur=0.22):
        gid = self.uid("f")
        self.css.append(
            f"#{gid}{{animation:{gid} {T}s linear forwards}}"
            f"@keyframes {gid}{{0%,{pct(t0)}%{{opacity:0}}{pct(t0 + dur)}%,100%{{opacity:1}}}}"
        )
        self.body.append(f'<g id="{gid}">{inner}</g>')

    def svg(self, freeze=None):
        th = self.th
        css = "".join(self.css)
        if freeze is not None:
            # debugging aid: pin every animation to one moment of the loop
            css += f"*{{animation-delay:-{freeze}s!important}}"
        return f"""<svg viewBox="0 0 {W} {self.height}" width="{W}" height="{self.height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="terminal boot sequence with language statistics">
<style>
text{{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:{FS}px;fill:{th['fg']};white-space:pre}}
rect{{shape-rendering:geometricPrecision}}
{css}
</style>
<rect width="{W}" height="{self.height}" rx="10" fill="{th['bg']}" stroke="{th['border']}"/>
<path d="M0 10a10 10 0 0 1 10-10h{W - 20}a10 10 0 0 1 10 10v22H0z" fill="{th['chrome']}"/>
<line x1="0" y1="32" x2="{W}" y2="32" stroke="{th['border']}"/>
<circle cx="20" cy="16" r="5.5" fill="#ff5f57"/><circle cx="38" cy="16" r="5.5" fill="#febc2e"/><circle cx="56" cy="16" r="5.5" fill="#28c840"/>
<text x="{W / 2}" y="21" text-anchor="middle" fill="{th['dim']}" font-size="11.5">martin@github - zsh</text>
{''.join(self.body)}
</svg>"""


def build(theme, data, top_n, seed=7):
    c = Card(theme)
    th = c.th
    rnd = random.Random(seed)
    langs = list(data["langs"].items())[:top_n]
    total = sum(data["langs"].values()) or 1
    y = 62

    c.typed(X0, y, "$ ", 0.0, 0.01, fill=th["green"], cursor=False)
    c.typed(X0 + 2 * CHARW, y, "boot martin.dev", 0.25, 0.75)
    y += LH * 1.5

    boot = [
        ("ok", "mounting /dev/coffee", ""),
        ("ok", "loading dotfiles", "dracula"),
        ("ok", "starting sketchybar.service", ""),
        ("warn", f"side projects: {data['repos']} started, {data['repos']} unfinished", ""),
        ("ok", "fetching language stats", f"{data['repos']} repos"),
    ]
    t = 1.35
    for state, msg, note in boot:
        col = th["green"] if state == "ok" else th["yellow"]
        label = "\u00a0\u00a0ok\u00a0\u00a0" if state == "ok" else "\u00a0warn\u00a0"
        inner = (
            f'<text x="{X0}" y="{y}" fill="{th["dim"]}">[</text>'
            f'<text x="{X0 + CHARW}" y="{y}" fill="{col}" textLength="{6 * CHARW:.2f}"'
            f' lengthAdjust="spacingAndGlyphs">{esc(label)}</text>'
            f'<text x="{X0 + 7 * CHARW}" y="{y}" fill="{th["dim"]}">]</text>'
            f'<text x="{X0 + 9.5 * CHARW}" y="{y}">{esc(msg)}</text>'
        )
        if note:
            inner += (
                f'<text x="{W - 26}" y="{y}" text-anchor="end" fill="{th["cyan"]}">{esc(note)}</text>'
            )
        c.fade(t, inner)
        t += 0.42
        y += LH

    y += LH * 0.9
    c.typed(X0, y, "$ ", t + 0.3, 0.01, fill=th["green"], cursor=False)
    c.typed(X0 + 2 * CHARW, y, f"stats --languages --top {top_n}", t + 0.55, 1.0)
    t += 1.85
    y += LH * 1.6

    bar_x, bar_w = 150, 400
    c.fade(t, (
        f'<text x="{X0}" y="{y}" fill="{th["dim"]}" font-size="11">LANGUAGE</text>'
        f'<text x="{bar_x}" y="{y}" fill="{th["dim"]}" font-size="11">DISTRIBUTION</text>'
        f'<text x="{W - 26}" y="{y}" text-anchor="end" fill="{th["dim"]}" font-size="11">SIZE</text>'
    ))
    y += LH * 1.3
    t += 0.3

    largest = langs[0][1] if langs else 1
    for name, size in langs:
        share = size / total * 100
        w = max(bar_w * size / largest, 2)
        col = LANG_COLOR.get(name, th["purple"])
        bid, pid = c.uid("bar"), c.uid("pc")
        row = (
            f'<text x="{X0}" y="{y}" fill="{col}">{esc(name)}</text>'
            f'<rect x="{bar_x}" y="{y - 10}" width="{bar_w}" height="11" rx="2.5" fill="{th["track"]}"/>'
            f'<rect id="{bid}" x="{bar_x}" y="{y - 10}" width="{w:.1f}" height="11" rx="2.5" fill="{col}"/>'
            f'<text x="{bar_x + bar_w + 14}" y="{y}" fill="{th["fg"]}">{share:4.1f}%</text>'
            f'<text x="{W - 26}" y="{y}" text-anchor="end" fill="{th["dim"]}">{size / 1000:,.0f} kB</text>'
        )
        # the percentage flickers through a few values before it settles
        row += "".join(
            f'<text id="{pid}s{i}" x="{bar_x + bar_w + 14}" y="{y}" fill="{th["fg"]}"'
            f' opacity="0">{rnd.uniform(1, 40):4.1f}%</text>'
            for i in range(3)
        )
        c.fade(t, row)
        c.css.append(
            f"#{bid}{{animation:{bid} {T}s cubic-bezier(.22,.8,.3,1) forwards}}"
            f"@keyframes {bid}{{0%,{pct(t)}%{{width:0}}{pct(t + 0.85)}%,100%{{width:{w:.1f}px}}}}"
        )
        for i in range(3):
            a, b = t + 0.08 * i, t + 0.08 * (i + 1)
            c.css.append(
                f"#{pid}s{i}{{animation:{pid}s{i} {T}s step-end forwards}}"
                f"@keyframes {pid}s{i}{{0%,{pct(a)}%{{opacity:0}}{pct(a + .001)}%{{opacity:1}}"
                f"{pct(b)}%,100%{{opacity:0}}}}"
            )
        t += 0.3
        y += LH * 1.45

    y += 2
    stamp = datetime.now(timezone.utc).date()
    footer = f"total {total / 1e6:.2f} MB · {data['repos']} repos · updated {stamp}"
    c.fade(t + 0.7, f'<text x="{X0}" y="{y}" fill="{th["dim"]}">{esc(footer)}</text>')

    c.typed(X0, y + LH * 1.6, "$ ", t + 1.1, 0.01, fill=th["green"], cursor=False)
    blink = c.uid("blink")
    # the blink runs on its own short loop, inside a group that only appears
    # once the final prompt has been printed
    c.fade(t + 1.1, (
        f'<rect id="{blink}" x="{X0 + 2 * CHARW:.1f}" y="{y + LH * 1.6 - FS + 2}"'
        f' width="{CHARW:.2f}" height="{FS + 2}" fill="{th["fg"]}"/>'
    ), dur=0.01)
    c.css.append(
        f"#{blink}{{animation:{blink} 1.06s step-end infinite}}"
        f"@keyframes {blink}{{0%,50%{{opacity:.9}}50.01%,100%{{opacity:0}}}}"
    )
    c.height = int(y + LH * 1.6 + 18)
    return c


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", required=True)
    p.add_argument("--out", default="dist")
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--freeze", type=float, help="pin animations to this second, for preview stills")
    p.add_argument("--data", help="read stats from this JSON file instead of the API")
    p.add_argument("--include-private", action="store_true",
                   help="count private repos too; reads the token's own account, "
                        "so --user is ignored (needs a token with repo scope)")
    args = p.parse_args()

    data = json.load(open(args.data)) if args.data else collect(args.user, args.include_private)
    os.makedirs(args.out, exist_ok=True)
    for theme in THEMES:
        path = os.path.join(args.out, f"terminal-{theme}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(build(theme, data, args.top).svg(args.freeze))
        print(f"{path} ({os.path.getsize(path)} bytes)")
    print(f"{data['repos']} repos, {sum(data['langs'].values()):,} bytes, "
          f"top: {', '.join(list(data['langs'])[:args.top])}")


if __name__ == "__main__":
    main()
