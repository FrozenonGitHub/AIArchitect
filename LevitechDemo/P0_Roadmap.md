# P0: "It already feels magical" Plan

## Step 0 — Lock the invariants (do this once, 30 minutes)

These are non-negotiable rules you don't revisit during P0.

### 0.1 Citation invariant

The system may only cite:
- gov.uk
- legislation.gov.uk
- caselaw.nationalarchives.gov.uk
- commonslibrary.parliament.uk

Every citation must have:
- URL
- short quoted excerpt
- source domain

Anything else → not a citation.

### 0.2 Memory invariant

No reliance on chat history.

Everything persistent lives in:
- case metadata
- document index
- generated summaries with provenance

Write this at the top of your repo README. Seriously.

---

## Step 1 — Local case ingestion (foundation)

**Goal:** Ask any factual question and reliably answer it from local docs.

### 1.1 Define "a case"

- One macOS folder = one case workspace
- Folder name = case ID (good enough for P0)

### 1.2 Document ingestion (PDF + Word only)

For each file:
- Extract text
- Preserve:
  - file name
  - page number (PDF) or paragraph index (Word)
- Chunk into ~500–800 tokens with overlap
- Store:
  - raw text
  - chunk ID
  - file + page/para reference

**Output:** a searchable local index with stable provenance

### 1.3 Minimal case metadata (manual first)

Create a tiny editable JSON / DB table:

```json
{
  "client_name": "",
  "matter_type": "immigration / employment",
  "key_dates": [],
  "jurisdiction": "UK",
  "notes": ""
}
```

Don't auto-extract yet. Judy can edit this manually in P0.

---

## Step 2 — Client fact retrieval (no law yet)

**Goal:** >90% accuracy on "what did the client do / when / where?"

### 2.1 Hybrid search

- Keyword search (for names, dates, IDs)
- Vector search (for narrative questions)

Always return:
- top N chunks
- with file + page reference

### 2.2 Answer format (hard-coded)

Every answer must include:

```
Answer:
<plain English>

Evidence used:
- Document X, page Y: "<quote>"
- Document Z, page W: "<quote>"
```

If nothing found:

> "This information does not appear in the current case documents."

That's a feature, not a bug.

---

## Step 3 — Legal source retrieval (separate pipeline)

**Goal:** The model never "remembers" law — it fetches it.

### 3.1 Build a legal retriever (read-only)

Start without embeddings if you want speed:

- Query GOV.UK / legislation / case law pages via search (or cached crawl)
- Return:

```json
{
  "id": "SRC-001",
  "title": "",
  "url": "",
  "domain": "",
  "excerpt": ""
}
```

Do not merge this with client-doc retrieval.

### 3.2 Discovery vs citation rule

- Blogs (Free Movement etc.) → optional query expansion only
- You must fetch the underlying judgment from: `caselaw.nationalarchives.gov.uk`
- Only the latter can be cited.

---

## Step 4 — Answer generation with guardrails

**Goal:** Zero hallucinated citations.

### 4.1 Two-phase answer

**Phase A: Retrieval**
- client evidence chunks
- legal sources (whitelisted only)

**Phase B: Answer**

Prompt the model with:
- "You may ONLY cite from this list of sources."
- "If insufficient sources exist, say so."

### 4.2 Citation validator (simple, brutal)

After generation:
- Extract all citations
- Check:
  - citation ID exists
  - URL exists
  - domain is whitelisted

If any fail → regenerate with stricter prompt

No exceptions. This is how you hit KR2.1 = 100%.

---

## Step 5 — Multi-turn continuity (the "memory magic")

**Goal:** Judy feels the assistant "remembers" the case.

### 5.1 Session state

Persist:
- case ID
- last N retrieved facts
- last legal sources used

### 5.2 Rolling case summary (generated artifact)

After meaningful turns, update:

```
Case summary (v3):
- Client background:
- Key chronology:
- Legal issues identified:
Sources:
- Doc A p2
- Doc B p5
```

This summary:
- is editable
- is re-fed into future turns
- is NOT treated as ground truth unless backed by sources

---

## Step 6 — Minimal UI (don't overbuild)

You need exactly 3 things:

1. **Folder picker** - "Select case folder"
2. **Ask box** - single text input
3. **Sources panel** - client evidence, legal sources (clickable)

No timeline view, no fancy dashboard yet.

---

## Step 7 — Sanity check against your OKRs

| OKR | Covered? |
|-----|----------|
| KR1.1 client info accuracy | ✅ Step 2 |
| KR1.2 editable metadata | ✅ Step 1.3 |
| KR2.1 100% verifiable citations | ✅ Step 4 |
| KR2.2 regulation updates | ❌ (P0.5 later) |
| KR3.1 sound arguments | ✅ Step 4 + sources |
| KR3.2 multi-turn memory | ✅ Step 5 |

---

## Step 8 — First "wow" demo script (important)

Use this exact flow when you test with Judy:

1. "What evidence shows the client started employment?"
2. "What immigration rules are engaged by this employment?"
3. "Cite the relevant rule and any Upper Tribunal authority."
4. "Given this, what is the weakest point in our case?"

If any answer:
- cites something without a link
- can't show where a fact came from

→ that's your next bug.

---

## Next: P0.5 (very high ROI)

- Weekly diff monitoring of selected GOV.UK pages
- Auto-generated "What changed & why it matters"

**But do not start there until Steps 1–5 are solid.**
