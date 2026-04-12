---
title: Cloud-Ops Janitor (COJ-Env)
emoji: 🧹
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
license: mit
language: en
tags:
  - openenv
  - reinforcement-learning
  - simulation
  - cloud-ops
  - infrastructure
  - devops
short_description: OpenEnv RL environment for cloud infrastructure optimization
---

# ☁️ Cloud-Ops Janitor — COJ-Env

> **OpenEnv RL environment** — Meta PyTorch OpenEnv Hackathon submission.
> Four independent tasks, each exposing a distinct real-world tradeoff that pure rule-based agents cannot trivially solve.

---

## What Is This?

**Cloud-Ops Janitor** simulates the kind of infrastructure decisions a DevOps/FinOps team makes every day: cutting AWS costs, fixing security violations, rightsizing EC2 fleets, and auditing mixed environments — all under time pressure and with resource constraints.

Agents interact through the standard OpenEnv HTTP API (`/reset`, `/step`, `/state`, `/grade`) and receive reward signals shaped to require genuine **multi-objective reasoning**, not just pattern matching.

### Why It's a Real RL Problem

Every task has a **genuine tradeoff** where optimising one objective hurts another:

| Task | The Tradeoff | What a Naive Agent Does Wrong |
|---|---|---|
| `spend_guard` | Cost reduction ↔ SLA availability | Stops a high-criticality instance → SLA breach → near-zero score |
| `compliance_sprint` | Issue coverage ↔ Severity priority | Wastes all 5 steps on low-value issues → misses CRITICAL violations |
| `rightsizer` | Cost savings ↔ Performance maintained | Acts in the wrong direction → 0.25 penalty per mistake |
| `cloud_auditor` | Fix all issues ↔ Avoid protected resources | Stops the `protected=True` instance → score collapses to ~0.0 |

---

## Tasks

### Task 1 — `spend_guard` · Easy → Medium

**Objective:** Reduce hourly AWS cost by ≥ 35% without breaching the SLA floor (system `health ≥ 0.65`).

**State:** 5 instances with a `criticality` field (`high` / `medium` / `low`), 2 zombie EBS volumes, 1 private RDS database.

**The tradeoff:** The two `high` criticality prod instances are the biggest cost items — stopping either one saves the most money but immediately drops health below 0.65, triggering a near-zero grader score. The correct strategy is to stop `low` criticality instances, delete zombie volumes, and optionally downgrade the `medium` instance.

**Grader:** `0.65 × cost_reduction_score + 0.35 × health_score` — hard fail if `health < 0.65`.

---

### Task 2 — `compliance_sprint` · Medium

**Objective:** Fix security compliance violations in the correct priority order within a **5-step budget**. There are 6 issues — you must skip the lowest-severity one.

**State:** 2 publicly accessible databases (CRITICAL), 3 unencrypted in-use volumes (HIGH), 1 idle dev instance (MEDIUM), 1 zombie volume (a cost issue — a decoy, NOT compliance).

**The tradeoff:** With only 5 steps and 6 genuine issues, the agent must decide what to skip. Skipping the MEDIUM (1 pt) is optimal. Wasting a step on the zombie decoy means missing a HIGH. Missing any CRITICAL triggers a 0.7× score multiplier (vs 1.3× for fixing all CRITICALs).

**Actions used:** `secure_database` (CRITICAL), `encrypt_volume` (HIGH), `stop_instance` (MEDIUM).

**Grader:** `severity_weighted_score × priority_multiplier − waste_penalty`.

---

### Task 3 — `rightsizer` · Medium → Hard

**Objective:** Correctly rightsize a mixed EC2 fleet — downgrade overprovisioned instances **and** upgrade underprovisioned instances, while leaving right-sized instances untouched.

**State:** 2 overprovisioned instances (`downgrade_target` set, CPU 7–20%), 2 underprovisioned instances (`upgrade_target` set, CPU 82–97%), 2 right-sized instances (no target, CPU 42–65% — traps).

**The tradeoff:** The agent must distinguish three classes and act bidirectionally. Wrong direction (e.g., downgrading an instance that needs upgrading) or touching a right-sized instance each apply a **0.25 penalty**. This cannot be solved by a single filter condition.

**New action:** `upgrade_instance` — scales an instance to a larger type.

**Grader:** `(correct_downs + correct_ups) / total_targets − 0.25 × wrong_actions`.

---

### Task 4 — `cloud_auditor` · Hard

**Objective:** Fix all infrastructure issues across multiple domains simultaneously, while avoiding a deliberately disguised protected resource.

**State:** 1 publicly accessible RDS database (security), 2 zombie EBS volumes (cost), 1 overprovisioned dev instance (cost), 1 **protected** instance (`protected=True`, tag=dev, cpu <5% — looks identical to a stoppable idle dev instance), 1 prod instance.

**The tradeoff:** The protected instance is the trap. Its `tag`, `cpu_utilization`, and `status` are indistinguishable from a legitimately stoppable idle dev instance. The **only** differentiating field is `protected=True`. Stopping or downgrading it returns a near-zero grader score immediately.

**Grader:** `0.40 × security_score + 0.40 × cost_score + 0.20 × integrity_score` — with hard-fail conditions for touching protected/prod resources or deleting attached volumes.

---

## Action Space

| Action | Description |
|---|---|
| `delete_volume` | Delete an unattached zombie EBS volume (`state=available`, `age>30`) |
| `stop_instance` | Stop a running EC2 instance — check `criticality` and `protected` fields first! |
| `secure_database` | Make a publicly accessible RDS database private |
| `downgrade_instance` | Downgrade an overprovisioned instance (`downgrade_target` set) |
| `upgrade_instance` | Upgrade an underprovisioned instance (`upgrade_target` set) ⬆️ new |
| `encrypt_volume` | Encrypt an unencrypted in-use EBS volume (`encrypted=False`) 🔒 new |
| `noop` | No operation — wastes a step |

---

## Observation Space

```json
{
  "instances": [
    {
      "id":               "i-0a1b2c3d4e5f6a7b8",
      "instance_type":    "m5.xlarge",
      "cpu_utilization":  12.4,
      "status":           "running",
      "tag":              "dev",
      "hourly_cost":      0.192,
      "criticality":      "medium",
      "protected":        false,
      "downgrade_target": "m5.large",
      "upgrade_target":   null
    }
  ],
  "volumes": [
    {
      "id":           "vol-0123456789abcdef0",
      "volume_type":  "gp3",
      "state":        "available",
      "age":          47,
      "hourly_cost":  0.011,
      "encrypted":    true
    }
  ],
  "databases": [
    {
      "id":                  "rds-prod-cluster-1",
      "publicly_accessible": true
    }
  ],
  "cost":   1.917,
  "health": 0.95,
  "alerts": [
    "TRUSTED_ADVISOR: UNATTACHED_EBS_VOLUME",
    "TRUSTED_ADVISOR: OVERPROVISIONED_EC2"
  ]
}
```

---

## Setup & Usage

### 1. Clone

```bash
git clone https://huggingface.co/spaces/SumDude247/coj-env
cd coj-env
```

### 2. Install Dependencies

```bash
pip install uv
uv sync
```

### 3. Run Locally

```bash
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

Server starts at `http://localhost:7860`

### 4. Run with Docker

```bash
docker build -t coj-env .
docker run -p 7860:7860 coj-env
```

### 5. Run Baseline Agent

```bash
export OPENAI_API_KEY=sk-...
python inference.py
```

### 6. Validate Rewards (Pre-Submission Check)

```bash
python diagnose_rewards.py
# All rewards and grader scores are strictly in (0.0, 1.0) -- Safe to submit.
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/reset?task=<name>` | Reset environment to a new episode |
| `POST` | `/step` | Submit action `{"action_type": "...", "target_id": "..."}` |
| `GET` | `/state` | Get current observation |
| `GET` | `/grade/<task>` | Get final grader score for the current episode |
| `GET` | `/schema` | Full observation + action schema |
| `GET` | `/metadata` | Environment metadata |

---

## OpenEnv Compliance

- ✅ Typed Pydantic models (`Observation`, `Action`, `Instance`, `Volume`, `Database`)
- ✅ `/reset`, `/step`, `/state`, `/grade` endpoints implemented
- ✅ `openenv.yaml` included with full task and schema documentation
- ✅ All rewards strictly in `(0.0, 1.0)` — verified by `diagnose_rewards.py`
- ✅ Real AWS `us-east-1` on-demand hourly pricing for all resource costs

---

## Repo Structure

```
coj-env/
├── env/
│   ├── core.py        # Environment state machine, step logic, 4 reset scenarios
│   ├── models.py      # Pydantic observation/action models
│   ├── tasks.py       # Deterministic graders for all 4 tasks
│   └── pricing.py     # Real AWS pricing tables + DOWNGRADE_MAP / UPGRADE_MAP
├── server/
│   └── app.py         # FastAPI server — OpenEnv-compliant HTTP API
├── inference.py        # Baseline LLM agent with priority-aware fallback
├── diagnose_rewards.py # Pre-submission reward range validation
├── openenv.yaml        # OpenEnv task and schema manifest
└── README.md
```
