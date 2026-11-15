# Two-minute speech for the mentor

Written to be **spoken while things happen on screen**. The `SHOW` lines are
stage directions, not words to say. Roughly 280 words — about two minutes at a
calm pace, which is slower than you think you need to talk.

## Set up before you start (30 seconds)

Two windows, side by side:

1. **Browser** — `test-apps/broken-admin/index.html`, opened from disk.
2. **Terminal** — big font, in the project folder, screen cleared.

Have this typed but **not** run, so you press Enter mid-sentence:

```
uv run python docs/demo_crawl.py
```

---

## The speech

> **SHOW: browser, on the dashboard page.**

"This is a small web app we built on purpose to be broken. I'm signed in as an
ordinary guest — the lowest level of access."

*(point at the Admin link)*

"This link should not be here. A guest can see the admin area. And if I click
it—"

> **SHOW: click Admin.**

"—there's a Delete User button. Two clicks from the front page."

"Now, a normal test wouldn't catch this. Normal tests check that the things you
*expect* to work, work. Nobody writes a test for a button that isn't supposed to
exist. That's the gap we're filling."

> **SHOW: switch to the terminal. Press Enter.**

"So we built something that explores an app on its own. Nobody tells it where to
go. It starts at the front page, tries every link and button, and checks each
screen against a list of rules — like a building inspector who walks every
corridor and tries every door."

> **SHOW: the output appears — under a second. Point at the map.**

"That's the map it drew. Six pages, and it worked out how they connect —
including the loops, where logging out brings you back to the start."

*(point at the four green FOUND lines)*

"And these are the problems it found. Four of them."

"Here's the part I'd like to highlight. We wrote those four bugs down in a file
*before* running it. So this isn't us looking at the output and saying 'looks
right.' It's scored automatically — it found all four, and it invented none.
It's checked the same way every time anyone touches the code."

> **SHOW: scroll to the summary line.**

"We're about halfway through the plan, and on schedule. One honest caveat: the
real browser is my teammate's part and isn't ready yet, so this runs against a
stand-in. That was deliberate — it's why I could finish two months of work
without waiting on anyone."

---

## If she asks one question, it'll be this

**"So does it work on a real website?"**

> "Not yet — the browser piece belongs to a teammate. But everything I built
> plugs into it with a one-line change, because we agreed the exact connection
> point between us before any of us started writing code."

## Two words to avoid

Don't say **orchestrator** or **breadth-first**. Say **"the part that decides
where to go next"** and **"it explores nearby pages before distant ones."**
