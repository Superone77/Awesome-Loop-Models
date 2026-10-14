"""Controlled vocabulary for the Awesome Loop Models catalog.

The catalog is organized as a topic map of parts, chapters and sections. Every
paper lists the sections it belongs to in ``survey_section`` (a historical field
name; primary first) and describes its loop with three single-valued design axes plus the
claims it makes. There are no free-form tags: every value below is closed and
adding one is a taxonomy change, not a per-paper decision.

This module has no third-party imports so build, audit and validation scripts
can share it.
"""

from __future__ import annotations

# (part id, part title)
SURVEY_PARTS = (
    ("foundations", "Part I. Foundations"),
    ("capabilities", "Part II. What Looping Buys"),
    ("building", "Part III. Building, Training and Deploying"),
    ("understanding", "Part IV. Understanding and Applications"),
    ("open-problems", "Part V. Open Problems"),
)

# (chapter number, part id, chapter title)
SURVEY_CHAPTERS = (
    ("2", "foundations", "From Recurrent Computation to Iterative Depth"),
    ("3", "capabilities", "Capabilities, Benefits and Trade-offs"),
    ("4", "building", "Architecture and Design"),
    ("5", "building", "Learning Algorithms"),
    ("6", "building", "Scaling Laws"),
    ("7", "building", "Systems and Infrastructure"),
    ("8", "understanding", "Understanding Why Looped Models Work"),
    ("9", "understanding", "Applications"),
    ("10", "open-problems", "Open Problems"),
)

# (section id, section number, section title). Order follows the topic map.
SURVEY_SECTIONS = (
    ("foundations/recurrence", "2.1", "Recurrent networks and weight sharing across computation"),
    ("foundations/depth-sharing", "2.2", "Weight sharing across network depth"),
    ("foundations/implicit", "2.3", "Deep equilibrium and implicit models"),
    ("foundations/algorithmic", "2.4", "Iterative and algorithmic computation"),
    ("capabilities/efficiency", "3.1", "Parameter, data, and compute efficiency"),
    ("capabilities/expressivity", "3.2", "Expressivity and reasoning capacity"),
    ("capabilities/generalization", "3.3", "Length, easy-to-hard, and compositional generalization"),
    ("architecture/topology", "4.1", "Loop topology"),
    ("architecture/residual-init", "4.2", "Residual manipulation and initialization"),
    ("architecture/state-memory", "4.3", "Recurrent state and loop-time memory"),
    ("architecture/sharing", "4.4", "Weight-sharing schemes and iteration-dependent computation"),
    ("architecture/depth-control", "4.5", "Controlling recurrence depth"),
    ("architecture/hybrid", "4.6", "Hybrid looped architectures"),
    ("training/supervision-optimization", "5.1", "Supervision, credit assignment, and loop-specific optimization"),
    ("training/post-training", "5.2", "Post-training and reinforcement learning"),
    ("training/retrofitting", "5.3", "Retrofitting pretrained models into looped models"),
    ("scaling/compute-optimal", "6.1", "Parameter, depth, and compute-optimal scaling"),
    ("scaling/test-time", "6.2", "Test-time scaling"),
    ("systems/quantization-edge", "7.1", "Quantization and edge deployment"),
    ("systems/kv-memory", "7.2", "KV cache and memory"),
    ("systems/batching-parallel", "7.3", "Loop-level batching, scheduling, and parallel execution"),
    ("understanding/why", "8.1", "Why looped models work"),
    ("understanding/interpretability", "8.2", "Mechanistic interpretability"),
    ("understanding/failure-modes", "8.3", "When looping does not help: limits and failure modes"),
    ("applications/language-speech-multimodal", "9.1", "Language, code, speech, and multimodal tasks"),
    ("applications/vision", "9.2", "Visual recognition, restoration, and generation"),
    ("applications/flow-3d", "9.3", "Flow, stereo, and 3D geometry"),
    ("applications/graphs-science", "9.4", "Graphs, structured data, and scientific modeling"),
    ("applications/embodied-other", "9.5", "Embodied AI and other domains"),
    ("open-problems/diffusion", "10.1", "Unification with diffusion models"),
    ("open-problems/depth-into-time", "10.2", "Folding depth into time"),
    ("open-problems/monitorability-safety", "10.3", "Monitorability and safety"),
)
VALID_SURVEY_SECTIONS = tuple(section_id for section_id, _, _ in SURVEY_SECTIONS)
SURVEY_SECTION_NUMBERS = {section_id: number for section_id, number, _ in SURVEY_SECTIONS}
SURVEY_SECTION_TITLES = {section_id: title for section_id, _, title in SURVEY_SECTIONS}


def chapter_of(section_id: str) -> str:
    """Return the chapter number ("2".."10") of a section id."""
    return SURVEY_SECTION_NUMBERS[section_id].split(".")[0]


# Design axes (chapter 4) and claims (chapter 3).
VALID_LOOP_TOPOLOGIES = (
    "whole-stack",
    "prelude-core-coda",
    "partial",
    "hierarchical",
    "shifted-parallel",
    "implicit-fixed-point",
    "unspecified",
)
VALID_SHARING_SCHEMES = ("full", "partial-adapter", "expert-routed", "unspecified")
VALID_DEPTH_CONTROLS = ("fixed", "sampled-train", "adaptive-halting", "convergence", "unspecified")
VALID_CLAIMS = (
    "param-efficiency",
    "compute-efficiency",
    "memory-efficiency",
    "data-efficiency",
    "expressivity",
    "length-generalization",
    "test-time-scaling",
    "stability",
    "failure-mode",
)
VALID_COMPARISONS = ("iso-param", "iso-flop", "iso-depth", "unclear")

AXIS_LABELS = {
    "loop_topology": "Loop topology",
    "sharing": "Sharing",
    "depth_control": "Depth control",
    "claims": "Claims",
    "comparison": "Looped-vs-untied comparison",
}

SURVEY_SCALAR_FIELDS = (
    ("loop_topology", VALID_LOOP_TOPOLOGIES),
    ("sharing", VALID_SHARING_SCHEMES),
    ("depth_control", VALID_DEPTH_CONTROLS),
)
SURVEY_LIST_FIELDS = (
    ("survey_section", VALID_SURVEY_SECTIONS),
    ("claims", VALID_CLAIMS),
    ("comparison", VALID_COMPARISONS),
)
SURVEY_FIELDS = (
    "survey_section",
    "loop_topology",
    "sharing",
    "depth_control",
    "claims",
    "comparison",
    "survey_core",
)
# Every paper must carry these; blogs carry only survey_section.
REQUIRED_PAPER_SURVEY_FIELDS = (
    "survey_section",
    "loop_topology",
    "sharing",
    "depth_control",
    "claims",
    "comparison",
)

# Fields removed by the 2026-10 taxonomy. Their presence is an error.
RETIRED_FIELDS = (
    "category",
    "category_path",
    "subcategory",
    "foundation",
    "mechanism_tags",
    "focus_tags",
    "domain_tags",
    "tags",
)

VALID_CATALOG_FITS = ("strict", "adjacent")
