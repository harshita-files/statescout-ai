---
hide:
  - navigation
---

# StateScout AI

**An autonomous vision-language agent for logical UI auditing.**

A QA engineer points StateScout at a running web application and writes a policy
in plain English, such as *"a guest must never see an Admin link"*. StateScout
explores the application on its own, builds a graph of every UI state it reaches,
and reports each state that violates the policy, with the evidence a human needs to
check it.

Final-year project · Team 46 · Department of Computer Science & Engineering ·
Amrita Vishwa Vidyapeetham

[GitHub repository](https://github.com/harshita-files/statescout-ai){ .md-button .md-button--primary }
[How it works](project/methodology.md){ .md-button }
[Demonstrations](demos.md){ .md-button }

---

## The idea in one line

Ordinary UI tests check that expected things **happen**. StateScout checks that
forbidden things **do not exist**:

> **violations = S<sub>current</sub> ∩ C<sub>negative</sub>**

That is, the UI elements and capabilities in the current state, intersected with
what the policy forbids, plus every required element that is missing.

## Explore the project

<div class="grid cards" markdown>

-   **[Problem statement](project/problem.md)**

    Why frontend access-control leaks slip past backend checks and workflow tests.

-   **[Objectives](project/objectives.md)**

    What the system must do, and the requirements it is measured against.

-   **[Methodology](project/methodology.md)**

    The Scan, Reason, Act, Observe loop, the cyclic state graph, and the negation
    engine.

-   **[Robustness on dynamic applications](project/robustness.md)**

    How exploration stays reliable when pages change between visits.

-   **[Team](project/team.md)**

    Four parallel tracks, one module each.

-   **[Progress](project/progress.md)**

    The four-month plan and where the project stands.

-   **[Demonstrations](demos.md)**

    Video walkthroughs, and how to run the demos yourself.

-   **[Documentation](documentation/getting-started.md)**

    Setup, every module, the design decisions, and the data model.

-   **[API reference](reference/rest-api.md)**

    The reporting API and the Python code reference, generated from the source.

</div>
