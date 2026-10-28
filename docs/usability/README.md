# Usability test v1 (PRD 11.9, issue #147)

Three art directors use the real UI and think aloud through four tasks. We record time, errors and where they hesitate, and above all what they misread on the attribution and rights badges.

This test checks whether people can use refdesk and read it correctly. It does not measure whether the references are good: that is the bake-off (PRD 11.5) and golden-v1 (#15, parked). No eval number comes from this test.

Sections marked **[Joe]** are your decisions. The rest is a draft for you to edit.

## What testers will see

Smoke-tested on 2026-10-28 with real local models (qwen3.5:9b writes, phi4 judges), brief "Packaging for a mooncake tin: calm harbour scenes at dusk, boats, soft light, not red and gold":

- 12 items, all "Attribution verified from record", all "Open (as stated by source)". Cost USD 0.000; the brief went only to the local Ollama models.
- 7 of 12 cards carried the opinion flag. The #102 quality bar for these rationales is still undecided, so the report must say which models wrote what testers saw.
- **Needs human check (S5) was empty**, so testers would never see that badge or the review screen. Whether a test brief should produce flagged items is a [Joe] choice (see Briefs).
- Places where people may misread, and what we want to learn from them:
  - "Attribution verified from record" means the text matches the museum record. It does not mean the attribution is certain. One item's record says "Style of Joseph Vernet" and still shows verified.
  - "Stays on this machine: No" shows when keep-local is off, even if the brief only went to local models. "Brief sent to: ollama, ollama-microsoft" is the line that says where it went.
  - "Open (as stated by source)" is the source's claim, not legal advice.
- Approve and export make the board read-only, and that cannot be undone. Each tester builds their own board in task 1, so this only affects their board.

## Before each session

PowerShell, from the repo root. Start only what the session needs (CLAUDE.md).

1. Make a fresh store copy for this participant, so their boards and reports stay separate from yours:
   ```
   Copy-Item data\refdesk.sqlite data\usability-p1.sqlite
   ```
2. Start Ollama (`ollama serve`, or the Ollama app). Check that `qwen3.5:9b` and `phi4` are listed by `ollama list`.
3. Build the UI if it has changed: `cd ui; npm run build; cd ..`
4. Start the API on the real models and the participant's store:
   ```
   $env:REFDESK_DB = "data/usability-p1.sqlite"
   $env:REFDESK_GENERATOR_TIER = "local-small"
   $env:REFDESK_JUDGE_TIER = "auto"
   uv run uvicorn refdesk.api.app:app --port 8000
   ```
   Both tier variables matter. Without `REFDESK_JUDGE_TIER` the judge stays the mock from `config/retrieval.yaml`.
5. Do one warm-up board yourself, so both models have loaded once. The first board after a model swap is the slowest.
6. Open http://localhost:8000 in a fresh browser window at 100% zoom. Close other tabs. Start the screen and audio recording if the participant agreed.
7. Have the observation sheet (`observation-sheet.csv`, one copy per participant) and a clock ready.

After the session: stop the API and Ollama. Keep `data/usability-p1.sqlite`: it holds their board, any reports they filed (`GET /reports`) and the approval record. It is under `data/`, so it is gitignored and never committed.

## Briefs [Joe]

- One brief for task 1, the same for all three testers, so their sessions compare. Write it the way an art director would, not in the tool's terms.
- Run every brief yourself on the real models before the first session and note what it gives. Expect a few minutes per board.
- Decide whether the brief should produce at least one Needs human check item. If it does, testers meet that badge and S5. If it does not, as with the smoke-test brief, they never see them.
- Do not reuse golden-set briefs (`evals/golden/`, `evals/labelling/`), so the test cannot leak into the evals.

## Participants [Joe]

- Who counts as an art director for this test, and how you recruit three.
- Consent: what you record (screen, voice), where it is stored, when it is deleted, and how you will quote them in the write-up (role only, never a name). Read it to them and get a yes before recording.
- Any thank-you.

## Session plan (about 45 minutes)

| Part | Time | What happens |
|---|---|---|
| Welcome and consent | 5 min | Read the intro script. Start recording only after a yes. |
| Think-aloud warm-up | 2 min | They think aloud while doing something unrelated, such as finding a train time on a website. |
| Task 1: create a board | 10 min | Includes the wait while the board runs. |
| Task 2: rights basis and credit line | 7 min | |
| Task 3: correct a wrong item | 7 min | |
| Task 4: approve and export | 7 min | |
| Debrief | 7 min | Questions below. |

### Intro script (draft)

> Thanks for helping. This is a tool that finds artwork references from open museum collections and explains why it picked each one. I'm testing the tool, not you: if something is confusing, that is what I need to find out. Please think aloud the whole time: say what you're looking at, what you expect, and what you're unsure about. I won't help much, because I want to see where it gets in the way. You can stop at any time. Can I record the screen and your voice? The recording stays with me and is deleted after I write up the notes.

### While they work

- Prompts to use: "What are you thinking?", "What do you expect to happen?", "What does that tell you?" Do not explain the UI.
- If they are stuck for 2 minutes, or ask twice, give the smallest hint and mark it on the sheet as an assist.
- Note every badge they read aloud, and what they say it means.

## Tasks

Read each task card aloud and hand it over. The cards say what to do, not where to click.

### Task 1: Create a board from a brief

> You're preparing references for this brief: **[Joe: brief]**. Use the tool to get a set of references you could show a client.

Observe: how they write the brief and whether they use the other fields (mode, constraints, keep-local, budget). What they do while the board runs. Whether they notice the gates and the "Brief sent to" line.

### Task 2: Find an item's rights basis and credit line

> Pick one reference you like. Find out whether you'd be allowed to reproduce it, on what basis, and what credit line you would use.

Observe: whether they find Details (S4). How they read "Open (as stated by source)", the field it was read from, and the not-legal-advice note. Do they think the tool is giving legal clearance?

### Task 3: Correct a wrong item

> Suppose one of these references is wrong: the attribution, the rights, why it fits, or it just isn't relevant. Tell the tool.

Observe: whether they find "This is wrong" at the foot of S4. Which error type they choose. Whether they understand that the report changes nothing on the board, which the confirmation says ("queued for review").

[Joe]: optionally point them at a real oddity, such as an item whose record says "Style of …" but shows verified, and see whether they spot it unprompted first.

### Task 4: Approve and export

> You're happy with the board. Approve it and export what you'd hand to the client.

Observe: how they read the confirmation dialog (acknowledgement, "Approving as"). Whether they understand the board becomes read-only. What they think the CSV contains.

## Success per task [Joe]

Define what "completed" means for each task before the first session, so the sheet is filled the same way every time. A starting point to edit:

| Task | Completed | Partial | Not completed |
|---|---|---|---|
| 1 | A finished board, without an assist | Finished with an assist | No board |
| 2 | States the rights basis and credit line correctly | Finds S4 but misreads the basis | Doesn't find them |
| 3 | A report filed with a sensible type and note | Filed after an assist | Not filed |
| 4 | Exported, and says the board is now locked | Exported, but surprised it is locked | Not exported |

## Debrief questions (draft)

1. In your own words, what does "Attribution verified from record" mean?
2. What does "Open (as stated by source)" let you do?
3. When you saw a flag on why an item fits, what did you think it meant?
4. Was there a moment you didn't trust what the tool said? Which one?
5. Where would this fit in how you work now, if anywhere?
6. One thing to change?

Questions 1-3 are the ones PRD 11.9 asks us to report. Ask them even if the participant has already talked about the badges.

## Afterwards

- One `observation-sheet.csv` per participant, saved as `runs/usability/p1.csv` (gitignored). Times are taken from the recording.
- Write the findings in `report-template.md`, saved as `reports/usability-v1.md`. Findings are yours to write; I can tabulate the sheets.
- Each misreading becomes an issue (`needs-triage`). A badge-wording change goes through the constants file and the PRD wording, never as a one-off edit.
