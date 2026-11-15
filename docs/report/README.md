# `docs/report/` — StateScout research paper draft

Self-contained: nothing here is imported by the product, and nothing outside
this folder was changed to produce it.

| Path | What it is |
| --- | --- |
| `ieee/main.pdf` | **IEEE-template version** (9 pages, A4, follows `IEEE_Journal_Paper_Template.docx`): `cd ieee && make` |
| `paper/main.pdf` | Compiled draft (10 pages, two-column) |
| `paper/main.tex`, `paper/sections/*.tex` | LaTeX source, one file per section |
| `paper/references.bib` | 40 references, each checked by the novelty agent |
| `paper/Makefile` | `make` → pdflatex + bibtex; `make clean` removes aux files |
| `agents/novelty-scout.md` | Definition of the dedicated novelty-analysis agent |
| `novelty/novelty-analysis.md` | Its output: related-work matrix, surviving vs. rejected claims, RQs |
| `experiments/run_experiments.py` | Reproduces RQ2–RQ4 (read-only w.r.t. the repo) |
| `data/experiments.json` | Raw results the paper's tables are built from |

## Rebuild

```bash
# numbers
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python docs/report/experiments/run_experiments.py
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python docs/demo_crawl.py        # RQ1

# paper
cd docs/report/paper && make && make clean
```

## Before this goes anywhere

- Add author names (`main.tex`, `\author`).
- RQ1 runs on `FakePerception` and a scripted crawler. Do not describe it as an
  end-to-end result until the live Playwright → `build_semantic_map` →
  `negation.audit` pipeline reproduces it.
- `click` is replay-safe (`orchestrator/state.py`). The paper states this
  precisely; keep it that way unless Track B narrows `REPLAY_SAFE_KINDS`.
- Spot-check the `~` cells of the related-work table (Table 4) against the
  cited papers before submission.
