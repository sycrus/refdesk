# ADR-009: Kubernetes (kind) for learning, compared with Cloud Run

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Demonstration goal D4 is to containerise, deploy and operate the system (PRD 3). PRD 13A lists the Kubernetes work: Deployment, Service, ConfigMap, Secret template, HPA, a nightly eval CronJob, probes, limits, and failure drills with postmortems. The API holds run state in SQLite and the index in memory, so it is not freely scalable (PRD 13A).

## Decision
Deploy to a local kind cluster in M5, for learning, and write a comparison with Cloud Run, including what a local cluster hides. **[Joe]**: the choice on API state, either a single API replica with HPA shown on stateless parts, or a small database as another service.

## Options considered
| Option | Why not chosen |
|---|---|
| Cloud Run only | **[Joe]** |
| A managed Kubernetes cluster | **[Joe]** |
| Docker Compose only | **[Joe]** |

## Consequences
- Easier: failure drills (kill a pod, missing secret, OOM, bad image, readiness failing) can run locally at no cost.
- Harder: kind hides cloud networking, load balancers and node failure; the GPU and WSL2 services (Kev, Ollama) stay outside the cluster.
- **[Joe]**

## Evidence
No measurement yet. Not built. The M5 drills supply it (time to detect and time to recover for each).

## Revisit trigger
The comparison shows Cloud Run covers the drills with less work, or the API needs more than one replica.
