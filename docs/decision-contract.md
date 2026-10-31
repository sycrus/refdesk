# Decision contract

Status: **scaffolding, not decided.** Drafted by Claude Code on 2026-10-31 for issue #153 (M4-01). Every cell marked `TODO (Joe)` is a learning-critical judgement reserved for Joe (CLAUDE.md, learning mode; PRD 10.1: "Claude Code may format and validate it but must not decide the meaning of a question or the cost of a wrong answer"). Nothing in this file is a decision until Joe fills it in and signs the change log at the bottom.

What this file does: it fixes what each decision question means, what each answer commits the system to, and what each kind of wrong answer costs. Policy thresholds (PRD 10.1, 10.3) are chosen from these costs. Without it, the abstention threshold and the routing labels have nothing to be judged against, so "Kev beats the baseline" cannot be stated in terms that matter.

v1 has one Kev question, Q1. Q2 to Q5 are rules in v1 and get their own sections when they are worked on (PRD 10.1 table).

## Facts this contract depends on

Read from the repo on 2026-10-31. Check them again before you rely on them.

| Fact | Source |
|---|---|
| Routing options are a config list, cheapest first: `routing: [local-small, cloud-flash]` | `config/providers.yaml` |
| `local-small` = Ollama `qwen3.5:9b`, thinking off; no per-token price (local) | `config/providers.yaml`, ADR-020 |
| `cloud-flash` = DeepSeek `deepseek-flash` (alias), configured at peak price, $0.30 / $1.20 per Mtok in / out | `config/providers.yaml` |
| If the local tier fails the M3 quality bar, the list switches to `[cloud-flash, cloud-strong]` | PRD 10, ADR-020, issue #102 |
| `keep_local` blocks every cloud provider. A keep-local brief that would need cloud is a Policy stop | CLAUDE.md, PRD 10.2 stop table |
| Kev returns a calibrated probability per option, with no generated text. Questions cannot see each other's answers | PRD 10.1 |
| The routing label for a brief is the cheapest tier that met the quality bar (verifier pass plus judge) | PRD 10.1 rule 1, PRD 10.3 |
| Judge is `phi4`, one claim at a time, never from the generator's family | ADR-021, ADR-022, `config/providers.yaml` |
| Abstention (low confidence) goes to the cloud tier or to a human, depending on the flag | PRD 10.1 |
| Cost is measured per resolved board, including retries and escalations. Starting cap USD 0.05 per board (placeholder) | PRD 12 |
| Every routing feature must exist before the decision; a feature that needs the local model's answer makes the router a cascade | PRD 12, PRD 10.1 rule 4 |

## Q1: Which tier should handle this request?

Type: choice. Backend in v1: Kev-4B fine-tuned on routing labels (PRD 10.3). Feeds: routing.

### Option meanings

Scope question for Joe: do the option names mean the *slots* "cheapest configured tier" / "next tier up" (so the contract survives a switch to `[cloud-flash, cloud-strong]`), or the specific tiers `local-small` / `cloud-flash`? This shapes whether a tier switch in #102 needs a new contract version.

| Option | Meaning: what choosing it commits the system to | Inputs it may use (must exist before the decision) |
|---|---|---|
| `local` | TODO (Joe) | TODO (Joe) |
| `cloud` | TODO (Joe) | TODO (Joe) |

### Cost of each wrong decision

"Hard" and "easy" are defined by the routing label: a brief is *easy* if the cheapest tier met the quality bar, *hard* if only a higher tier did. If you define them differently, replace this paragraph.

Things a cost can be measured in, from the PRD. Use the ones that apply, or others: money per resolved board (PRD 12), latency, a retry or escalation, an operator's time on the human check, a wrong or unverifiable item reaching the board (FR-5), a brief leaving the machine (PRD 10, data flow).

| True label | Decision | Name | What happens (consequences, in order) | Cost (unit and size or rank) |
|---|---|---|---|---|
| hard | `local` | Under-routing | TODO (Joe) | TODO (Joe) |
| easy | `cloud` | Over-routing | TODO (Joe) | TODO (Joe) |
| easy | `local` | Correct | (no error) | n/a |
| hard | `cloud` | Correct | (no error) | n/a |

Cost ratio (under-routing : over-routing), used to set the threshold: TODO (Joe).

Neither tier met the bar: what is the label, and what should the router do? TODO (Joe).

### Abstention rule

Policy code turns Kev's calibrated probabilities into an action (PRD 10.1). The threshold *value* comes from validation data (PRD 10.3, coverage at a 5% error budget). The *rule* is Joe's.

| Condition | Action | Why |
|---|---|---|
| Top-option probability below the threshold, brief not flagged | TODO (Joe): escalate to cloud, or human check | TODO (Joe) |
| Below the threshold, brief flagged (Q2, Q3 or out of domain) | TODO (Joe) | TODO (Joe) |
| Below the threshold, brief marked `keep_local` | TODO (Joe). Cloud is blocked (CLAUDE.md), so the choice is: local anyway, human check, or Policy stop | TODO (Joe) |
| Kev unavailable or returns an error | TODO (Joe) | TODO (Joe) |

Who sets the threshold, and when it is re-fitted: TODO (Joe).

### Routing-label quality bar

The bar a tier's output must meet for that tier to count as "got it right" in the routing labels (PRD 10.3: verifier pass plus judge).

| Part | Definition |
|---|---|
| Verifier | TODO (Joe), or: "deferred to #102 (M3 quality bar)" |
| Judge (`phi4`, one claim at a time) | TODO (Joe), or: "deferred to #102" |
| How the two combine | TODO (Joe) |
| Judge agreement needed before labels are trusted (PRD 10.3: calibrated on 100 rows Joe rates) | TODO (Joe) |

If you defer the bar to #102, write the deferral here explicitly (issue #153, second acceptance criterion).

## Change log

| Date | Change | By |
|---|---|---|
| 2026-10-31 | Scaffolding drafted, all judgements empty (#153) | Claude Code |
