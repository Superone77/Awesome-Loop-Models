<div align="center">

# Awesome Loop Models

**Models that compute by looping: one learned layer, block, or operator, reused inside a single forward pass.**

[![Awesome](https://awesome.re/badge.svg)](https://awesome.re)
[![Website](https://img.shields.io/badge/🌐%20Live%20Website-Link-blue?style=flat-square)]({{PUBLIC_INDEX_URL}})
[![Submit](https://img.shields.io/badge/📄%20Submit-blue?style=flat-square)]({{PUBLIC_SUBMIT_URL}})
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<img src="assets/cover.png" alt="Loop architecture concept diagram" width="100%" />

### 🌐 [**Interactive Browser**]({{PUBLIC_INDEX_URL}}) · 🧾 [**PR Submission Guide**]({{PUBLIC_SUBMIT_URL}})

<sub>The full catalog lives in the browser: search, browse by survey chapter, filter by section and loop design, and read TL;DRs, venues, code links, and daily briefings.</sub>

</div>

## News

- **2026-07-17** — The browser gained a **Release Intelligence** view: publication pulse, long-term trends, and dossiers for the latest releases. [Explore stats]({{PUBLIC_INDEX_URL}}#stats)
- **2026-04-24** — Awesome Loop Models is released. [Announcement](https://x.com/huskydogewoof/status/2047655947942744285)

## What is a loop model?

> Within a single forward pass, a shared learned layer, block, module, or operator is reused.

That covers looped, recurrent-depth, and weight-tied Transformers, adaptive halting over a reused block, deep-equilibrium and implicit layers, and shared neural algorithmic processors, plus theory and analysis of all of these. It leaves out agent loops, repeated full-model calls, diffusion-style iterative inference, and plain recurrence over time steps. [TAXONOMY.md](TAXONOMY.md) has the full rules.

<details>
<summary>Where the scope boundary sits</summary>
<br>
<img src="assets/scope.png" alt="Scope scale from agent loop to loop models" width="100%" />

Only the rightmost end of this scale is in scope. Omitting `catalog_fit` means strict scope; the rare exceptions kept for context set `catalog_fit: adjacent` and are labeled **Adjacent work**.
</details>

<details>
<summary>How the catalog is organized</summary>
<br>

The catalog follows the chapters of the **Looped Models Survey**. Each paper lists every survey section it belongs to, primary first, and the browser files it under that primary section.

| Part | Chapters |
|:--|:--|
| I. Foundations | §2 From recurrent computation to iterative depth |
| II. What looping buys | §3 Capabilities, benefits and trade-offs |
| III. Building, training and deploying | §4 Architecture · §5 Learning algorithms · §6 Scaling laws · §7 Systems |
| IV. Understanding and applications | §8 Why looped models work · §9 Applications |
| V. Open problems | §10 Diffusion · folding depth into time · monitorability and safety |

Every paper also records its design axes (`loop_topology`, `sharing`, `depth_control`) and what it claims looping buys (`claims`, `comparison`). All values are controlled; there are no free-form tags. Blogs sit in one flat section and list only the survey sections they discuss. [TAXONOMY.md](TAXONOMY.md) explains each value and [TAGS.md](TAGS.md) shows current counts.
</details>
