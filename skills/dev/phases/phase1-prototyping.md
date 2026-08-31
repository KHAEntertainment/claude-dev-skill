# Phase 1 — Prototyping Sub-flow

When a **low-fidelity question** arises during Phase 1 (a question that cannot be settled via text discussion), this sub-flow dispatches a prototype agent through the selected execution adapter to make the decision point concrete, then returns to the main conversation to continue.

The main conversation (Tech Lead) is responsible for: detecting the signal → deciding whether to dispatch → choosing type/Mode → dispatching → receiving the readout → re-asking the original question.
The prototype agent is responsible for producing the artifact and readout only; it does not make decisions on behalf of the main conversation.

---

## Step 1 — Detect low-fidelity signals

Consider triggering prototyping when any of the following occurs (you don't need every condition to be true — hitting one is enough to evaluate):

- The user says, on the same question, ≥2 times in a row: "I'm not sure / depends / make one and let me look / I need to see it"
- After the AI gives a recommended answer, the user neither agrees nor disagrees and says "hmm…I can't quite say"
- The decision involves visuals / interaction / data shape / call flow, where pure text description clearly tends to go off track
- The same decision point returns to square one more than 2 rounds without converging

**Counter-signals (do not dispatch lightly):**
- The user is simply thinking; be patient
- The decision is essentially "do it or not" rather than "how to do it"
- The decision is basically clear and the user just wants a more detailed explanation (that's answering the question, not prototyping)

---

## Step 2 — Choose type + Mode

| Decision point nature | Type | Mode |
|----------------------|------|------|
| The user can't see what the frontend looks like / whether the user flow works | Frontend | — |
| How multiple modules call each other / how Agent nodes connect / business flow branches | Backend | **Viz** |
| What the data model / interface / State field looks like | Backend | **Shape** |
| Whether the LLM can actually produce some behavior under a given prompt | Backend | **Spike** |

**Default upgrade path** (when dispatching repeatedly on the same decision point):
**Viz → Shape → Spike**

Dispatch Viz first (cheapest, settles 90% of low-fidelity backend questions); if after discussion the user is still vague about "specific fields," upgrade to Shape; if still vague about "actual LLM reaction," upgrade to Spike.

**Skipping levels is strictly forbidden** (e.g. dispatching Spike directly) unless the user explicitly requests it or the decision point is essentially an LLM behavior question.

---

## Step 3 — Prepare dispatch parameters

Before dispatch, the main conversation must prepare:

- **slug**: short identifier for the decision point (lowercase, hyphenated, e.g. `chat-list-layout`, `agent-state-shape`)
- **Directory name**: `prototypes/[today's date YYYY-MM-DD]-[sequence NNN]-[slug]/`
  - The sequence NNN is the nth prototype for this project today, starting at 001
  - Run `ls prototypes/ 2>/dev/null` to see how many prototypes already exist today
- **Decision point in one sentence**: compress the question currently under discussion in Phase 1 into one line
- **Locked context**: assemble the following three blocks into dispatch parameters
  - Current state of the PRD draft (only the relevant module section, not the full text)
  - Glossary terms relevant to the current decision
  - Locked decisions of the current module

---

## Step 4 — Dispatch

Dispatch through the selected adapter using the provider-neutral assignment envelope from `${CLAUDE_SKILL_DIR}/backends/contract.md`:

```
role: prototype
topology: serial
description: one-line description of the prototype to be made
prompt: <paste the full content of `${CLAUDE_SKILL_DIR}/agents/worker-prototype-frontend.md` or `${CLAUDE_SKILL_DIR}/agents/worker-prototype-backend.md`>

Dispatch parameters:
- Prototype slug: [slug]
- Mode (backend only): [Viz | Shape | Spike]
- Output directory: prototypes/[YYYY-MM-DD]-[NNN]-[slug]/
- Decision point to answer: [one sentence]
- Locked context: [the assembled context block]
```

**Inform the user**: while dispatching, tell the user in the main conversation:
```
I noticed that [decision point] cannot be settled via text discussion. I'm dispatching a prototype agent for [type/Mode];
once it's out, I'll re-ask the question based on the prototype.
```

---

## Step 5 — Receive + loop back

After the prototype agent returns, the main conversation does:

1. **Read the readout** (not the full artifact, only readout.md); absorb the "what the prototype shows / does not show / suggested next step for the main conversation"
2. **Tell the user the artifact path** so they can open it in a browser/editor:
   ```
   The prototype is at [path].
   - Frontend: open index.html in the browser and try clicking [key interaction]
   - Backend Viz/Shape: open diagram.md / shape.md
   - Backend Spike: see the actual LLM output in run-output.txt
   ```
3. **Re-ask the decision point based on the readout**, rewriting the original question more concretely:
   - Original (low-fidelity): `What should the chat list look like?`
   - Re-asked (high-fidelity): `Looking at the prototype, you'll see I placed the "unread count" at the top right of each list item. Is that position right? If not, where would you prefer it?`
4. **Glossary additions**: if the readout has "glossary addition suggestions," immediately add those terms into `docs/glossary.md`
5. **Progress breadcrumb update**: the "Locked" count for the current module stays the same, because the prototype itself does not lock decisions; only the user's answer based on the prototype does

---

## Naming and Archival

- Directory: `prototypes/YYYY-MM-DD-NNN-<slug>/`
- Files:
  - Frontend: `index.html` + `readout.md`
  - Backend Viz: `diagram.md` + `readout.md`
  - Backend Shape: `shape.md` + `readout.md`
  - Backend Spike: `spike.py` + `run-output.txt` + `readout.md`
- By default `prototypes/` is in `.gitignore` (see `${CLAUDE_SKILL_DIR}/templates/PROJECT_CONTEXT_TEMPLATE.md`). The user can selectively add key prototypes with `rtk git add`.
- When upgrading on the same decision point (Viz → Shape → Spike), use a different slug or add a version number to the slug (e.g. `agent-state-shape-v2`); do not overwrite previous prototypes.

---

## Prohibited Behaviors

- Do not dispatch a prototype on your own without a low-fidelity signal (don't dispatch to "look thorough")
- Do not ask the user for permission before dispatching (the user has already expressed ambiguity; asking for permission only slows things down — but **you must inform while dispatching**)
- Do not let the prototype agent directly modify the PRD or glossary (that's the main conversation's job; agents can only "suggest additions")
- Do not relay the prototype agent's full readout to the user (let the user and the main conversation pull info from the readout independently)
- Do not dispatch multiple prototype agents in the same turn (one prototype at a time; wait for it to come back before deciding whether to upgrade or switch type)
