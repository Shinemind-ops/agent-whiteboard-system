# Whiteboard

**Persistent working memory for long-running AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)

An agent that runs for 200 turns forgets what it is doing. Context gets compacted, the thread is lost, and it starts re-solving problems it already solved — or worse, silently overwrites work it did three hours ago.

The usual fix is "write everything down." That fails the other way: the notes become a diary nobody reads, and the agent still can't tell what matters *right now*.

Whiteboard is a **single 11-field markdown file** each session maintains for itself, plus a **validator that fails loudly** when that file goes stale or malformed. It is not a memory database. It is a recovery point — enough context to resume work after 100 turns of unrelated conversation.

---

## The problem, measured

This wasn't designed from theory. It came out of auditing a real agent setup that had a rule file nobody read.

| Check | Command | Result |
|---|---|---|
| Was `SESSION-RULES` ever loaded by the runtime? | `grep -rn "SESSION-RULES" --include="*.py"` across the whole agent source | **0 hits** |
| Was `RULES.md` in the auto-injection list? | inspect `agent/coding_context.py` `_CONTEXT_FILES` | **not present** (L86) |
| The file containing the most important rule ("don't be terse") | created 2026-11-08, audited 2026-11-09 | **loaded zero times** |

The rules existed. They were never read. Every turn a note said "rules read ✅" — true of the agent's belief, false of the machine's behaviour.

> **A rule that was written but never took effect is more dangerous than no rule at all — it manufactures the illusion of being governed.**

That is the failure mode this project addresses: not missing capability, but **silent divergence between what the system claims and what it does**.

---

## The fix, in one table

| Old approach | What Whiteboard does instead |
|---|---|
| `RULES.md` read every turn (assumed) | Template injected from `AGENTS.md`, the only file the runtime guarantees to load |
| `SESSION-RULES-<id>.md` per session (assumed) | `<whiteboard_root>/<session_id>.md` — one 11-field board per session |
| Cap file size with an arbitrary character limit | Cap *content per field* — 11 fields with fixed responsibilities |
| "Announce board read ✅" at end of turn | **Mandatory update report**: all 11 fields accounted for, each marked updated / unchanged **with a reason** |

---

## The 11 fields

One board per session. Nothing else.

| # | Field | Holds |
|---|---|---|
| ① | Project rules | Written by the human, read-only for the agent |
| ② | Goal | Why this session exists |
| ③ | Current project | Root path / main file / ToDo source / what was last touched |
| ④ | ToDo list | Mirror of the project ToDo, kept in sync |
| ⑤ | Task queue | In progress / queued 1 / queued 2 |
| ⑥ | Done | **Conclusions only** — details live in the project |
| ⑦ | Last turn | ≤3 sentences, for session restart |
| ⑧ | Last 5 turns | Sliding window, **for drift detection** |
| ⑨ | Next | — |
| ⑩ | After that | — |
| ⑪ | How to resume | Board path + schema location + entry-point location |

**Why ⑦ and ⑧ are separate.** ⑦ answers *"what did I just do"* — restart fuel. ⑧ answers *"have my last 5 turns drifted off the goal"* — drift detection. After ten turns discussing something unrelated, ⑧ shows five consecutive off-topic entries; ⑦ alone can't distinguish "just drifted" from "drifted long ago."

**Why dated log sections were removed.** Five boards had five different structures. The worst used `### 2026-11-09 evening | topic` day-by-day accounting — 4,503 characters. Returning after 100 off-topic turns, the reader sees a pile of dates and still cannot tell which one is *now*. A schema that every board follows beats a format every board interprets.

---

## The validator

One file, five checks, exits non-zero on failure.

```bash
python verify_whiteboard.py --session $HERMES_SESSION_ID
```

```
█ 20261012_085850_9d3077d8  ✅ PASS  [6342 B]
   fields 11/11 | staleness board 03:23 vs reply 03:23 | last5 5 | mirror — | log-sections 0
```

| # | Check | Fails when |
|---|---|---|
| 1 | All 11 fields present | any field missing |
| 2 | Header timestamp vs last reply in session DB | behind by >10 min ⇒ **stale board** |
| 3 | ⑧ entry count | more than 5 |
| 4 | ④ mirror source file exists | path is dead |
| 5 | No dated log sections | any `### <date>` heading present |

`--json` for machine consumption, `--lag` to tune the staleness tolerance. A session dormant for more than 6 hours degrades to a warning instead of a failure — a board that will never move again shouldn't be punished for not moving, but the condition stays visible.

The staleness check is the one that matters. Everything else verifies shape; check 2 verifies **the board is actually being maintained**, which is the failure mode that motivated the project.

---

## Quick start

```bash
git clone https://github.com/Shinemind-ops/agent-whiteboard-system
cd agent-whiteboard-system

python install.py --dry-run     # show every path it will touch
python install.py               # apply
python verify.py                # 22/22 PASS means it actually landed
```

The installer detects `%LOCALAPPDATA%\hermes` (or `HERMES_HOME` / `~/.hermes`), your `AGENTS.md`, and the whiteboard root (`~/白板` by default). It is idempotent, backs up before writing, and every path is overridable:

```bash
python install.py \
  --agents "$HOME/AGENTS.md" \
  --whiteboard-dir "$HOME/whiteboard" \
  --hermes-dir "$HOME/.hermes"
```

> **The default whiteboard root is `~/白板`, not your workspace root.** If your boards live elsewhere, override with `--whiteboard-dir`, or the installer will create a second, empty board directory and the validator will happily pass on the wrong one.

`verify.py` runs 22 checks across the installed tree — `AGENTS.md` contains the required sections with real paths interpolated, the skill file has all 15 sections, the board has 11 fields, no hardcoded paths belonging to another machine, `manifest.json` hashes match on-disk files.

---

## Design notes: three things I got wrong first

### 1. A schema without enforcement rots

v1.0 defined two zones — "current" and "archive" — and nothing else. No field list, no size limit, no validator. Five boards grew five structures. Rules that specify only *where* to write, without specifying *what* or *who checks*, specify nothing.

The fix was not more rules. It was **fixing the field list** and adding **a machine that counts**. Human-defined rules drift; machine-counted numbers don't.

### 2. A report format must be falsifiable

v1.0's end-of-turn announcement was `Board <id> read`. **Reporting the wrong id still passed**, because no part of it could be contradicted.

v2.0 requires all 11 fields to be accounted for, each marked updated or unchanged *with a reason*. Stay silent on one and it shows. Write "unchanged" without a reason and it shows. **The format itself becomes the audit** — no separate review needed.

### 3. Multiple sessions edit the same rules concurrently

Three sessions were active simultaneously, all working on the same system. A board written by one was rewritten by the session that owned it — with no data loss, and the rewrite was *more* accurate, containing facts (real turn count, a tool-call limit that interrupted a run) the original author didn't know.

That isn't chaos; it's the rule system actually running. But it means **read current state before writing** — overwriting from memory will delete a sibling's improvement.

### Addendum: a check that existed but could never fail

The first version of `verify.py` shipped a check called *"whiteboard paths are local, none hardcoded from another machine."* It printed PASS. It had a name, a green tick, a place in the 22-item list.

It never checked anything.

```python
PLACEHOLDER_WB = r'C:\\Shinemind\\白板'          # value contains doubled backslashes
nrm = lambda x: x.replace('\\\\', '/')          # only replaces doubled backslashes
```

Real paths use single backslashes, so they were never normalised. The placeholder's own doubled backslashes normalised to a form that could never equal the single-backslash paths in `AGENTS.md`. The set was always empty ⇒ the condition was always true ⇒ always PASS.

It was rewritten to detect *any* foreign user path generically — no hardcoded usernames, comparing against `$USERNAME` from the environment — and verified with a **negative test**: inject `C:\Users\SomeGuy` into a copy and confirm it fails.

```
clean install      → [PASS] AGENTS.md contains no foreign machine paths
path injected      → [FAIL] found C:\Users\SomeGuy
```

A test that has never failed is not evidence. This is the same lesson as the opening table, one level down: **the check was written, was reported as passing, and governed nothing.**

---

## What's in the box

```
agent-whiteboard-system/
├── README.md              ← this file
├── README.zh.md           ← original Chinese documentation
├── LICENSE                ← MIT
├── manifest.json          ← package metadata + sha256 of every file
├── install.py             ← 6-step installer, idempotent, backs up first
├── verify.py              ← 22-check verifier for the installed tree
└── payload/
    ├── SKILL.md                    ← skill definition (15 sections)
    ├── AGENTS-template.md          ← the B1 / B5 sections to insert into AGENTS.md
    ├── verify_whiteboard.py        ← the 5-check per-turn validator
    ├── template-board.md           ← 11-field board template
    ├── template-index.md           ← board index template
    └── RULES-retirement.md         ← template converting a dead RULES.md into a notice
```

**Resource plus tutorial is the point.** `payload/` is what gets moved; `README.md` + `install.py` + `verify.py` are how you confirm it moved correctly. A package with only resources assumes the reader will figure out the integration; a package with only a tutorial can't be applied.

---

## Why `AGENTS.md`

The runtime injects context files from the project root into the system prompt every turn. That is the **only** injection that happens without the agent taking any action.

So the selection criterion isn't *"is this content important"* — it's:

> **If this isn't read this turn, will I do something wrong?**

Yes → `AGENTS.md`.
No, but it matters for certain task types → a skill or process doc, loaded when the relevant task appears.

This ordering replaced three earlier habits: "read six files every turn" (none were read), "cap injected files by character count" (the cap was invented, never sourced — and it was used to justify cutting real content), and "remember to read it" (willpower is not a mechanism).

**Anything a machine can verify should not rely on self-discipline.**

---

## Requirements

- Python 3.8+
- Any agent runtime that injects a project-root context file each turn (built and tested against [Hermes Agent](https://hermes-agent.nousresearch.com/); the schema and validator are runtime-agnostic, only `install.py`'s auto-detection is Hermes-specific)

---

## License

MIT — see [LICENSE](LICENSE).
