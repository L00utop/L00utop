"""Update the Featured Projects section of README.md from public GitHub repos."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

START_MARKER = "<!-- FEATURED-PROJECTS:START -->"
END_MARKER = "<!-- FEATURED-PROJECTS:END -->"

LANGUAGE_STYLE: dict[str, tuple[str, str, str]] = {
    "C++": ("C++", "4361EE", "cplusplus"),
    "C": ("C", "4361EE", "c"),
    "Python": ("Python", "3776AB", "python"),
    "JavaScript": ("JavaScript", "323330", "javascript"),
    "TypeScript": ("TypeScript", "3178C6", "typescript"),
    "Rust": ("Rust", "111111", "rust"),
    "Go": ("Go", "00ADD8", "go"),
    "PHP": ("PHP", "777BB4", "php"),
    "HTML": ("HTML", "E34F26", "html5"),
    "CSS": ("CSS", "1572B6", "css3"),
    "C#": ("C#", "239120", "csharp"),
    "Java": ("Java", "ED8B00", "openjdk"),
}

LANGUAGE_EMOJI: dict[str, str] = {
    "C++": "⚙️",
    "C": "⚙️",
    "Rust": "🦀",
    "Python": "🐍",
    "JavaScript": "🟨",
    "TypeScript": "🔷",
    "Go": "🐹",
    "PHP": "🐘",
}


def github_get(url: str, token: str | None = None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "L00utop-Readme-Updater",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def shields_part(value: str) -> str:
    escaped = value.replace("-", "--").replace("_", "__").replace(" ", "_")
    return urllib.parse.quote(escaped, safe="")


def make_badge(
    label: str,
    message: str,
    color: str,
    logo: str | None = None,
    alt: str | None = None,
) -> str:
    url = (
        f"https://img.shields.io/badge/{shields_part(label)}-{shields_part(message)}-{color}"
        "?style=flat-square"
    )
    if logo:
        url += f"&logo={urllib.parse.quote(logo, safe='')}&logoColor=white"
    safe_alt = html.escape(alt or f"{label} {message}", quote=True)
    return f'<img src="{url}" alt="{safe_alt}" />'


def has_release(owner: str, repo_name: str, token: str | None) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo_name}/releases?per_page=1"
    try:
        releases = github_get(url, token)
    except urllib.error.URLError:
        return None
    if isinstance(releases, list) and releases:
        tag = releases[0].get("tag_name")
        return str(tag) if tag else "Latest"
    return None


def pick_emoji(repo: dict, ai_topics: set[str]) -> str:
    topics = {t.lower() for t in (repo.get("topics") or [])}
    if topics & ai_topics:
        return "🤖"
    lang = repo.get("language") or ""
    return LANGUAGE_EMOJI.get(lang, "📦")


def select_repos(repos: list[dict], cfg: dict) -> list[dict]:
    excluded = set(cfg.get("exclude", []))
    max_projects = int(cfg.get("max_projects", 4))
    min_projects = int(cfg.get("min_projects", 2))
    max_age_days = int(cfg.get("max_age_days", 365))

    candidates = [
        r
        for r in repos
        if not r.get("private")
        and not r.get("fork")
        and not r.get("archived")
        and r.get("name") not in excluded
    ]
    candidates.sort(key=lambda r: r.get("pushed_at", ""), reverse=True)

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=max_age_days)
    recent: list[dict] = []
    for repo in candidates:
        pushed_raw = repo.get("pushed_at", "")
        try:
            pushed_at = dt.datetime.fromisoformat(pushed_raw.replace("Z", "+00:00"))
        except ValueError:
            pushed_at = now
        if pushed_at >= cutoff:
            recent.append(repo)

    if len(recent) >= min_projects:
        return recent[:max_projects]
    return candidates[: min(max_projects, max(min_projects, len(recent)))]


def build_card(repo: dict, cfg: dict, token: str | None, colspan: int = 1) -> str:
    owner = cfg["username"]
    name = repo["name"]
    repo_url = repo["html_url"]
    override = cfg.get("overrides", {}).get(name, {})
    ai_topics = {t.lower() for t in cfg.get("ai_topics", [])}
    topics = {t.lower() for t in (repo.get("topics") or [])}

    title = html.escape(override.get("title") or f"{pick_emoji(repo, ai_topics)} {name}")
    if "description_html" in override:
        desc_html = override["description_html"]
    else:
        raw_desc = override.get("description") or repo.get("description") or "Active repository."
        desc_html = html.escape(raw_desc)

    badges: list[str] = []

    website = override.get("website") or repo.get("homepage")
    if website:
        website_label = override.get("website_label") or urllib.parse.urlparse(website).netloc or "Link"
        img = make_badge("Website", website_label, "4CC9F0", logo="googlechrome", alt=f"{name} Website")
        badges.append(f'<a href="{html.escape(website, quote=True)}">{img}</a>')

    lang = repo.get("language")
    if lang:
        label, color, logo = LANGUAGE_STYLE.get(lang, (lang, "4361EE", ""))
        img = make_badge(label, "Repo", color, logo=logo or None, alt=label)
        if name == "HMFOMT_PC":
            img = make_badge(label, "Engine", color, logo=logo or None, alt=label)
        badges.append(f'<a href="{html.escape(repo_url, quote=True)}">{img}</a>')

    release_tag = has_release(owner, name, token)
    if release_tag:
        rel_label = override.get("releases_label") or release_tag
        img = make_badge("Releases", rel_label, "FF5CCC", logo="github", alt=f"{name} Releases")
        badges.append(
            f'<a href="{html.escape(repo_url, quote=True)}/releases">{img}</a>'
        )

    for extra in override.get("extra_badges", []):
        img = make_badge(
            extra["label"],
            extra["message"],
            extra["color"],
            logo=extra.get("logo"),
        )
        badges.append(f'<a href="{html.escape(repo_url, quote=True)}">{img}</a>')

    uses_ai = bool(override.get("ai")) or bool(topics & ai_topics)
    if uses_ai:
        badges.append(make_badge("Built with", "AI", "7209B7", alt="Built with AI"))

    if not badges:
        badges.append(
            f'<a href="{html.escape(repo_url, quote=True)}">'
            f'{make_badge("GitHub", "Repository", "4361EE", logo="github", alt=name)}'
            "</a>"
        )

    td_attr = 'colspan="2" valign="top"' if colspan == 2 else 'width="50%" valign="top"'
    badges_block = "\n        ".join(badges)
    return (
        f"    <td {td_attr}>\n"
        f'      <h4 align="center"><a href="{html.escape(repo_url, quote=True)}">{title}</a></h4>\n'
        f'      <p align="center">\n'
        f"        {desc_html}\n"
        f"      </p>\n"
        f'      <p align="center">\n'
        f"        {badges_block}\n"
        f"      </p>\n"
        f"    </td>"
    )


def render_table(selected: list[dict], cfg: dict, token: str | None) -> str:
    rows: list[str] = []
    for i in range(0, len(selected), 2):
        pair = selected[i : i + 2]
        if len(pair) == 1:
            cells = build_card(pair[0], cfg, token, colspan=2)
        else:
            cells = "\n".join(build_card(r, cfg, token, colspan=1) for r in pair)
        rows.append(f"  <tr>\n{cells}\n  </tr>")

    body = "\n".join(rows)
    return f'<div align="center">\n\n<table>\n{body}\n</table>\n\n</div>'


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    cfg_path = root / ".github" / "projects-config.json"
    readme_path = root / "README.md"

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    token = os.environ.get("GITHUB_TOKEN") or None
    owner = cfg["username"]

    repos = github_get(
        f"https://api.github.com/users/{owner}/repos?type=owner&sort=pushed&per_page=100",
        token,
    )
    if not isinstance(repos, list):
        raise RuntimeError("Unexpected GitHub API response")

    selected = select_repos(repos, cfg)
    if not selected:
        print("No eligible repositories found; leaving README untouched.")
        return 0

    rendered = render_table(selected, cfg, token)
    readme = readme_path.read_text(encoding="utf-8")

    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )
    if not pattern.search(readme):
        raise RuntimeError(f"Could not find {START_MARKER} ... {END_MARKER} in README.md")

    replacement = f"{START_MARKER}\n\n{rendered}\n\n{END_MARKER}"
    updated = pattern.sub(lambda _: replacement, readme, count=1)

    if updated == readme:
        print("Featured Projects already up to date.")
        return 0

    readme_path.write_text(updated, encoding="utf-8")
    print(f"Updated Featured Projects with: {[r['name'] for r in selected]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
