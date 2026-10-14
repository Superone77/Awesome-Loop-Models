#!/usr/bin/env python3
"""
build.py — Single-source build script for Awesome Loop Models.

Reads all papers/*.yaml and blogs/*.yaml files and generates:
  1. papers.json   — catalog manifest consumed by index.html, plus the paper
                     records it lists under catalog/papers-NNN.json
  2. submission-meta.json — minimal tag/path inventory consumed by submit.html
  3. README.md     — the GitHub repository README
  4. TAGS.md       — contributor-facing tag reference

The paper/blog YAML files are the source of truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import yaml

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import (  # noqa: E402
    AXIS_LABELS,
    REQUIRED_PAPER_SURVEY_FIELDS,
    RETIRED_FIELDS,
    SURVEY_CHAPTERS,
    SURVEY_FIELDS,
    SURVEY_LIST_FIELDS,
    SURVEY_PARTS,
    SURVEY_SCALAR_FIELDS,
    SURVEY_SECTION_NUMBERS,
    SURVEY_SECTION_TITLES,
    SURVEY_SECTIONS,
    VALID_CATALOG_FITS,
    VALID_CLAIMS,
    VALID_COMPARISONS,
    VALID_DEPTH_CONTROLS,
    VALID_LOOP_TOPOLOGIES,
    VALID_SHARING_SCHEMES,
    VALID_SURVEY_SECTIONS,
    chapter_of,
)

REPO_ROOT = Path(__file__).parent.parent
PAPERS_DIR = REPO_ROOT / "papers"
BLOGS_DIR = REPO_ROOT / "blogs"
BRIEFINGS_DIR = REPO_ROOT / "briefings"
JSON_OUT = REPO_ROOT / "papers.json"
# The newest briefing's full reading page, fetched lazily by index.html's Briefing tab.
# papers.json.briefings stays content-free; the Markdown body lives only here.
# The path is relative to JSON_OUT.parent, next to the manifest.
BRIEFING_LATEST_FILENAME = "briefing-latest.json"
BRIEFING_PAGE_FIELDS = (
    "date",
    "title",
    "status",
    "summary",
    "highlights",
    "candidates",
    "source_path",
    "body_markdown",
)
# Paper records are split into bounded chunks next to the manifest so no single
# browser asset grows with the catalog. Paths are relative to JSON_OUT.parent.
PAPER_CHUNK_DIRNAME = "catalog"
PAPER_CHUNK_SIZE = 100
SUBMISSION_META_OUT = REPO_ROOT / "submission-meta.json"
README_OUT = REPO_ROOT / "README.md"
TAGS_OUT = REPO_ROOT / "TAGS.md"
HEADER_FILE = Path(__file__).parent / "README_HEADER.md"
FOOTER_FILE = Path(__file__).parent / "README_FOOTER.md"
REPO_META_FILE = REPO_ROOT / "repo_meta.json"
REPO_META_JS_OUT = REPO_ROOT / "assets" / "repo-meta.js"
ISSUE_TEMPLATE_CONFIG_TEMPLATE_FILE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.template.yml"
ISSUE_TEMPLATE_CONFIG_OUT = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"
CATALOG_TIME_ZONE = ZoneInfo("America/New_York")

ADJACENT_SCOPE_NOTE = (
    "Retained as adjacent work; its recurrence is outside the strict single-forward loop-model scope."
)

TAXONOMY_NOTE = (
    "Papers are organized by the chapters of the repo's topic map. Each paper lists every taxonomy section it "
    "belongs to, primary first, and records where its loop sits, how weights are shared, how depth is controlled, "
    "and what it claims looping buys. Every value is controlled; there are no free-form tags."
)
BLOG_SECTION_TITLE = "Blogs"
DAILY_BRIEFING_SECTION_TITLE = "Daily Briefing"
DAILY_BRIEFING_SECTION_DESC = (
    "Reader-facing daily research briefings: notable loop-model papers, watchlist candidates, "
    "and concise inclusion rationale."
)
BLOG_SECTION_DESC = (
    "Long-form technical posts, essays, and deep-dives about loop models. Blogs list the taxonomy sections they "
    "discuss but stay in a single flat section."
)
BLOG_VENUE_CLASS = "venue-other"
BADGE_STYLE = "flat-square"
LINK_BADGES = {
    "blog": ("Blog", "0ea5e9"),
    "arxiv": ("arXiv", "b31b1b"),
    "alphaxiv": ("AlphaXiv", "7c3aed"),
    "paper": ("Paper", "0366d6"),
    "github": ("GitHub stars", "24292f"),
    "readme": ("README", "0969da"),
    "hf": ("HuggingFace", "ffb000"),
    "openreview": ("OpenReview", "8E44AD"),
    "project": ("Website", "blue"),
    "twitter": ("Twitter", "1d9bf0"),
}


def load_repo_meta() -> dict:
    meta = json.loads(REPO_META_FILE.read_text(encoding="utf-8"))
    required_keys = ("github_owner", "default_repo_name", "public_repo_name")
    missing = [key for key in required_keys if not meta.get(key)]
    if missing:
        raise ValueError(f"repo_meta.json is missing required keys: {', '.join(missing)}")
    meta["public_pages_base"] = f"https://{meta['github_owner']}.github.io/{meta['public_repo_name']}"
    meta["public_github_base"] = f"https://github.com/{meta['github_owner']}/{meta['public_repo_name']}"
    return meta


def render_repo_meta_js(meta: dict) -> str:
    return (
        "window.REPO_META = {\n"
        f"  githubOwner: {json.dumps(meta['github_owner'])},\n"
        f"  defaultRepoName: {json.dumps(meta['default_repo_name'])},\n"
        f"  publicRepoName: {json.dumps(meta['public_repo_name'])},\n"
        f"  publicPagesBase: {json.dumps(meta['public_pages_base'])},\n"
        "  inferRepoNameFromLocation(locationLike = window.location) {\n"
        "    const pathParts = String(locationLike.pathname || '').split('/').filter(Boolean);\n"
        "    const hostname = String(locationLike.hostname || '');\n"
        "    if (hostname.endsWith('github.io') && pathParts.length) return pathParts[0];\n"
        "    if (hostname === 'github.com' && pathParts.length >= 2) return pathParts[1];\n"
        "    return this.defaultRepoName;\n"
        "  },\n"
        "  getGitHubRepoBase(locationLike = window.location) {\n"
        "    return 'https://github.com/' + this.githubOwner + '/' + this.inferRepoNameFromLocation(locationLike);\n"
        "  },\n"
        "  getGitHubBlobUrl(path, locationLike = window.location) {\n"
        "    return this.getGitHubRepoBase(locationLike) + '/blob/main/' + String(path || '').replace(/^\\/+/, '');\n"
        "  },\n"
        "  getGitHubNewFileBase(locationLike = window.location) {\n"
        "    return this.getGitHubRepoBase(locationLike) + '/new/main';\n"
        "  }\n"
        "};\n"
    )


def build_repo_meta_js(meta: dict) -> None:
    REPO_META_JS_OUT.write_text(render_repo_meta_js(meta), encoding="utf-8")


def render_issue_template_config(meta: dict) -> str:
    template = ISSUE_TEMPLATE_CONFIG_TEMPLATE_FILE.read_text(encoding="utf-8")
    return (
        template
        .replace("{{PUBLIC_SUBMIT_URL}}", meta["public_pages_base"] + "/submit.html")
        .replace("{{PUBLIC_TAGS_URL}}", meta["public_github_base"] + "/blob/main/TAGS.md")
    )


def build_issue_template_config(meta: dict) -> None:
    ISSUE_TEMPLATE_CONFIG_OUT.write_text(render_issue_template_config(meta), encoding="utf-8")

VENUE_CLASSES = {
    "NeurIPS": "venue-neurips",
    "ICLR": "venue-iclr",
    "ICML": "venue-icml",
    "ACL": "venue-acl",
    "CoLM": "venue-colm",
    "COLM 2025 Workshop": "venue-colm",
    "LoG": "venue-log",
    "arXiv": "venue-arxiv",
}

def normalize_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [str(item) for item in value if item is not None]
    else:
        raise ValueError(f"expected string or list, got {type(value).__name__}")

    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = raw.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def has_non_empty_metadata_value(raw_value: object) -> bool:
    if raw_value is None:
        return False
    if isinstance(raw_value, str):
        return bool(raw_value.strip())
    if isinstance(raw_value, (list, tuple, set)):
        return any(has_non_empty_metadata_value(item) for item in raw_value)
    if isinstance(raw_value, dict):
        return bool(raw_value)
    return True


def normalize_bool_flag(raw_value: object) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value is None:
        return False
    return str(raw_value).strip().lower() in {"1", "true", "yes", "y"}


def normalize_must_read_flag(raw_must_read: object) -> bool:
    return normalize_bool_flag(raw_must_read)


def reject_retired_fields(data: dict, source: str) -> None:
    """Fail on fields retired by the current taxonomy (categories and free-form tags)."""
    retired = [field for field in (*RETIRED_FIELDS, "family_tags") if field in data]
    if retired:
        raise ValueError(
            f"{source}: {', '.join(retired)} no longer exist; classify the entry with survey_section and the "
            "design axes (see TAXONOMY.md)"
        )


def normalize_paper_taxonomy_fields(paper: dict, source: str = "<paper>") -> dict:
    reject_retired_fields(paper, source)
    raw_catalog_fit = paper.get("catalog_fit")
    catalog_fit = "strict" if raw_catalog_fit is None else str(raw_catalog_fit).strip().lower()
    if catalog_fit not in VALID_CATALOG_FITS:
        raise ValueError(
            f"{source}: invalid catalog_fit '{catalog_fit}'; valid values are {list(VALID_CATALOG_FITS)!r}"
        )
    return {"catalog_fit": catalog_fit}


def primary_section(entry: dict) -> str | None:
    sections = entry.get("survey_section") or []
    return sections[0] if sections else None


def section_label(section_id: str) -> str:
    return f"§{SURVEY_SECTION_NUMBERS[section_id]} {SURVEY_SECTION_TITLES[section_id]}"


def heading_anchor(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "-")
        .replace("/", "")
        .replace("(", "")
        .replace(")", "")
        .replace("&", "")
        .replace(".", "")
        .replace(",", "")
    )


def get_arxiv_id(filename: str) -> str | None:
    stem = Path(filename).stem
    match = re.match(r"^(\d{4}\.\d{4,5})", stem)
    return match.group(1) if match else None


def get_arxiv_id_from_url(url: str) -> str | None:
    if not url:
        return None
    match = re.search(r"(?:arxiv\.org/(?:abs|pdf)|alphaxiv\.org/abs)/(\d{4}\.\d{4,5})(?:v\d+)?", url)
    return match.group(1) if match else None


def _repo_slug_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.endswith("github.com") and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    if parsed.netloc.endswith("huggingface.co") and parts:
        return "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
    return None


def _hostname_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.strip().lower()
    if not host:
        return None
    return host.removeprefix("www.")


def _openreview_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.netloc.endswith("openreview.net"):
        return None
    query = parsed.query or ""
    match = re.search(r"(?:^|&)id=([^&]+)", query)
    if match:
        return match.group(1)
    return None


def _is_openreview_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("openreview.net")


def _github_stargazers_url(url: str) -> str | None:
    repo_slug = _repo_slug_from_url(url)
    if not repo_slug:
        return None
    return f"https://github.com/{repo_slug}/stargazers"


def shields_escape(text: str) -> str:
    return text.replace("_", "__").replace("-", "--").replace(" ", "_")


def badge_message_for_link(key: str, url: str) -> str | None:
    if key in {"arxiv", "alphaxiv"}:
        return get_arxiv_id_from_url(url)
    if key == "twitter":
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0] not in {"home", "intent", "share", "search", "i"}:
            return f"@{parts[0].lstrip('@')}"
        return _hostname_from_url(url)
    if key in {"github", "hf", "readme"}:
        return _repo_slug_from_url(url) or _hostname_from_url(url)
    if key == "openreview":
        return _openreview_id_from_url(url) or _hostname_from_url(url)
    if key in {"project", "paper", "blog"}:
        return _hostname_from_url(url)
    return None


def normalize_comment_links(raw_comment: object) -> list[dict]:
    if not raw_comment:
        return []

    if isinstance(raw_comment, (str, dict)):
        items = [raw_comment]
    elif isinstance(raw_comment, list):
        items = raw_comment
    else:
        return []

    rows: list[tuple[str, str]] = []
    for item in items:
        label = ""
        url = ""
        if isinstance(item, str):
            url = item.strip()
        elif isinstance(item, dict):
            raw_url = item.get("url", "")
            raw_label = item.get("label", "")
            url = str(raw_url).strip() if raw_url is not None else ""
            label = str(raw_label).strip() if raw_label is not None else ""
        if url:
            rows.append((label, url))

    if not rows:
        return []

    multi = len(rows) > 1
    out = []
    for idx, (label, url) in enumerate(rows, start=1):
        out.append({
            "label": label or (f"Comment {idx}" if multi else "Comment"),
            "url": url,
        })
    return out


def validate_links(links: dict, source: str) -> None:
    if not isinstance(links, dict):
        raise ValueError(f"{source}: links must be a mapping")
    if not any(links.get(key) for key in ("arxiv", "paper", "openreview")):
        raise ValueError(f"{source}: at least one of links.arxiv, links.paper, or links.openreview is required")


# Blogs are intentionally flat metadata entries: they need a canonical public blog URL,
# but they do not participate in the paper taxonomy.
def validate_blog_links(links: dict, source: str) -> None:
    if not isinstance(links, dict):
        raise ValueError(f"{source}: links must be a mapping")
    if not links.get("blog"):
        raise ValueError(f"{source}: blogs require links.blog")


def normalize_venue_class(venue: str, entry_type: str) -> str:
    if entry_type == "blog":
        return BLOG_VENUE_CLASS
    return VENUE_CLASSES.get(venue, "venue-other")


def validate_publication_metadata(data: dict, source: str) -> None:
    """Require explicit, attributable evidence without inferring review from venue names."""
    if "peer_reviewed" in data and not isinstance(data["peer_reviewed"], bool):
        raise ValueError(f"{source}: peer_reviewed must be a boolean")
    evidence = data.get("venue_source")
    if evidence is not None:
        if not isinstance(evidence, str):
            raise ValueError(f"{source}: venue_source must be an HTTPS URL")
        parsed = urlparse(evidence)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or any(char.isspace() for char in evidence)):
            raise ValueError(f"{source}: venue_source must be an HTTPS URL without credentials")
    if data.get("peer_reviewed") is True:
        venue = data.get("venue")
        if not isinstance(venue, str) or not venue.strip() or venue.strip().lower() == "arxiv" or not evidence:
            raise ValueError(f"{source}: peer_reviewed requires a publication venue and venue_source")


def normalize_survey_fields(data: dict, source: str, required: tuple[str, ...] = ()) -> dict:
    """Validate the taxonomy fields and return their normalized values.

    ``survey_section`` lists every taxonomy section the entry belongs to, primary
    first. Fields named in ``required`` must be present; other missing fields
    are omitted from the result.
    """
    missing = [
        field for field in required
        if data.get(field) is None or (isinstance(data.get(field), str) and not data[field].strip())
    ]
    if missing:
        raise ValueError(f"{source}: missing required {', '.join(missing)}")
    result: dict = {}
    for field, allowed in SURVEY_SCALAR_FIELDS:
        raw = data.get(field)
        if raw is None or raw == "":
            continue
        value = str(raw).strip()
        if value not in allowed:
            raise ValueError(f"{source}: invalid {field} {value!r}; valid values are {list(allowed)!r}")
        result[field] = value
    for field, allowed in SURVEY_LIST_FIELDS:
        if field not in data or data.get(field) is None:
            continue
        values = normalize_str_list(data.get(field))
        invalid = [value for value in values if value not in allowed]
        if invalid:
            raise ValueError(f"{source}: invalid {field} {invalid!r}; valid values are {list(allowed)!r}")
        if field == "survey_section" and not values:
            raise ValueError(f"{source}: survey_section must list at least one section when present")
        result[field] = values
    if "survey_core" in data and data.get("survey_core") is not None:
        if not isinstance(data.get("survey_core"), bool):
            raise ValueError(f"{source}: survey_core must be true or false")
        result["survey_core"] = data["survey_core"]
    return result


def normalize_authors(raw_authors: object) -> tuple[list[str], str]:
    authors = normalize_str_list(raw_authors)
    return authors, ", ".join(authors)


DATE_FIELD_NAMES = {"published_date", "added_date"}


def normalize_optional_date_string(raw_value: object, field_name: str, source: str) -> str | None:
    if field_name not in DATE_FIELD_NAMES:
        raise ValueError(f"{source}: unsupported date field {field_name!r}")
    if raw_value is None or raw_value == "":
        return None
    if isinstance(raw_value, datetime):
        value = raw_value.date().isoformat()
    elif isinstance(raw_value, date):
        value = raw_value.isoformat()
    else:
        value = str(raw_value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{source}: invalid {field_name} {value!r}; expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{source}: invalid {field_name} {value!r}; expected YYYY-MM-DD") from exc


def normalize_required_date_string(raw_value: object, field_name: str, source: str) -> str:
    value = normalize_optional_date_string(raw_value, field_name, source)
    if value is None:
        raise ValueError(f"{source}: missing required {field_name}")
    return value


def load_papers() -> list[dict]:
    papers = []
    for yaml_file in sorted(PAPERS_DIR.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue

        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        validate_publication_metadata(data, yaml_file.name)
        taxonomy = normalize_paper_taxonomy_fields(data, yaml_file.name)
        catalog_fit = taxonomy["catalog_fit"]

        links = dict(data.get("links") or {})
        validate_links(links, yaml_file.name)
        comments = normalize_comment_links(links.get("comment") or links.get("comments"))
        links = {k: v for k, v in links.items() if v and k not in {"comment", "comments"}}

        arxiv_id_from_link = get_arxiv_id_from_url(links.get("arxiv", ""))
        if arxiv_id_from_link and "alphaxiv" not in links:
            links["alphaxiv"] = f"https://www.alphaxiv.org/abs/{arxiv_id_from_link}"

        authors_list, authors_text = normalize_authors(data.get("authors", []))
        published_date = normalize_required_date_string(data.get("published_date"), "published_date", yaml_file.name)
        added_date = normalize_optional_date_string(data.get("added_date"), "added_date", yaml_file.name)
        must_read = normalize_must_read_flag(data.get("must_read"))
        survey_fields = normalize_survey_fields(data, yaml_file.name, REQUIRED_PAPER_SURVEY_FIELDS)

        paper = dict(data)
        for field in SURVEY_FIELDS:
            paper.pop(field, None)
        paper.update(survey_fields)
        paper["id"] = yaml_file.stem
        paper["source_file"] = yaml_file.name
        paper["source_path"] = f"papers/{yaml_file.name}"
        paper["entry_type"] = "paper"
        if catalog_fit == "adjacent":
            paper["catalog_fit"] = catalog_fit
        else:
            paper.pop("catalog_fit", None)
        paper["links"] = links
        paper["authors_list"] = authors_list
        paper["authors"] = authors_text
        paper["published_date"] = published_date
        if must_read:
            paper["must_read"] = True
        else:
            paper.pop("must_read", None)
        if added_date is not None:
            paper["added_date"] = added_date
        else:
            paper.pop("added_date", None)
        paper["venueClass"] = normalize_venue_class(str(paper.get("venue", "")), "paper")

        file_arxiv_id = get_arxiv_id(yaml_file.name)
        if file_arxiv_id:
            paper["arxiv_id"] = file_arxiv_id
        elif arxiv_id_from_link:
            paper["arxiv_id"] = arxiv_id_from_link

        if comments:
            paper["community_comments"] = comments
            paper["comments"] = comments

        papers.append(paper)
    return papers


# Blogs live in a separate flat section. They list the taxonomy sections they discuss
# but carry none of the paper-only design axes.
def load_blogs() -> list[dict]:
    if not BLOGS_DIR.exists():
        return []

    blogs = []
    for yaml_file in sorted(BLOGS_DIR.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue

        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        links = dict(data.get("links") or {})
        validate_blog_links(links, yaml_file.name)
        comments = normalize_comment_links(links.get("comment") or links.get("comments"))
        links = {k: v for k, v in links.items() if v and k not in {"comment", "comments"}}

        authors_list, authors_text = normalize_authors(data.get("authors", []))
        reject_retired_fields(data, yaml_file.name)
        extra_axes = [field for field in SURVEY_FIELDS if field != "survey_section" and field in data]
        if extra_axes:
            raise ValueError(f"{yaml_file.name}: blogs only use survey_section, not {', '.join(extra_axes)}")
        survey_fields = normalize_survey_fields(data, yaml_file.name, ("survey_section",))
        published_date = normalize_required_date_string(data.get("published_date"), "published_date", yaml_file.name)
        added_date = normalize_optional_date_string(data.get("added_date"), "added_date", yaml_file.name)
        must_read = normalize_must_read_flag(data.get("must_read"))

        blog = dict(data)
        blog.update(survey_fields)
        blog["id"] = yaml_file.stem
        blog["source_file"] = yaml_file.name
        blog["source_path"] = f"blogs/{yaml_file.name}"
        blog["entry_type"] = "blog"
        blog["links"] = links
        blog["authors_list"] = authors_list
        blog["authors"] = authors_text
        blog["published_date"] = published_date
        if must_read:
            blog["must_read"] = True
        else:
            blog.pop("must_read", None)
        if added_date is not None:
            blog["added_date"] = added_date
        else:
            blog.pop("added_date", None)
        blog["venueClass"] = normalize_venue_class(str(blog.get("venue", "")), "blog")

        if comments:
            blog["community_comments"] = comments
            blog["comments"] = comments

        blogs.append(blog)
    return blogs


def split_markdown_frontmatter(text: str, source: str) -> tuple[dict, str]:
    """Return YAML frontmatter metadata and the Markdown body for a briefing file."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError(f"{source}: frontmatter starts with --- but has no closing ---")
    frontmatter_text = text[4:end].strip()
    body_start = end + len("\n---")
    if text[body_start:body_start + 2] == "\r\n":
        body_start += 2
    elif text[body_start:body_start + 1] == "\n":
        body_start += 1
    metadata = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{source}: frontmatter must be a mapping")
    return metadata, text[body_start:].strip()


def normalize_briefing_date(raw_value: object, source: str) -> str:
    """Normalize the required briefing date from YAML or string input."""
    if raw_value is None or raw_value == "":
        raise ValueError(f"{source}: missing required date")
    if isinstance(raw_value, datetime):
        value = raw_value.date().isoformat()
    elif isinstance(raw_value, date):
        value = raw_value.isoformat()
    else:
        value = str(raw_value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{source}: invalid date {value!r}; expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{source}: invalid date {value!r}; expected YYYY-MM-DD") from exc


def normalize_briefing_candidates(raw_candidates: object, source: str) -> list[dict]:
    """Normalize optional candidate rows from a daily briefing frontmatter block."""
    if raw_candidates is None:
        return []
    if not isinstance(raw_candidates, list):
        raise ValueError(f"{source}: candidates must be a list")
    candidates = []
    for idx, raw_candidate in enumerate(raw_candidates, start=1):
        if not isinstance(raw_candidate, dict):
            raise ValueError(f"{source}: candidates[{idx}] must be a mapping")
        candidate = {
            str(key): str(value).strip()
            for key, value in raw_candidate.items()
            if value is not None and str(value).strip()
        }
        if candidate:
            candidates.append(candidate)
    return candidates


def load_briefings() -> list[dict]:
    """Load daily Markdown briefings stored as briefings/YYYY/MM/YYYY-MM-DD.md."""
    if not BRIEFINGS_DIR.exists():
        return []

    briefings = []
    for markdown_file in sorted(BRIEFINGS_DIR.glob("*/*/*.md")):
        if markdown_file.name.startswith("_"):
            continue
        try:
            source_path = markdown_file.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            source_path = markdown_file.relative_to(BRIEFINGS_DIR.parent).as_posix()
        metadata, body = split_markdown_frontmatter(markdown_file.read_text(encoding="utf-8"), source_path)
        briefing_date = normalize_briefing_date(metadata.get("date") or markdown_file.stem, source_path)
        expected_relative_path = f"briefings/{briefing_date[:4]}/{briefing_date[5:7]}/{briefing_date}.md"
        if source_path != expected_relative_path:
            raise ValueError(f"{source_path}: expected path {expected_relative_path}")

        highlights = normalize_str_list(metadata.get("highlights", []))
        candidates = normalize_briefing_candidates(metadata.get("candidates", []), source_path)
        briefing = {
            "date": briefing_date,
            "title": str(metadata.get("title") or f"Daily Loop-Model Watch — {briefing_date}").strip(),
            "status": str(metadata.get("status") or "ok").strip(),
            "summary": str(metadata.get("summary") or "").strip(),
            "highlights": highlights,
            "candidates": candidates,
            "content": body,
            "source_path": source_path,
        }
        briefings.append(briefing)

    return sorted(briefings, key=lambda item: item["date"], reverse=True)


# Must match the pattern in index.html's restoreDerivedLinks().
BROWSER_ARXIV_LINK_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?")


def compact_browser_links(links: dict) -> dict:
    """Drop an AlphaXiv link that index.html can rebuild exactly from the arXiv link.

    The link is omitted only when it equals the derived URL and directly follows
    ``arxiv``, so the browser restores both the value and the badge order.
    """
    match = BROWSER_ARXIV_LINK_RE.search(str(links.get("arxiv") or ""))
    arxiv_id = match.group(1) if match else None
    if not arxiv_id or links.get("alphaxiv") != f"https://www.alphaxiv.org/abs/{arxiv_id}":
        return dict(links)
    keys = list(links)
    if keys.index("alphaxiv") != keys.index("arxiv") + 1:
        return dict(links)
    return {key: value for key, value in links.items() if key != "alphaxiv"}


def serialize_browser_entry(entry: dict) -> dict:
    """Return a catalog entry containing only fields consumed by index.html.

    The projection avoids redundant copies: ``authors_list`` replaces the joined
    ``authors`` string, ``community_comments`` replaces its ``comments`` alias,
    ``entry_type`` is emitted only for non-paper entries, and a derivable AlphaXiv
    link is omitted. index.html restores each of these in ``preparePaperRecord``.
    """
    browser_fields = (
        "id",
        "entry_type",
        "title",
        "authors_list",
        "venue",
        "venueClass",
        "peer_reviewed",
        "venue_source",
        "year",
        "published_date",
        "added_date",
        "desc",
        "links",
        "catalog_fit",
        "survey_section",
        "loop_topology",
        "sharing",
        "depth_control",
        "claims",
        "comparison",
        "survey_core",
        "must_read",
        "citations",
        "github_stars",
        "community_comments",
    )
    browser_entry = {field: entry[field] for field in browser_fields if field in entry}
    if browser_entry.get("entry_type") == "paper":
        del browser_entry["entry_type"]
    if "authors_list" not in browser_entry and "authors" in entry:
        browser_entry["authors"] = entry["authors"]
    if "community_comments" not in browser_entry and "comments" in entry:
        browser_entry["community_comments"] = entry["comments"]
    if isinstance(browser_entry.get("links"), dict):
        browser_entry["links"] = compact_browser_links(browser_entry["links"])
    return browser_entry


def serialize_browser_briefing_candidate(candidate: dict) -> dict:
    """Return a new candidate mapping containing only fields rendered by index.html."""
    browser_fields = ("id", "title", "verdict", "url")
    return {field: candidate[field] for field in browser_fields if field in candidate}


def serialize_browser_briefings(briefings: list[dict]) -> list[dict]:
    """Return an isolated latest briefing containing only fields rendered by index.html."""
    if not briefings:
        return []

    latest = max(briefings, key=lambda item: item.get("date", ""))
    scalar_fields = (
        "date",
        "title",
        "status",
        "summary",
        "source_path",
    )
    browser_briefing = {
        field: latest[field]
        for field in scalar_fields
        if field in latest
    }
    if "highlights" in latest:
        browser_briefing["highlights"] = list(latest["highlights"])
    if "candidates" in latest:
        browser_briefing["candidates"] = [
            serialize_browser_briefing_candidate(candidate)
            for candidate in latest["candidates"]
        ]
    return [browser_briefing]


def render_latest_briefing_page(briefings: list[dict]) -> dict:
    """Return the newest briefing as the reading-page payload written to briefing-latest.json.

    Keys always appear in ``BRIEFING_PAGE_FIELDS`` order. Without any briefing the
    payload keeps every key, with ``None`` for the scalar identity fields and empty
    text and lists, so the browser can show a friendly empty state.
    """
    if not briefings:
        return {
            "date": None,
            "title": None,
            "status": None,
            "summary": "",
            "highlights": [],
            "candidates": [],
            "source_path": None,
            "body_markdown": "",
        }
    latest = max(briefings, key=lambda item: item.get("date", ""))
    page = {
        "date": latest["date"],
        "title": latest.get("title", ""),
        "status": latest.get("status", ""),
        "summary": latest.get("summary", ""),
        "highlights": list(latest.get("highlights") or []),
        "candidates": [serialize_browser_briefing_candidate(candidate) for candidate in latest.get("candidates") or []],
        "source_path": latest.get("source_path", ""),
        "body_markdown": latest.get("content", ""),
    }
    return {field: page[field] for field in BRIEFING_PAGE_FIELDS}


def render_latest_briefing_text(briefings: list[dict]) -> str:
    """Serialize the latest-briefing page deterministically, with a trailing newline."""
    return json.dumps(render_latest_briefing_page(briefings), ensure_ascii=False, indent=2) + "\n"


def write_latest_briefing(briefings: list[dict]) -> str:
    """Write briefing-latest.json only when its content changes and return its 12-character version."""
    text = render_latest_briefing_text(briefings)
    out_path = JSON_OUT.parent / BRIEFING_LATEST_FILENAME
    try:
        current = out_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = None
    if current != text:
        out_path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def build_json(papers: list[dict], blogs: list[dict], briefings: list[dict] | None = None) -> None:
    briefings = sorted(briefings or [], key=lambda item: item.get("date", ""), reverse=True)
    latest_briefing_version = write_latest_briefing(briefings)
    generated_at = datetime.now(timezone.utc)
    payload = {
        "meta": {
            "total": len(papers) + len(blogs),
            "paper_total": len(papers),
            "blog_total": len(blogs),
            "briefing_total": len(briefings),
            "latest_briefing_date": briefings[0]["date"] if briefings else None,
            "latest_briefing_version": latest_briefing_version,
            "generated": generated_at.isoformat(),
            "generated_local_date": generated_at.astimezone(CATALOG_TIME_ZONE).date().isoformat(),
            "taxonomy_note": TAXONOMY_NOTE,
            "blog_section_title": BLOG_SECTION_TITLE,
            "blog_section_desc": BLOG_SECTION_DESC,
            "briefing_section_title": DAILY_BRIEFING_SECTION_TITLE,
            "briefing_section_desc": DAILY_BRIEFING_SECTION_DESC,
        },
        "survey_taxonomy": render_survey_taxonomy(),
        "paper_chunks": write_paper_chunks([serialize_browser_entry(paper) for paper in papers]),
        "blogs": [serialize_browser_entry(blog) for blog in blogs],
        "briefings": serialize_browser_briefings(briefings),
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        f"✓ papers.json  — {len(papers)} papers in {len(payload['paper_chunks'])} chunks, "
        f"{len(blogs)} blogs, {len(briefings)} briefings"
    )


def render_survey_taxonomy() -> dict:
    """Return the controlled taxonomy vocabulary consumed by index.html and submit.html."""
    return {
        "parts": [{"id": part_id, "title": title} for part_id, title in SURVEY_PARTS],
        "chapters": [
            {"number": number, "part": part_id, "title": title}
            for number, part_id, title in SURVEY_CHAPTERS
        ],
        "sections": [
            {"id": section_id, "number": number, "chapter": number.split(".")[0], "title": title}
            for section_id, number, title in SURVEY_SECTIONS
        ],
        "axes": {
            field: {"label": AXIS_LABELS[field], "values": list(values)}
            for field, values in (
                ("loop_topology", VALID_LOOP_TOPOLOGIES),
                ("sharing", VALID_SHARING_SCHEMES),
                ("depth_control", VALID_DEPTH_CONTROLS),
                ("claims", VALID_CLAIMS),
                ("comparison", VALID_COMPARISONS),
            )
        },
    }


def count_field_values(entries: list[dict], field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for entry in entries:
        value = entry.get(field)
        if isinstance(value, list):
            counts.update(value)
        elif value:
            counts[value] += 1
    return counts


def write_paper_chunks(entries: list[dict]) -> list[dict]:
    """Write browser paper records as fixed-size chunks and return their manifest rows.

    Chunks keep the catalog order, so new arXiv IDs usually land in the last chunk.
    Each row carries a content hash that index.html uses to bypass stale caches.
    Chunk files left over from a larger catalog are removed.
    """
    chunk_dir = JSON_OUT.parent / PAPER_CHUNK_DIRNAME
    chunk_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for index, start in enumerate(range(0, len(entries), PAPER_CHUNK_SIZE)):
        chunk = entries[start:start + PAPER_CHUNK_SIZE]
        raw = json.dumps({"papers": chunk}, ensure_ascii=False, separators=(",", ":"))
        relative_path = f"{PAPER_CHUNK_DIRNAME}/papers-{index:03d}.json"
        (JSON_OUT.parent / relative_path).write_text(raw, encoding="utf-8")
        rows.append({
            "path": relative_path,
            "count": len(chunk),
            "version": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12],
        })
    expected = {row["path"] for row in rows}
    for stale in sorted(chunk_dir.glob("papers-*.json")):
        if f"{PAPER_CHUNK_DIRNAME}/{stale.name}" not in expected:
            stale.unlink()
    return rows


def render_submission_metadata(papers: list[dict], blogs: list[dict]) -> dict:
    """Return the deterministic minimal path and tag inventory used by submit.html."""
    entries = [*papers, *blogs]
    existing_paths = sorted({str(entry["source_path"]) for entry in entries})

    def counted_inventory(counter: Counter[str], labels: tuple[str, ...] | None = None) -> list[dict]:
        """Return counted tag rows sorted by descending count and deterministic label order."""
        inventory_labels = labels if labels is not None else tuple(counter)
        return [
            {"label": label, "count": counter[label]}
            for label in sorted(
                inventory_labels,
                key=lambda label: (-counter[label], label.lower(), label),
            )
        ]

    inventories = {"survey_section": counted_inventory(count_field_values(entries, "survey_section"), VALID_SURVEY_SECTIONS)}
    for field, values in (*SURVEY_SCALAR_FIELDS, *SURVEY_LIST_FIELDS[1:]):
        inventories[field] = counted_inventory(count_field_values(papers, field), values)
    return {
        "existing_paths": existing_paths,
        "survey_taxonomy": render_survey_taxonomy(),
        "inventories": inventories,
    }


def build_submission_metadata(papers: list[dict], blogs: list[dict]) -> None:
    """Write submission-meta.json for the lightweight submission-page bootstrap."""
    payload = render_submission_metadata(papers, blogs)
    SUBMISSION_META_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ submission-meta.json — {len(payload['existing_paths'])} existing source paths")


def render_tags_reference_text(papers: list[dict], blogs: list[dict]) -> str:
    """Render TAGS.md: the taxonomy vocabulary with current usage counts."""
    entries = [*papers, *blogs]
    section_counts = count_field_values(entries, "survey_section")
    primary_counts: Counter[str] = Counter(
        section for section in (primary_section(entry) for entry in entries) if section
    )
    lines = [
        "# Taxonomy vocabulary",
        "",
        "Every paper and blog is classified with the controlled vocabulary below, which follows the chapters of the "
        "repo's topic map. There are no free-form tags; a value that is not listed here is a taxonomy change and "
        "needs the maintainer. See [TAXONOMY.md](TAXONOMY.md) for how to choose values.",
        "",
        "This file is auto-generated from `papers/*.yaml` and `blogs/*.yaml` by `scripts/build.py`.",
        "",
        "## Taxonomy sections (`survey_section`)",
        "",
        "List every section the entry belongs to; the first entry is its primary section. Counts are primary / any.",
        "",
    ]
    chapter_titles = {number: title for number, _, title in SURVEY_CHAPTERS}
    part_titles = dict(SURVEY_PARTS)
    current_part = current_chapter = None
    for section_id, number, title in SURVEY_SECTIONS:
        chapter = number.split(".")[0]
        part = next(part_id for num, part_id, _ in SURVEY_CHAPTERS if num == chapter)
        if part != current_part:
            if lines[-1] != "":
                lines.append("")
            lines.extend([f"### {part_titles[part]}", ""])
            current_part = part
        if chapter != current_chapter:
            if current_chapter is not None and lines[-1] != "":
                lines.append("")
            lines.extend([f"**§{chapter} {chapter_titles[chapter]}**", ""])
            current_chapter = chapter
        lines.append(
            f"- `{section_id}` — §{number} {title} "
            f"({primary_counts.get(section_id, 0)} / {section_counts.get(section_id, 0)})"
        )
    lines.append("")
    for field, allowed, intro in (
        ("loop_topology", VALID_LOOP_TOPOLOGIES, "Where the loop sits in the network (one value, papers only)."),
        ("sharing", VALID_SHARING_SCHEMES, "How parameters are shared across iterations (one value, papers only)."),
        ("depth_control", VALID_DEPTH_CONTROLS, "How the number of iterations is decided (one value, papers only)."),
        ("claims", VALID_CLAIMS, "What the paper argues looping buys or costs (list, papers only)."),
        ("comparison", VALID_COMPARISONS, "Which quantity is held fixed when the paper compares looped and untied models (list; empty when there is no such comparison)."),
    ):
        counts = count_field_values(papers, field)
        lines.extend([f"## {AXIS_LABELS[field]} (`{field}`)", "", intro, ""])
        lines.extend(f"- `{value}` ({counts.get(value, 0)})" for value in allowed)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_tags_reference(papers: list[dict], blogs: list[dict]) -> None:
    TAGS_OUT.write_text(render_tags_reference_text(papers, blogs), encoding="utf-8")
    print(f"✓ TAGS.md      — {len(SURVEY_SECTIONS)} sections, {len(papers) + len(blogs)} classified entries")


def primary_link(links: dict) -> str:
    return (
        links.get("blog")
        or links.get("arxiv")
        or links.get("paper")
        or links.get("openreview")
        or links.get("project")
        or links.get("github")
        or links.get("hf")
        or links.get("twitter")
        or "#"
    )


def link_badge_parts(key: str, url: str) -> tuple[str, str, str]:
    if key == "github":
        repo_slug = _repo_slug_from_url(url)
        stargazers_url = _github_stargazers_url(url)
        if repo_slug and stargazers_url:
            badge_url = f"https://img.shields.io/github/stars/{quote(repo_slug, safe='/')}?style=social"
            return ("GitHub stars", badge_url, stargazers_url)

    if key == "project":
        return ("Website", "https://img.shields.io/badge/Website-Link-blue", url)

    if key == "openreview" or (key == "paper" and _is_openreview_url(url)):
        return ("OpenReview", "https://img.shields.io/badge/OpenReview-Paper-8E44AD.svg", url)

    label, color = LINK_BADGES[key]
    message = badge_message_for_link(key, url) or "link"
    badge_url = (
        f"https://img.shields.io/badge/{quote(shields_escape(label), safe='')}-"
        f"{quote(shields_escape(message), safe='')}-{color}.svg"
    )
    return (label, badge_url, url)


def render_link_badge(key: str, url: str) -> str:
    label, badge_url, target_url = link_badge_parts(key, url)
    return f"[![{label}]({badge_url})]({target_url})"


def render_link_badge_html(key: str, url: str, linked: bool = True) -> str:
    label, badge_url, target_url = link_badge_parts(key, url)
    img_html = f'<img alt="{escape(label, quote=True)}" src="{escape(badge_url, quote=True)}">'
    if not linked:
        return img_html
    return f'<a href="{escape(target_url, quote=True)}">{img_html}</a>'


def iter_ordered_link_items(links: dict):
    ordered = [
        ("blog", "Blog"),
        ("arxiv", "arXiv"),
        ("alphaxiv", "AlphaXiv"),
        ("paper", "Paper"),
        ("github", "GitHub stars"),
        ("readme", "README"),
        ("hf", "HuggingFace"),
        ("openreview", "OpenReview"),
        ("project", "Website"),
        ("twitter", "Twitter"),
    ]
    paper_is_openreview = _is_openreview_url(links.get("paper") or "")
    for key, _label in ordered:
        if not links.get(key):
            continue
        if key == "openreview" and paper_is_openreview:
            continue
        yield key, links[key]


def render_link_list(links: dict) -> str:
    return " ".join(render_link_badge(key, url) for key, url in iter_ordered_link_items(links))


def render_link_list_html(links: dict, linked: bool = True) -> str:
    return " ".join(render_link_badge_html(key, url, linked=linked) for key, url in iter_ordered_link_items(links))


def _readme_display_date(published_date: object) -> str:
    """Format a normalized publication date for README entry prefixes."""
    value = str(published_date or "").strip()
    if not value:
        return ""
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError:
        return ""
    return parsed_date.strftime("%m/%d/%Y")


def _paper_to_md(paper: dict) -> str:
    title = paper.get("title", "Untitled")
    authors = paper.get("authors", "")
    venue = paper.get("venue", "")
    year = paper.get("year", "")
    desc = (paper.get("desc") or "").strip()
    sections = paper.get("survey_section") or []
    comments = paper.get("community_comments") or []
    links = paper.get("links", {})

    venue_year = f"{venue} {year}" if venue and venue != "arXiv" else str(year)
    summary_link_html = render_link_list_html(links, linked=True)

    summary_parts = []
    display_date = _readme_display_date(paper.get("published_date"))
    if display_date:
        summary_parts.append(f"[{display_date}]")
    if paper.get("must_read"):
        summary_parts.append("🌟")
    if paper.get("catalog_fit") == "adjacent":
        summary_parts.append("⚠️ Adjacent work")
    summary_parts.append(f"<strong>{escape(title)}</strong>")
    if summary_link_html:
        summary_parts.append(summary_link_html)

    lines = ["<details>", f"  <summary>{' '.join(summary_parts)}</summary>"]

    detail_lines = []
    metadata = " · ".join(str(part).strip() for part in (authors, venue_year) if str(part).strip())
    if metadata:
        detail_lines.append(f"  <div><strong>Authors:</strong> {escape(metadata)}</div>")
    if paper.get("catalog_fit") == "adjacent":
        detail_lines.append(f"  <div><strong>Catalog fit:</strong> {escape(ADJACENT_SCOPE_NOTE)}</div>")
    if sections:
        detail_lines.append(
            f"  <div><strong>Sections:</strong> {escape(' · '.join(section_label(s) for s in sections))}</div>"
        )
    design = [
        f"{AXIS_LABELS[field]}: {paper[field]}"
        for field in ("loop_topology", "sharing", "depth_control")
        if paper.get(field)
    ]
    if design:
        detail_lines.append(f"  <div><strong>Design:</strong> {escape(' · '.join(design))}</div>")
    if comments:
        cc_links = [
            f'<a href="{escape(item["url"])}">{escape(item["label"])}</a>'
            for item in comments
            if item.get("url") and item.get("label")
        ]
        if cc_links:
            detail_lines.append(f"  <div><strong>Community Comments:</strong> {' '.join(cc_links)}</div>")
    if desc:
        detail_lines.append(f"  <div><strong>TL;DR:</strong> {escape(desc)}</div>")

    lines.extend(detail_lines)
    lines.append("  </details>")
    return "\n".join(lines)


def render_readme_fragment(template_text: str, meta: dict) -> str:
    return (
        template_text
        .replace("{{PUBLIC_INDEX_URL}}", meta["public_pages_base"] + "/index.html")
        .replace("{{PUBLIC_SUBMIT_URL}}", meta["public_pages_base"] + "/submit.html")
    )


README_LATEST_COUNT = 10
README_MOST_CITED_COUNT = 10
README_LINK_LABELS = (
    ("blog", "Read"),
    ("arxiv", "arXiv"),
    ("openreview", "OpenReview"),
    ("paper", "Paper"),
    ("github", "Code"),
    ("hf", "HF"),
    ("project", "Project"),
)
def _readme_date_rank(value: object) -> int:
    """Return a sortable ordinal for a YYYY-MM-DD value, or 0 when it is missing."""
    try:
        return date.fromisoformat(str(value or "").strip()).toordinal()
    except ValueError:
        return 0


def _readme_cell(text: object) -> str:
    """Escape text for a single Markdown table cell."""
    return escape(str(text or "")).replace("|", "&#124;").replace("\n", " ")


def _readme_short_date(value: object) -> str:
    rank = _readme_date_rank(value)
    return date.fromordinal(rank).strftime("%Y-%m-%d") if rank else ""


def _readme_venue(entry: dict) -> str:
    venue = str(entry.get("venue") or "").strip()
    year = str(entry.get("year") or "").strip()
    if venue and venue != "arXiv":
        return f"{venue} {year}".strip()
    return year


def _readme_link_cell(entry: dict) -> str:
    """Render compact text links (arXiv · Code ★N · …) instead of badge images."""
    links = entry.get("links") or {}
    parts = []
    for key, label in README_LINK_LABELS:
        url = links.get(key)
        if not url:
            continue
        if key in ("openreview", "paper") and links.get("arxiv"):
            continue
        text = label
        if key == "github" and isinstance(entry.get("github_stars"), int) and entry["github_stars"] > 0:
            text = f"{label} ★{entry['github_stars']:,}"
        parts.append(f'<a href="{escape(url)}">{text}</a>')
    return " · ".join(parts)


def _readme_title_cell(entry: dict) -> str:
    marks = []
    if entry.get("must_read"):
        marks.append("🌟")
    if entry.get("catalog_fit") == "adjacent":
        marks.append("⚠️")
    title = f"<b>{_readme_cell(entry.get('title', 'Untitled'))}</b>"
    return " ".join(marks + [title])


def _readme_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(":--" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def build_readme(papers: list[dict], blogs: list[dict], repo_meta: dict) -> None:
    """Write README.md as a compact front page; the full catalog lives in the browser."""
    header = render_readme_fragment(HEADER_FILE.read_text(encoding="utf-8").rstrip(), repo_meta)
    footer = render_readme_fragment(FOOTER_FILE.read_text(encoding="utf-8").rstrip(), repo_meta)
    browser_url = repo_meta["public_pages_base"] + "/index.html"

    stats_line = (
        f"<p align=\"center\"><b>{len(papers)} papers</b> · {len(SURVEY_SECTIONS)} sections"
        + (f" · <b>{len(blogs)} blogs</b>" if blogs else "")
        + f" · <a href=\"{escape(browser_url)}\">browse all →</a></p>"
    )

    sections = ["## At a glance", "", stats_line]

    section_counts = count_field_values(papers, "survey_section")
    primary_counts: Counter[str] = Counter(primary_section(p) for p in papers)
    chapter_titles = {number: title for number, _, title in SURVEY_CHAPTERS}
    map_rows = []
    for section_id, number, title in SURVEY_SECTIONS:
        chapter = number.split(".")[0]
        map_rows.append([
            f"§{number}",
            _readme_cell(f"{chapter_titles[chapter]} › {title}"),
            str(primary_counts.get(section_id, 0)),
            str(section_counts.get(section_id, 0)),
        ])
    sections += [
        "",
        "## 🗺️ Topic map",
        "",
        "The catalog is organized into chapters and sections. A paper is counted once under its primary "
        "section and again under every other section it belongs to.",
        "",
        "<details>",
        "<summary>Papers per section</summary>",
        "",
        _readme_table(["§", "Section", "Primary", "Any"], map_rows),
        "",
        "</details>",
    ]

    anchors = [paper for paper in papers if paper.get("survey_core") or paper.get("must_read")]
    anchors.sort(key=lambda p: (_readme_date_rank(p.get("published_date")), str(p.get("title", "")).lower()))
    if anchors:
        rows = [
            [
                _readme_title_cell(p),
                _readme_cell(_readme_venue(p)),
                _readme_cell(p.get("loop_topology") or ""),
                _readme_link_cell(p),
            ]
            for p in anchors
        ]
        sections += [
            "",
            "## 🌟 Start here",
            "",
            "Core references for loop models, plus the ones the maintainer marks as must-read.",
            "",
            _readme_table(["Paper", "Venue", "Loop", "Links"], rows),
        ]

    latest = sorted(
        papers,
        key=lambda p: (
            -_readme_date_rank(p.get("added_date")),
            -_readme_date_rank(p.get("published_date")),
            str(p.get("title", "")).lower(),
        ),
    )[:README_LATEST_COUNT]
    if latest:
        rows = [
            [
                _readme_cell(_readme_short_date(p.get("added_date"))),
                _readme_title_cell(p),
                _readme_cell(f"§{SURVEY_SECTION_NUMBERS[primary_section(p)]}" if primary_section(p) else ""),
                _readme_link_cell(p),
            ]
            for p in latest
        ]
        sections += [
            "",
            "## 🆕 Latest additions",
            "",
            _readme_table(["Added", "Paper", "§", "Links"], rows),
            "",
            f"<sub>A daily watch adds new arXiv papers. The <a href=\"{escape(browser_url)}\">browser</a> has every paper and each day's briefing.</sub>",
        ]

    cited = [p for p in papers if isinstance(p.get("citations"), int) and p["citations"] > 0]
    cited.sort(key=lambda p: (-p["citations"], str(p.get("title", "")).lower()))
    cited = cited[:README_MOST_CITED_COUNT]
    if cited:
        rows = [
            [
                _readme_title_cell(p),
                _readme_cell(_readme_venue(p)),
                f"{p['citations']:,}",
                _readme_link_cell(p),
            ]
            for p in cited
        ]
        sections += [
            "",
            "## 🔥 Most cited",
            "",
            _readme_table(["Paper", "Venue", "Citations", "Links"], rows),
        ]

    if blogs:
        ordered_blogs = sorted(
            blogs,
            key=lambda b: (-_readme_date_rank(b.get("published_date")), str(b.get("title", "")).lower()),
        )
        rows = [
            [
                _readme_cell(_readme_short_date(b.get("published_date"))),
                _readme_title_cell(b),
                _readme_cell(b.get("venue") or ""),
                _readme_link_cell(b),
            ]
            for b in ordered_blogs
        ]
        sections += [
            "",
            f"## ✍️ {BLOG_SECTION_TITLE}",
            "",
            "Long-form technical posts on loop models.",
            "",
            _readme_table(["Date", "Post", "Where", "Links"], rows),
        ]

    auto_note = (
        "<!-- AUTO-GENERATED by scripts/build.py on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — "
        "DO NOT EDIT the sections below manually. Edit papers/*.yaml or blogs/*.yaml and run `python3 scripts/build.py` instead. -->"
    )

    README_OUT.write_text("\n\n".join([header, auto_note, "\n".join(sections), footer]) + "\n", encoding="utf-8")
    print(f"✓ README.md    — {len(papers)} papers, {len(blogs)} blogs")


def build() -> None:
    repo_meta = load_repo_meta()
    papers = load_papers()
    blogs = load_blogs()
    briefings = load_briefings()
    build_json(papers, blogs, briefings)
    build_submission_metadata(papers, blogs)
    build_readme(papers, blogs, repo_meta)
    build_tags_reference(papers, blogs)
    build_repo_meta_js(repo_meta)
    build_issue_template_config(repo_meta)

    chapter_counts = Counter(chapter_of(primary_section(paper)) for paper in papers)
    for number, _, title in SURVEY_CHAPTERS:
        if chapter_counts.get(number):
            print(f"    §{number} {title}: {chapter_counts[number]}")
    if blogs:
        print(f"    {BLOG_SECTION_TITLE}: {len(blogs)}")


if __name__ == "__main__":
    build()
