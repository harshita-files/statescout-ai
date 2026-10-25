# Demonstrations

## Videos

<!-- TODO(team): add each recording here. For a YouTube video, replace VIDEO_ID:

<div class="video">
  <iframe src="https://www.youtube-nocookie.com/embed/VIDEO_ID"
          title="StateScout demo" allowfullscreen></iframe>
</div>

For a video committed to the repository, put the file in docs/portal/assets/ and use:

<video controls width="100%" src="../assets/demo.mp4"></video>
-->

| Demo | What it shows | Video |
| --- | --- | --- |
| End-to-end audit | A policy, an autonomous crawl of `broken-admin`, and the four planted violations found | *Coming soon* |
| The state graph | The cyclic exploration graph: deduplicated states and preserved back-edges | *Coming soon* |
| Evidence chain | One violation traced from the report back to the clicks, screenshot and policy clause | *Coming soon* |
| Dynamic applications | A live audit of a dynamic single-page application | [Watch](#live-audit-of-a-dynamic-application) |

## Live audit of a dynamic application

StateScout auditing a live single-page application, the Conduit demo app, as a
guest user.

<div class="video">
  <iframe src="https://www.youtube-nocookie.com/embed/J1Andaxddr8"
          title="StateScout Demo" loading="lazy"
          allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
          allowfullscreen></iframe>
</div>

## Exploration graph

The crawl of the `broken-admin` ground-truth app, drawn as a single page: every
state reached, forward edges and back-edges (cycles are kept, never pruned), the
pages that violate the policy, and every planted violation checked against what
the crawl found. This page is regenerated from the real exploration loop each time
the site is built.

<div class="demo-frame">
  <iframe src="../demo/exploration-graph.html" title="StateScout exploration graph of broken-admin" loading="lazy"></iframe>
</div>

<a class="md-button" href="../demo/exploration-graph.html" target="_blank" rel="noopener">Open the exploration graph in its own tab</a>

To render it yourself:

```bash
uv run python -m apps.agent.orchestrator.demo_visual statescout-demo.html
```

It runs offline, with no browser, database or API keys, and prints the path of the
page it wrote. Without an argument it writes to the system's temporary folder.

## Run the demo yourself

The scripted demo walks through the same crawl step by step in the terminal. It is
fully offline: no Docker, browser or API keys. It runs the real orchestrator against
the `broken-admin` ground-truth app with scripted crawler and perception stand-ins.

```bash
git clone https://github.com/harshita-files/statescout-ai.git
cd statescout-ai
uv sync --all-groups
./demo.sh            # run straight through
./demo.sh --step     # pause before each step, for presenting live
```

`apps/agent/orchestrator/demo.sh` runs the orchestrator's version of the walkthrough,
which includes a step that renders and opens the exploration graph above.

For a crawl against the real database, see
[Getting started](documentation/getting-started.md).
