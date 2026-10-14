"""Contract tests for deterministic static-site asset budgets."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from scripts import check_asset_budgets


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build-papers.yml"
UPDATE_METRICS_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "update-metrics.yml"


def write_json(path: Path, payload: object) -> None:
    """Write a deterministic JSON fixture to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def valid_briefing(date: str = "2026-07-10") -> dict:
    """Return the minimal complete browser briefing schema."""
    return {
        "date": date,
        "title": "Latest briefing",
        "status": "published",
        "summary": "A concise reader-facing summary.",
        "source_path": f"briefings/{date[:4]}/{date[5:7]}/{date}.md",
        "highlights": [],
        "candidates": [],
    }


def valid_briefing_page(date: str | None = "2026-07-10") -> dict:
    """Return the complete reading-page schema of briefing-latest.json."""
    if date is None:
        return {
            "date": None, "title": None, "status": None, "summary": "", "highlights": [],
            "candidates": [], "source_path": None, "body_markdown": "",
        }
    return {
        **valid_briefing(date),
        "highlights": ["One highlight."],
        "candidates": [{"id": "2607.00001", "title": "A looped paper", "verdict": "added"}],
        "body_markdown": "## Added\n\n**TL;DR:** A looped block.",
    }


def briefing_page_text(page: dict) -> str:
    """Serialize a briefing page the way scripts/build.py writes it."""
    return json.dumps(page, ensure_ascii=False, indent=2) + "\n"


def briefing_page_version(page: dict) -> str:
    """Return the papers.json cache-busting version of a serialized briefing page."""
    return hashlib.sha256(briefing_page_text(page).encode("utf-8")).hexdigest()[:12]


def write_briefing_page(root: Path, page: dict) -> None:
    """Write briefing-latest.json under ``root``."""
    (root / "briefing-latest.json").write_text(briefing_page_text(page), encoding="utf-8")


def valid_survey_taxonomy() -> dict:
    """Return the smallest complete survey taxonomy the browser and submission pickers read."""
    return {
        "parts": [{"id": "building", "title": "Part III. Building, Training and Deploying"}],
        "chapters": [{"number": "4", "part": "building", "title": "Architecture and Design"}],
        "sections": [
            {"id": "architecture/depth-control", "number": "4.5", "chapter": "4", "title": "Controlling recurrence depth"}
        ],
        "axes": {
            axis: {"label": axis.replace("_", " ").title(), "values": ["unspecified"]}
            for axis in check_asset_budgets.SURVEY_AXES
        },
    }


def valid_submission_payload(existing_paths: list | None = None) -> dict:
    """Return the minimal complete submission metadata schema."""
    return {
        "existing_paths": existing_paths or [],
        "survey_taxonomy": valid_survey_taxonomy(),
        "inventories": {name: [] for name in check_asset_budgets.SUBMISSION_INVENTORIES},
    }


def valid_papers_payload() -> dict:
    """Return the minimal complete browser catalog schema."""
    return {
        "meta": {"latest_briefing_version": briefing_page_version(valid_briefing_page())},
        "survey_taxonomy": valid_survey_taxonomy(),
        "paper_chunks": [],
        "blogs": [],
        "briefings": [valid_briefing()],
    }


def write_chunk(root: Path, index: int, papers: list, count: int | None = None) -> dict:
    """Write one paper chunk under ``root`` and return its manifest row."""
    relative_path = f"catalog/papers-{index:03d}.json"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"papers": papers}, sort_keys=True)
    path.write_text(raw, encoding="utf-8")
    return {
        "path": relative_path,
        "count": len(papers) if count is None else count,
        "version": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12],
    }


def write_valid_fixture(root: Path) -> None:
    """Create the smallest valid repository fixture for the budget checker."""
    write_json(root / "papers.json", valid_papers_payload())
    write_briefing_page(root, valid_briefing_page())
    write_json(root / "submission-meta.json", valid_submission_payload())
    favicon_path = root / "assets" / "favicon.png"
    favicon_path.parent.mkdir(parents=True, exist_ok=True)
    favicon_path.write_bytes(b"fixture favicon")


def deterministic_noise(length: int) -> str:
    """Return deterministic, poorly compressible ASCII text of ``length`` characters."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    state = 0xC0FFEE
    characters = []
    for _ in range(length):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        characters.append(alphabet[state % len(alphabet)])
    return "".join(characters)


def measurement(report: check_asset_budgets.AssetBudgetReport, name: str) -> int | None:
    """Return the measured value for ``name`` from an asset-budget report."""
    return next(item.measured for item in report.measurements if item.name == name)


class AssetBudgetContractTests(unittest.TestCase):
    """Exercise every byte and schema contract enforced by the checker."""

    def test_valid_fixture_passes_every_budget(self):
        """A minimal valid fixture should satisfy every configured budget."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertTrue(report.ok, report.violations)
        self.assertEqual(
            {item.name for item in report.measurements},
            {
                "papers.json deterministic gzip bytes",
                "largest paper chunk deterministic gzip bytes",
                "largest paper chunk entries",
                "papers.json briefing count",
                "papers.json briefing content fields",
                "briefing-latest.json deterministic gzip bytes",
                "submission-meta.json raw bytes",
                "assets/favicon.png raw bytes",
            },
        )

    def test_rejects_papers_gzip_bytes_over_limit(self):
        """The deterministic gzip budget should catch a high-entropy catalog."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["padding"] = deterministic_noise(140_000)
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertGreater(
            measurement(report, "papers.json deterministic gzip bytes"),
            check_asset_budgets.PAPERS_GZIP_BYTES_LIMIT,
        )
        self.assertIn("papers.json deterministic gzip bytes", "\n".join(report.violations))

    def test_accepts_manifest_with_valid_paper_chunks(self):
        """Chunks that match their manifest rows should pass and be measured."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["paper_chunks"] = [
                write_chunk(root, 0, [{"id": "a"}, {"id": "b"}]),
                write_chunk(root, 1, [{"id": "c"}]),
            ]
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertTrue(report.ok, report.violations)
        self.assertEqual(measurement(report, "largest paper chunk entries"), 2)
        self.assertGreater(measurement(report, "largest paper chunk deterministic gzip bytes"), 0)

    def test_rejects_paper_chunk_over_gzip_limit(self):
        """Each chunk has its own deterministic gzip budget."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["paper_chunks"] = [write_chunk(root, 0, [{"desc": deterministic_noise(140_000)}])]
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertIn("largest paper chunk deterministic gzip bytes", "\n".join(report.violations))

    def test_rejects_paper_chunk_with_too_many_entries(self):
        """Chunks must stay bounded in entry count."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            papers = [{"id": str(index)} for index in range(check_asset_budgets.PAPER_CHUNK_ENTRIES_LIMIT + 1)]
            payload["paper_chunks"] = [write_chunk(root, 0, papers)]
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertIn("largest paper chunk entries", "\n".join(report.violations))

    def test_rejects_inconsistent_paper_chunks(self):
        """Count, version, path, missing-file, and stale-file errors are all reported."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            wrong_count = write_chunk(root, 0, [{"id": "a"}], count=2)
            wrong_version = write_chunk(root, 1, [{"id": "b"}])
            wrong_version["version"] = "000000000000"
            write_chunk(root, 7, [{"id": "stale"}])
            payload["paper_chunks"] = [
                wrong_count,
                wrong_version,
                {"path": "../papers.json", "count": 0, "version": ""},
                {"path": "catalog/papers-002.json", "count": 0, "version": ""},
            ]
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        violations = "\n".join(report.violations)
        self.assertIn("catalog/papers-000.json: holds 1 papers but", violations)
        self.assertIn("catalog/papers-001.json: content does not match", violations)
        self.assertIn("paper_chunks[2].path must match catalog/papers-NNN.json", violations)
        self.assertIn("catalog/papers-002.json: missing required file", violations)
        self.assertIn("catalog/papers-007.json: not listed in papers.json.paper_chunks", violations)

    def test_rejects_submission_metadata_over_limit(self):
        """Oversized but schema-valid submission metadata should fail its byte budget."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            write_json(
                root / "submission-meta.json",
                valid_submission_payload([f"papers/{index:05d}.yaml" for index in range(1_500)]),
            )

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertGreater(
            measurement(report, "submission-meta.json raw bytes"),
            check_asset_budgets.SUBMISSION_META_BYTES_LIMIT,
        )
        self.assertIn("submission-meta.json raw bytes", "\n".join(report.violations))

    def test_rejects_favicon_over_limit(self):
        """An oversized favicon should fail without affecting JSON validation."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            (root / "assets" / "favicon.png").write_bytes(
                b"x" * (check_asset_budgets.FAVICON_BYTES_LIMIT + 1)
            )

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertIn("assets/favicon.png raw bytes", "\n".join(report.violations))

    def test_rejects_more_than_one_browser_briefing(self):
        """The browser payload should contain at most the latest briefing."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["briefings"] = [valid_briefing("2026-07-10"), valid_briefing("2026-07-09")]
            write_json(
                root / "papers.json",
                payload,
            )

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertEqual(measurement(report, "papers.json briefing count"), 2)
        self.assertIn("papers.json briefing count", "\n".join(report.violations))

    def test_rejects_briefing_content_field(self):
        """Rendered briefing Markdown must stay out of the browser catalog."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["briefings"][0]["content"] = "Too much text"
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertEqual(measurement(report, "papers.json briefing content fields"), 1)
        self.assertIn("must not contain a 'content' field", "\n".join(report.violations))

    def test_rejects_nested_briefing_content_field(self):
        """No nested candidate or metadata object may restore full briefing content."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["briefings"][0]["candidates"] = [
                {"title": "Candidate", "details": {"content": "Hidden Markdown"}}
            ]
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertEqual(measurement(report, "papers.json briefing content fields"), 1)
        self.assertIn("must not contain a 'content' field", "\n".join(report.violations))

    def test_rejects_missing_required_browser_root_fields(self):
        """Every browser-consumed top-level catalog field must be present."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            write_json(root / "papers.json", {"briefings": []})

            report = check_asset_budgets.check_asset_budgets(root)

        violations = "\n".join(report.violations)
        for field in ("meta", "survey_taxonomy", "paper_chunks", "blogs"):
            with self.subTest(field=field):
                self.assertIn(f"papers.json.{field}", violations)

    def test_rejects_wrong_browser_root_field_types(self):
        """Browser-consumed objects and arrays must retain their expected root types."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload.update(
                {
                    "meta": [],
                    "survey_taxonomy": [],
                    "paper_chunks": {},
                    "blogs": {},
                    "briefings": {},
                }
            )
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        violations = "\n".join(report.violations)
        self.assertIn("papers.json.meta must be an object", violations)
        self.assertIn("papers.json.survey_taxonomy must be an object", violations)
        for field in ("paper_chunks", "blogs", "briefings"):
            with self.subTest(field=field):
                self.assertIn(f"papers.json.{field} must be an array", violations)

    def test_rejects_malformed_survey_taxonomy_and_inventories(self):
        """Pickers need complete survey rows, every design axis and every value inventory."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["survey_taxonomy"]["sections"] = [{"id": "architecture/depth-control", "number": 4.5}]
            del payload["survey_taxonomy"]["axes"]["claims"]
            payload["survey_taxonomy"]["axes"]["sharing"]["values"] = []
            write_json(root / "papers.json", payload)
            submission = valid_submission_payload()
            del submission["inventories"]["comparison"]
            submission["inventories"]["survey_section"] = [{"label": "architecture/depth-control", "count": -1}]
            write_json(root / "submission-meta.json", submission)

            report = check_asset_budgets.check_asset_budgets(root)

        violations = "\n".join(report.violations)
        self.assertIn("papers.json.survey_taxonomy.sections[0].number must be a non-empty string", violations)
        self.assertIn("papers.json.survey_taxonomy.sections[0].title must be a non-empty string", violations)
        self.assertIn("papers.json.survey_taxonomy.axes.claims must be an object", violations)
        self.assertIn("papers.json.survey_taxonomy.axes.sharing.values must be a non-empty array of strings", violations)
        self.assertIn("submission-meta.json.inventories.comparison must be an array", violations)
        self.assertIn("submission-meta.json.inventories.survey_section[0].count must be a non-negative integer", violations)

    def test_rejects_invalid_briefing_field_types(self):
        """Required briefing scalar, highlight, and candidate fields must match the UI schema."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            payload["briefings"] = [
                {
                    "date": 20260710,
                    "title": None,
                    "status": [],
                    "summary": {},
                    "source_path": False,
                    "highlights": ["valid", 3],
                    "candidates": [{"title": "valid"}, "invalid"],
                }
            ]
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        violations = "\n".join(report.violations)
        for field in ("date", "title", "status", "summary", "source_path"):
            with self.subTest(field=field):
                self.assertIn(f"papers.json.briefings[0].{field} must be a string", violations)
        self.assertIn("papers.json.briefings[0].highlights[1] must be a string", violations)
        self.assertIn("papers.json.briefings[0].candidates[1] must be an object", violations)

    def test_reports_missing_and_malformed_json_clearly(self):
        """Missing and malformed JSON files should be reported in one run."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            (root / "papers.json").unlink()
            (root / "submission-meta.json").write_text("{not-json", encoding="utf-8")

            report = check_asset_budgets.check_asset_budgets(root)

        violations = "\n".join(report.violations)
        self.assertIn("papers.json: missing required file", violations)
        self.assertIn("submission-meta.json: invalid JSON", violations)

    def test_reports_all_schema_violations_in_one_run(self):
        """Invalid top-level and submission schemas should not stop later checks."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            write_json(root / "papers.json", [])
            write_json(root / "submission-meta.json", {"existing_paths": "not-a-list"})

            report = check_asset_budgets.check_asset_budgets(root)

        violations = "\n".join(report.violations)
        self.assertIn("papers.json: top-level JSON value must be an object", violations)
        self.assertIn("submission-meta.json.existing_paths must be an array", violations)
        self.assertIn("submission-meta.json.survey_taxonomy must be an object", violations)
        self.assertIn("submission-meta.json.inventories must be an object", violations)

    def test_cli_prints_measurements_and_returns_zero_on_success(self):
        """The CLI should print measured/limit rows and return zero on success."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = check_asset_budgets.main(["--root", str(root)])

        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("measured=", rendered)
        self.assertIn("limit=", rendered)
        self.assertIn("Asset budgets: PASS", rendered)

    def test_requires_latest_briefing_page(self):
        """The Briefing tab's lazily fetched page is a required generated asset."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            (root / "briefing-latest.json").unlink()

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertIsNone(measurement(report, "briefing-latest.json deterministic gzip bytes"))
        self.assertIn("briefing-latest.json: missing required file", report.violations)

    def test_rejects_latest_briefing_page_over_gzip_limit(self):
        """A briefing body that grows past the network budget must fail."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            page = valid_briefing_page()
            page["body_markdown"] = deterministic_noise(140_000)
            write_briefing_page(root, page)
            payload = valid_papers_payload()
            payload["meta"]["latest_briefing_version"] = briefing_page_version(page)
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertGreater(
            measurement(report, "briefing-latest.json deterministic gzip bytes"),
            check_asset_budgets.BRIEFING_LATEST_GZIP_BYTES_LIMIT,
        )
        self.assertEqual(
            [violation for violation in report.violations if violation.startswith("briefing-latest.json")],
            [next(v for v in report.violations if v.startswith("briefing-latest.json deterministic gzip bytes"))],
        )

    def test_rejects_invalid_latest_briefing_json_and_fields(self):
        """Malformed JSON, missing keys and wrong field types are all reported."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            (root / "briefing-latest.json").write_text("{not json", encoding="utf-8")
            malformed = check_asset_budgets.check_asset_budgets(root)

            page = valid_briefing_page()
            del page["body_markdown"]
            page["title"] = 7
            page["date"] = "July 10"
            page["highlights"] = ["ok", 3]
            page["candidates"] = ["not an object"]
            write_briefing_page(root, page)
            invalid = check_asset_budgets.check_asset_budgets(root)

        self.assertTrue(any(v.startswith("briefing-latest.json: invalid JSON") for v in malformed.violations))
        for expected in (
            "briefing-latest.json.body_markdown is required",
            "briefing-latest.json.title must be a string",
            "briefing-latest.json.date must use YYYY-MM-DD",
            "briefing-latest.json.highlights[1] must be a string",
            "briefing-latest.json.candidates[0] must be an object",
            "briefing-latest.json: content does not match papers.json.meta.latest_briefing_version",
        ):
            self.assertIn(expected, invalid.violations)

    def test_latest_briefing_must_match_the_manifest(self):
        """The page must be the manifest's newest briefing and match its cache-busting version."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            page = valid_briefing_page("2026-07-09")
            write_briefing_page(root, page)
            payload = valid_papers_payload()
            payload["meta"]["latest_briefing_version"] = briefing_page_version(page)
            write_json(root / "papers.json", payload)

            report = check_asset_budgets.check_asset_budgets(root)

        self.assertEqual(
            report.violations,
            ("briefing-latest.json.date '2026-07-09' does not match papers.json.briefings[0].date '2026-07-10'",),
        )

    def test_accepts_empty_latest_briefing_page_without_briefings(self):
        """Without any briefing the page keeps every key with null identity fields and empty content."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            page = valid_briefing_page(None)
            write_briefing_page(root, page)
            payload = valid_papers_payload()
            payload["briefings"] = []
            payload["meta"]["latest_briefing_version"] = briefing_page_version(page)
            write_json(root / "papers.json", payload)
            empty = check_asset_budgets.check_asset_budgets(root)

            page["body_markdown"] = "Orphaned body"
            page["title"] = "Orphaned title"
            write_briefing_page(root, page)
            payload["meta"]["latest_briefing_version"] = briefing_page_version(page)
            write_json(root / "papers.json", payload)
            orphaned = check_asset_budgets.check_asset_budgets(root)

        self.assertTrue(empty.ok, empty.violations)
        self.assertIn("briefing-latest.json.title must be null when date is null", orphaned.violations)
        self.assertIn("briefing-latest.json.body_markdown must be empty when date is null", orphaned.violations)

    def test_cli_lists_all_violations_and_returns_nonzero(self):
        """The CLI should aggregate failures and return nonzero when any budget fails."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_valid_fixture(root)
            payload = valid_papers_payload()
            first = valid_briefing()
            first["content"] = "first"
            second = valid_briefing("2026-07-09")
            second["content"] = "second"
            payload["briefings"] = [first, second]
            write_json(
                root / "papers.json",
                payload,
            )
            (root / "assets" / "favicon.png").write_bytes(
                b"x" * (check_asset_budgets.FAVICON_BYTES_LIMIT + 1)
            )
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = check_asset_budgets.main(["--root", str(root)])

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("papers.json briefing count", rendered)
        self.assertIn("must not contain a 'content' field", rendered)
        self.assertIn("assets/favicon.png raw bytes", rendered)
        self.assertIn("Asset budgets: FAIL", rendered)

    def test_build_workflow_is_offline_read_only_pull_request_ci(self):
        """Build CI should validate pull requests without fetching metrics or writing to main."""
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            workflow[True],
            {
                "pull_request": {"branches": ["main"]},
                "workflow_dispatch": None,
            },
        )

        job = workflow["jobs"]["build"]
        self.assertEqual(
            job["permissions"],
            {"contents": "read", "pull-requests": "read"},
        )
        steps = job["steps"]
        steps_by_name = {step["name"]: step for step in steps}

        offline_gate_commands = {
            "Build papers.json, briefing-latest.json, submission-meta.json, README.md, and TAGS.md": "python3 scripts/build.py",
            "Check static asset budgets": "python3 scripts/check_asset_budgets.py",
            "Run unit tests": "python3 -m unittest discover -s tests -t . -p 'test_*.py'",
        }
        for name, command in offline_gate_commands.items():
            with self.subTest(step=name):
                self.assertEqual(steps_by_name[name]["run"], command)
                self.assertNotIn("if", steps_by_name[name])

        self.assertIn("Validate YAML files", steps_by_name)
        self.assertNotIn("Check new free-form tags need review", steps_by_name)

        forbidden_names = (
            "Require Semantic Scholar API key",
            "Fetch citation counts and GitHub stars",
            "Commit metrics and generated files (on main only)",
        )
        for name in forbidden_names:
            with self.subTest(step=name):
                self.assertNotIn(name, steps_by_name)

        serialized_steps = json.dumps(steps, sort_keys=True)
        self.assertNotIn("SEMANTIC_SCHOLAR_API_KEY", serialized_steps)
        self.assertNotIn("scripts/fetch_metrics.py", serialized_steps)
        self.assertNotIn("git commit", serialized_steps)
        self.assertNotIn("git push", serialized_steps)

    def test_metric_workflow_is_the_single_stale_safe_main_writer(self):
        """Metric refreshes should run daily and publish only from the current main commit."""
        workflow = yaml.safe_load(UPDATE_METRICS_WORKFLOW_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            workflow[True],
            {
                "push": {"branches": ["main"]},
                "schedule": [{"cron": "17 5 * * *"}],
                "workflow_dispatch": None,
            },
        )
        self.assertEqual(
            workflow["concurrency"],
            {"group": "update-paper-metrics-${{ github.ref }}", "cancel-in-progress": True},
        )

        job = workflow["jobs"]["update-metrics"]
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main'")
        self.assertEqual(job["permissions"], {"contents": "write"})
        steps = job["steps"]
        steps_by_name = {step["name"]: step for step in steps}
        self.assertIn(
            "--strict",
            steps_by_name["Fetch citation counts and GitHub stars"]["run"],
        )
        self.assertEqual(
            steps_by_name["Rebuild generated outputs"]["run"],
            "python3 scripts/build.py",
        )
        self.assertEqual(
            steps_by_name["Check static asset budgets"]["run"],
            "python3 scripts/check_asset_budgets.py",
        )
        self.assertEqual(
            steps_by_name["Run unit tests"]["run"],
            "python3 -m unittest discover -s tests -t . -p 'test_*.py'",
        )
        commit_step = next(step for step in steps if step["name"] == "Commit updated metrics")
        script = commit_step["run"]

        for command in (
            "git add papers",
            "git add -f papers.json briefing-latest.json submission-meta.json README.md TAGS.md catalog",
            "git diff --cached --quiet && exit 0",
            'base_sha="$(git rev-parse HEAD)"',
            "git commit -m \"chore: update paper metrics [skip ci]\"",
            "git push origin HEAD:main",
        ):
            with self.subTest(command=command):
                self.assertIn(command, script)
        self.assertEqual(
            script.count(
                "git fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main'"
            ),
            2,
        )
        self.assertEqual(
            script.count('[ "$(git rev-parse origin/main)" != "${base_sha}" ]'),
            2,
        )
        self.assertIn(
            "::notice::main advanced; a newer push run owns this refresh.",
            script,
        )
        self.assertIn(
            "::notice::main advanced during push; skipping stale refresh.",
            script,
        )


if __name__ == "__main__":
    unittest.main()
