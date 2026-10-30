# Problem statement

## Access control that leaks through the interface

Modern web applications protect sensitive actions with backend role-based access
control (RBAC): the server refuses a request the user is not allowed to make.
The interface is a separate layer, and its own rendering logic decides what each
user *sees*. When that logic is wrong, restricted parts of the application are
exposed even though the backend would block them:

- an **Admin** link or dashboard rendered for a guest;
- a **debug panel** left in a production build;
- a destructive control - *Delete user* - reachable by a role that should never
  see it;
- role-dependent rendering that differs from page to page;
- a required element (a consent notice, a logout control, an accessibility skip
  link) silently missing from some state.

The backend may reject the request, but the exposure has already happened. It
reveals what exists, invites probing, and can itself breach a compliance rule.

## Why existing testing misses it

| Approach | What it checks | Why it misses UI exposure |
| --- | --- | --- |
| Scripted end-to-end tests | that a predefined workflow succeeds | only follow the paths someone wrote down; they assert what *should* happen, not what *must not* |
| Backend authorisation tests | that the server rejects forbidden requests | pass even when the forbidden control is on screen |
| GUI agents | that a task can be completed | optimise for reaching a goal, not for auditing every state on the way |
| Asking a vision-language model | whether a screenshot contains something | models are unreliable at judging **absence** - the core question of a policy audit |

The underlying gap is twofold. Nobody enumerates the **state space** of the
interface - every screen reachable by every sequence of actions, including loops
back to earlier screens. And nobody checks those states against a policy phrased
as **negation**: *this must not exist for this role*.

## What StateScout does about it

StateScout reframes UI testing as **state-space auditing**:

1. It explores the application autonomously, recording every distinct UI state and
   every transition between them as a **cyclic** directed graph.
2. It reads each state - structure, accessibility tree, and screenshot - into a
   semantic map of what a user in the given role can see and do.
3. It turns the QA engineer's plain-English policy into machine-checkable clauses.
4. It flags every state where a forbidden element is present or a required one is
   absent, and reports each violation with its evidence: how to reach it, a
   screenshot, the clause it breaks, and the reasoning.

Whether an element is present or absent is decided deterministically from the page
structure. The vision-language model only adds semantic interpretation; it is
never trusted to notice an absence on its own.

See [Objectives](objectives.md) for the measurable goals and
[Methodology](methodology.md) for how each step works.
