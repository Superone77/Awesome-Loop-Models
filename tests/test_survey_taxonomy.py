import unittest
from pathlib import Path

import yaml

from scripts import build, taxonomy

REPO_ROOT = Path(__file__).resolve().parents[1]


def complete_fields(**overrides) -> dict:
    fields = {
        "survey_section": ["architecture/topology", "scaling/test-time"],
        "loop_topology": "prelude-core-coda",
        "sharing": "full",
        "depth_control": "sampled-train",
        "claims": ["test-time-scaling"],
        "comparison": [],
    }
    fields.update(overrides)
    return fields


class SurveyTaxonomyFieldTests(unittest.TestCase):
    def test_valid_fields_are_normalized(self):
        result = build.normalize_survey_fields(
            complete_fields(survey_core=True),
            "x.yaml",
            build.REQUIRED_PAPER_SURVEY_FIELDS,
        )
        self.assertEqual(result["survey_section"], ["architecture/topology", "scaling/test-time"])
        self.assertEqual(result["loop_topology"], "prelude-core-coda")
        self.assertEqual(result["comparison"], [])
        self.assertTrue(result["survey_core"])

    def test_missing_optional_fields_are_omitted(self):
        self.assertEqual(build.normalize_survey_fields({}, "x.yaml"), {})
        self.assertEqual(
            build.normalize_survey_fields({"survey_section": ["understanding/why"]}, "x.yaml", ("survey_section",)),
            {"survey_section": ["understanding/why"]},
        )

    def test_required_fields_must_be_present(self):
        for field in build.REQUIRED_PAPER_SURVEY_FIELDS:
            data = complete_fields()
            del data[field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f"x.yaml: missing required {field}"):
                build.normalize_survey_fields(data, "x.yaml", build.REQUIRED_PAPER_SURVEY_FIELDS)
        self.assertEqual(taxonomy.REQUIRED_PAPER_SURVEY_FIELDS, taxonomy.SURVEY_FIELDS[:-1])
        self.assertNotIn("survey_core", taxonomy.REQUIRED_PAPER_SURVEY_FIELDS)

    def test_invalid_values_are_rejected(self):
        for data in (
            {"survey_section": ["design/topology"]},
            {"survey_section": ["architecture"]},
            {"survey_section": []},
            {"loop_topology": "flat"},
            {"sharing": "tied"},
            {"depth_control": "dynamic"},
            {"claims": ["speed"]},
            {"comparison": ["iso-time"]},
            {"survey_core": "yes"},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                build.normalize_survey_fields(data, "x.yaml")

    def test_vocabularies_are_consistent(self):
        sections = taxonomy.VALID_SURVEY_SECTIONS
        self.assertEqual(len(sections), len(set(sections)))
        self.assertEqual(len(taxonomy.SURVEY_SECTION_NUMBERS), len(sections))
        chapter_numbers = [number for number, _, _ in taxonomy.SURVEY_CHAPTERS]
        part_ids = [part_id for part_id, _ in taxonomy.SURVEY_PARTS]
        self.assertEqual(chapter_numbers, [str(n) for n in range(2, 11)])
        for _, part_id, _ in taxonomy.SURVEY_CHAPTERS:
            self.assertIn(part_id, part_ids)
        numbers = [taxonomy.SURVEY_SECTION_NUMBERS[section_id] for section_id in sections]
        self.assertEqual(numbers, sorted(numbers, key=lambda n: tuple(int(p) for p in n.split("."))))
        for section_id in sections:
            with self.subTest(section_id=section_id):
                self.assertRegex(section_id, r"^[a-z-]+/[a-z0-9-]+$")
                self.assertIn(taxonomy.chapter_of(section_id), chapter_numbers)
        for chapter in chapter_numbers:
            self.assertTrue(any(taxonomy.chapter_of(section_id) == chapter for section_id in sections), chapter)
        for _, values in (*taxonomy.SURVEY_SCALAR_FIELDS, *taxonomy.SURVEY_LIST_FIELDS):
            self.assertEqual(len(values), len(set(values)))
        for _, values in taxonomy.SURVEY_SCALAR_FIELDS:
            self.assertIn("unspecified", values)
        self.assertEqual(set(taxonomy.AXIS_LABELS), {"loop_topology", "sharing", "depth_control", "claims", "comparison"})
        self.assertFalse(set(taxonomy.RETIRED_FIELDS) & set(taxonomy.SURVEY_FIELDS))

    def test_chapter_of_uses_the_survey_number(self):
        self.assertEqual(taxonomy.chapter_of("foundations/recurrence"), "2")
        self.assertEqual(taxonomy.chapter_of("architecture/depth-control"), "4")
        self.assertEqual(taxonomy.chapter_of("open-problems/monitorability-safety"), "10")
        with self.assertRaises(KeyError):
            taxonomy.chapter_of("design/topology")

    def test_browser_entries_keep_survey_fields(self):
        entry = {"id": "x", "entry_type": "paper", **complete_fields(survey_section=["understanding/interpretability"]),
                 "survey_core": False, "category": "analysis", "tags": ["x"]}
        browser_entry = build.serialize_browser_entry(entry)
        for field in build.SURVEY_FIELDS:
            self.assertIn(field, browser_entry)
        self.assertNotIn("category", browser_entry)
        self.assertNotIn("tags", browser_entry)

    def test_catalog_papers_carry_every_required_survey_field(self):
        for path in sorted((REPO_ROOT / "papers").glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            with self.subTest(path=path.name):
                build.reject_retired_fields(data, path.name)
                build.normalize_survey_fields(data, path.name, build.REQUIRED_PAPER_SURVEY_FIELDS)

    def test_catalog_blogs_carry_only_survey_sections(self):
        for path in sorted((REPO_ROOT / "blogs").glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            with self.subTest(path=path.name):
                build.reject_retired_fields(data, path.name)
                build.normalize_survey_fields(data, path.name, ("survey_section",))
                for field in build.SURVEY_FIELDS:
                    if field != "survey_section":
                        self.assertNotIn(field, data)


if __name__ == "__main__":
    unittest.main()
