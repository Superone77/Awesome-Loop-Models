#!/usr/bin/env python3
"""Generate a paper YAML stub from an arXiv ID for this repository."""

from __future__ import annotations

import argparse
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import (  # noqa: E402
    VALID_CLAIMS,
    VALID_COMPARISONS,
    VALID_DEPTH_CONTROLS,
    VALID_LOOP_TOPOLOGIES,
    VALID_SHARING_SCHEMES,
    VALID_SURVEY_SECTIONS,
)

NS = {"a": "http://www.w3.org/2005/Atom"}
ROOT = Path(__file__).resolve().parents[1]
PAPERS_DIR = ROOT / "papers"


def yaml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def clean_text(text: str) -> str:
    return " ".join((text or "").split())


def normalize_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError as exc:
        raise SystemExit(f"Invalid {field_name}: {value!r} (expected YYYY-MM-DD)") from exc


def extract_iso_date(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    raw_date = raw.split("T", 1)[0]
    try:
        return date.fromisoformat(raw_date).isoformat()
    except ValueError:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None


def wrap_desc(desc: str) -> str:
    wrapped = textwrap.wrap(desc, width=88)
    if not wrapped:
        return "''"
    if len(wrapped) == 1:
        return wrapped[0]
    return wrapped[0] + "\n  " + "\n  ".join(wrapped[1:])


def fetch_arxiv_entry(arxiv_id: str) -> dict:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": arxiv_id})
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = resp.read()
    except Exception:
        import subprocess

        payload = subprocess.check_output(["curl", "-fsSL", url], timeout=30)
    root = ET.fromstring(payload)
    entry = root.find("a:entry", NS)
    if entry is None:
        raise SystemExit(f"No arXiv entry found for {arxiv_id}")
    published = entry.findtext("a:published", default="", namespaces=NS)
    published_date = extract_iso_date(published)
    if not published_date:
        raise SystemExit(f"Missing usable published_date in arXiv metadata for {arxiv_id}: {published!r}")
    return {
        "title": clean_text(entry.findtext("a:title", default="", namespaces=NS)),
        "authors": [a.findtext("a:name", default="", namespaces=NS) for a in entry.findall("a:author", NS)],
        "year": int(published_date[:4]),
        "published_date": published_date,
        "summary": clean_text(entry.findtext("a:summary", default="", namespaces=NS)),
        "id": entry.findtext("a:id", default="", namespaces=NS).split("/abs/")[-1].split("v")[0],
    }


def first_sentence(summary: str) -> str:
    parts = summary.split(". ")
    sentence = parts[0].strip()
    if not sentence.endswith("."):
        sentence += "."
    return sentence


def render_yaml(data: dict, args: argparse.Namespace) -> str:
    lines: list[str] = []
    lines.append(f"title: {yaml_quote(data['title'])}")
    lines.append("authors:")
    for author in data["authors"]:
        lines.append(f"- {yaml_quote(author)}")
    lines.append(f"year: {data['year']}")
    if data.get("published_date"):
        lines.append(f"published_date: {yaml_quote(data['published_date'])}")
    if args.added_date:
        lines.append(f"added_date: {yaml_quote(args.added_date)}")
    lines.append(f"venue: {args.venue}")
    if args.catalog_fit:
        lines.append(f"catalog_fit: {args.catalog_fit}")
    lines.append("survey_section:")
    for item in dict.fromkeys(args.survey_sections):
        lines.append(f"- {item}")
    lines.append(f"loop_topology: {args.loop_topology}")
    lines.append(f"sharing: {args.sharing}")
    lines.append(f"depth_control: {args.depth_control}")
    for field, values in (("claims", args.claims), ("comparison", args.comparison)):
        unique = list(dict.fromkeys(values))
        if unique:
            lines.append(f"{field}:")
            lines.extend(f"- {item}" for item in unique)
        else:
            lines.append(f"{field}: []")
    if args.survey_core:
        lines.append("survey_core: true")
    desc = args.desc or first_sentence(data["summary"])
    lines.append(f"desc: {wrap_desc(desc)}")
    lines.append("links:")
    lines.append(f"  arxiv: https://arxiv.org/abs/{data['id']}")
    lines.append("citations: 0")
    if args.metrics_updated:
        lines.append(f"metrics_updated: {yaml_quote(args.metrics_updated)}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("arxiv_id", help="arXiv ID, e.g. 2604.11791")
    p.add_argument("--venue", default="arXiv")
    p.add_argument(
        "--section",
        action="append",
        required=True,
        choices=VALID_SURVEY_SECTIONS,
        dest="survey_sections",
        help="Taxonomy section id (survey_section); repeat for several, primary first",
    )
    p.add_argument("--loop-topology", required=True, choices=VALID_LOOP_TOPOLOGIES)
    p.add_argument("--sharing", required=True, choices=VALID_SHARING_SCHEMES)
    p.add_argument("--depth-control", required=True, choices=VALID_DEPTH_CONTROLS)
    p.add_argument("--claim", action="append", default=[], choices=VALID_CLAIMS, dest="claims")
    p.add_argument("--comparison", action="append", default=[], choices=VALID_COMPARISONS)
    p.add_argument("--survey-core", action="store_true", help="Mark the paper as survey_core: true")
    p.add_argument("--catalog-fit", choices=["adjacent"], help="Emit catalog_fit: adjacent (strict is the default)")
    p.add_argument("--desc", help="Curated one-line description; defaults to first abstract sentence")
    p.add_argument("--added-date", default=date.today().isoformat(), help="Repo intake date in YYYY-MM-DD; defaults to today")
    p.add_argument("--metrics-updated", help="Optional YYYY-MM-DD stamp")
    p.add_argument("--output", help="Optional custom output path")
    p.add_argument("--force", action="store_true", help="Overwrite existing file")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.added_date:
        args.added_date = normalize_iso_date(args.added_date, "--added-date")
    if args.metrics_updated:
        args.metrics_updated = normalize_iso_date(args.metrics_updated, "--metrics-updated")
    data = fetch_arxiv_entry(args.arxiv_id)
    output = Path(args.output) if args.output else PAPERS_DIR / f"{data['id']}.yaml"
    if output.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_yaml(data, args), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
