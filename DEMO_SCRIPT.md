# Phoenix Earnings Coach — Recorded Demo Script

A ~10 minute screen recording of the **Earnings Coach (Phoenix)** only. The
Intelligence Extractor is deliberately out of scope: it is referenced in one
sentence of narration and never shown.

Written for someone recording once and handing the file to a colleague who will
present it to a customer. Every prompt to type is given verbatim; every stretch
of generation time has narration written to fill it.

**Default configuration in this script:** `COMPANY_PROFILE=alphabet` (Alphabet,
benchmarked against Microsoft and Amazon). The prompts are profile-agnostic —
if you are demoing a different company, only the pasted quarter excerpt and the
company names in the narration change.

---

## Run of show

| # | Segment | Screen | Approx. |
|---|---|---|---|
| 0 | Pre-flight | — | not recorded |
| 1 | Cold open — the problem | Title slide or empty chat | 0:45 |
| 2 | Greeting | Type `Hello` | 1:00 |
| 3 | Intake — hand it the quarter | Paste excerpt | 0:45 |
| 4 | **The recommendation** | Phoenix picks a starting point | 1:00 |
| 5 | Module: Guidance Credibility | Full module output | 1:45 |
| 6 | Module: Analyst Ambush Prep | Full module output | 1:45 |
| 7 | Module: Q&A Drill (interactive) | Two exchanges | 2:00 |
| 8 | Close-out | "I'm done" | 0:45 |
| 9 | Wrap narration | Last frame held | 0:30 |

Segment 7 is the strongest closing beat for a customer audience — protect its
time. If you run long, cut segment 6 down to scrolling the table rather than
reading it, or drop Competitor Landmines (optional variant, below) entirely.

---

## Segment 0 — Pre-flight (do not record)

**Do a full dry run first.** This is a live model; wording varies between runs.
The dry run tells you where the pauses land so your narration fits them, and it
warms nothing — you will still start a fresh session for the real take.

Checklist:

- [ ] **Fresh session.** Module completion is tracked in session state and shows
      up in the navigation footer ("Completed: …"). A reused session opens the
      demo with modules already marked done.
- [ ] **Check the reports are current.** Reports older than 45 days render a
      `STALE` warning that Phoenix is instructed to surface before advising — it
      will say so on camera. Re-run extraction beforehand if needed.
- [ ] **Confirm the active profile matches the reports.** A `PROFILE MISMATCH`
      banner makes Phoenix refuse to brief at all.
- [ ] **Quarter excerpt ready to paste** — see segment 3. Have it in a plain text
      file, not a PDF you will fumble with on camera.
- [ ] **Only the Coach is reachable.** If both agents are registered in the same
      Gemini Enterprise app, the agent picker will show the Intelligence
      Extractor. Either scroll past it without comment or unregister it for the
      recording. Never click it — invoking the extractor from the UI triggers the
      full pipeline and overwrites the live reports.
- [ ] **Nothing confidential in frame.** No `.env`, no terminal with project IDs,
      no `projects/…/reasoningEngines/…` resource names, no other customer's tabs.
      Close bookmark bars, silence notifications, hide unrelated windows.
- [ ] **Zoom the browser to ~125%.** Module output is dense markdown tables; at
      100% it is unreadable in a compressed video.

**Recording surface:** Gemini Enterprise chat UI. It is what the customer would
actually use, and it renders the markdown tables the modules emit. `adk web .`
is an acceptable fallback but looks like a dev tool — if you use it, say so once
so nobody mistakes it for the product.

---

## Segment 1 — Cold open (0:45)

Empty chat on screen. Nothing typed yet. Narrate:

> "Every quarter, a CFO walks into an earnings call with a Q&A binder the IR team
> spent two weeks assembling. It's a static document. It doesn't know which
> analysts are dialed in this quarter, it doesn't know what the competitor said
> on their call last Tuesday, and it can't tell you that the answer you just gave
> is the one that gets you a hostile follow-up.
>
> This is the Earnings Coach. It has already read Alphabet's filings and earnings
> transcripts, profiled the analysts who cover the stock, and analysed Microsoft
> and Amazon. That work happens offline, ahead of time — so the session you're
> about to watch runs at conversation speed.
>
> It doesn't hand over a document. It runs a coaching session."

That last line is the whole pitch. Land it, then start typing.

---

## Segment 2 — The greeting (1:00)

Type exactly:

```
Hello
```

Phoenix opens with who it is, a concrete list of what it can do, and one
question. The capability list is generated from the same registry that drives
routing, so it can never advertise a module that does not exist.

While it renders, narrate:

> "It leads with what it can actually do — guidance credibility, analyst prep,
> competitor exposure, the financials, and an interactive drill. Five modules,
> taken in any order, and you don't have to do all of them."

Then read the last line off the screen and let it hang for a beat:

> "And it asks one question: do you have this quarter's numbers?"

**Do not** type anything that names a module yet. See the warning in segment 4.

---

## Segment 3 — Intake (0:45)

Paste the quarter excerpt followed by the framing line. Type this as **one
message**:

```
Q3 FY2025. I'm the CFO, and I'm prepping with the IR team. Here's the release:

<paste the excerpt here>
```

**What to paste.** Not the whole 10-Q — this is a chat box, and a 60-page dump
reads badly on camera and buries the signal. Paste 15–25 lines: the revenue and
segment lines, the margin line, and — most importantly — **the forward guidance
paragraph**. The guidance language is what makes segment 4 work.

Narrate over the paste:

> "I'm giving it the current quarter, and telling it who's prepping — a CFO gets
> different questions than a CEO does."

If you have no usable document, say so on camera and type
`Q3 FY2025, CFO prepping. I don't have the release to hand — work from what you
already have.` Phoenix will proceed from pre-extracted intelligence and state
plainly that its recommendation is less targeted. That is a perfectly good demo
beat, just a weaker one.

---

## Segment 4 — The recommendation (1:00)

Nothing to type. This segment is Phoenix's response to segment 3, and it is the
most important minute of the video.

> ⚠️ **The one way to break this segment:** if your intake message names a
> module — even loosely, even as "maybe start with the analyst stuff" — Phoenix
> is instructed to honour that instruction and skip straight to it. The
> recommendation never happens. Keep segment 3's message free of module names.

Phoenix reads the quarter, cross-references the pre-extracted intelligence, and
recommends a starting point **grounded in a specific trigger it found in your
numbers**, ordered by what matters most this quarter, and explicitly overridable.

Narrate, pointing at the actual sentence on screen:

> "Watch what it just did. It didn't give me a generic checklist. It named the
> specific thing in *my* quarter that drives the recommendation — and then it
> told me I can override it and take them in any order. It's advising, not
> railroading."

Then pause. Let the customer read it. This is the beat that separates the
product from a prompt.

---

## Segment 5 — Guidance Credibility (1:45)

Type:

```
Let's start with guidance credibility.
```

This module takes real time — it runs a synthesise → fact-check loop, then a
separate editor pass. Fill the wait with the architecture story, which is
exactly what a technical buyer wants to hear anyway:

> "While that runs — every module here is fact-checked before you see it. A
> synthesiser drafts the section, a verifier checks the claims against the source
> documents, and the draft goes back for another pass. Then a final editor
> applies the findings and has the last word. Anything that couldn't be confirmed
> reaches the executive marked UNVERIFIED, rather than quietly presented as fact.
>
> That matters more here than almost anywhere else. A wrong number in a prep
> document is a wrong number said out loud on a call that's being transcribed."

When it lands, walk the structure — do not read the whole thing aloud:

1. **`## What matters`** at the top — the walk-away points, one sentence each.
2. **The confidence line** underneath — how many claims were checked, how many
   remain unverified. Point at this explicitly; it is the trust artifact.
3. **The tables** — anything enumerable is a table, never a prose list.
4. **The source footer** on each section — `_Sources: …_`.
5. **The navigation footer** — Completed / Still available / what next.

Say:

> "Completed, still available, and what would you like next. It's tracking the
> journey, not answering a question and stopping."

---

## Segment 6 — Analyst Ambush Prep (1:45)

Answer the footer directly. Type:

```
Analyst ambush prep next.
```

This is the module customers react to hardest, because it names people.

Narrate while it generates:

> "This one is built from the analyst behavioural profiles — mined out of years
> of earnings call transcripts. Not 'analysts may ask about margins.' Who, what
> they open with, and what they do when they don't like your answer."

When it lands, scroll to the question table and read **one row aloud, in full** —
the named analyst, their opening question, and the escalation. One row, read
properly, beats scrolling through all of them.

Then say the line that sells it:

> "Note the follow-up column. The first question is rarely where an executive
> gets caught — it's the second one, after a soft answer. It's prepping you for
> both."

**Optional variant — Competitor Landmines.** If your audience is
competitive-positioning-focused and you have time, insert it here with
`Show me competitor landmines.` It covers what Microsoft and Amazon disclosed
that invites a comparison, the question that triggers, and a response that
acknowledges the fact and pivots. Cut it first if you are running long.

---

## Segment 7 — Q&A Drill (2:00)

Type:

```
Let's drill. Put me under pressure.
```

Phoenix transfers to the interactive module. It asks **one** question, in the
voice of a specific named analyst drawn from the modules you just completed, and
waits.

> **Answer the first question deliberately weakly.** This is the single most
> important direction in this script. A polished answer produces a polite
> critique and a flat demo. A hedge produces the critique that shows what the
> product is for.

Type something like:

```
We're comfortable with where the business is heading and we'll have more to say
next quarter.
```

Narrate before it responds:

> "That's the answer every executive gives when they don't want to answer. Let's
> see what it does with it."

The critique comes back in three parts: what landed, what a hostile analyst does
with the weak part, and a stronger formulation. Read the "what a hostile analyst
does with this" part aloud verbatim — it is the best sentence in the demo.

Then take the follow-up it asks, and answer it properly this time — use a real
number from the excerpt you pasted. Say:

> "And it escalates. It asked the follow-up that analyst would actually ask —
> and it gets harder as you get better."

Two exchanges is enough. Do not run a third; the pacing sags.

---

## Segment 8 — Close-out (0:45)

Type:

```
I'm done.
```

Phoenix closes out itself: the three things to remember, the one phrase to land
unprompted, and any `[UNVERIFIED]` items the IR team must confirm before the
call. It is written to be readable in a car.

Narrate:

> "Three things to remember, one phrase to land unprompted, and a short list of
> anything it couldn't verify — handed to the IR team to confirm before you go
> on. That's the thing you actually read in the car on the way in."

---

## Segment 9 — Wrap (0:30)

Hold the close-out on screen. Narrate over it:

> "Everything you just saw ran against pre-extracted intelligence — the filings,
> the transcripts, the analyst profiles, the competitor disclosures, all mined
> ahead of time so the live session stays conversational.
>
> And it isn't hard-wired to Alphabet. Point it at another company's filings and
> name their competitors, and the same coaching session runs for them."

Stop recording. Do not add an outro slide reading "thank you" — end on the
product.

---

## Handling trouble mid-take

| What happens | What to do |
|---|---|
| A module is slow | Keep talking. The architecture narration in segment 5 is written to be moved anywhere you need filler. |
| Output is thinner than the dry run | Say "let me get more from that" and ask a follow-up question in-module. Do not re-record the whole session for this. |
| `[UNVERIFIED]` markers appear | **Leave them in and point them out.** They are the feature. Hiding them would be the worst possible edit. |
| A `STALE` or `PROFILE MISMATCH` banner appears | Stop the take. This is a data problem, not a demo problem — fix it and start over. |
| A rate-limit or timeout error | Stop the take and restart the session. Do not narrate over an error screen. |
| Phoenix skips the recommendation | Your intake message named a module. Restart from segment 2 in a fresh session. |

**Never ask it to "show me the full intelligence report."** It is explicitly
instructed to refuse to dump raw extractions and will give you a reorganised
summary instead — which looks like it dodged you, on camera.

---

## Questions the customer will ask your colleague

Short, honest answers — worth reading before presenting.

**"Is it making the numbers up?"**
Every figure traces to a source document, and figures are used exactly as
written — no rounding, no approximation. Each module is fact-checked before it
reaches the executive, and anything unconfirmable is marked `[UNVERIFIED]`
rather than smoothed over. The confidence line under `## What matters` states how
many claims were checked.

**"How long does it take to set up for our company?"**
No code changes. You supply your filings and transcripts plus your competitors'
filings, name each competitor's reporting segments, and run the extraction
pipeline once — roughly ten to fifteen minutes of compute. The reports are
namespaced per company, so multiple companies coexist safely in one deployment.

**"What if our data changes mid-quarter?"**
Add the documents and re-run the extraction. Reports carry their extraction date
and are flagged stale after 45 days, and the Coach surfaces that warning before
advising rather than quietly briefing from old intelligence.

**"Where does our data live?"**
Inside your own Google Cloud project — your Cloud Storage buckets and your
Vertex AI Search data stores. The agent runs on Vertex AI Agent Engine under a
service account you control.

**"Can it see live market data?"**
No. It works from the documents you give it plus the current quarter's report
you provide in the session. That is deliberate — it is a preparation tool
grounded in disclosed material, not a market feed.

**"What was that offline pipeline you mentioned?"**
There is a separate batch stage that mines the transcripts and filings and builds
the intelligence the Coach reads. It is out of scope for this recording, and
worth its own walkthrough if they are interested.
