
# Cloud-Ops Janitor - OpenEnv Environment

## Introduction

**Cloud-Ops Janitor** is a real-world OpenEnv environment that simulates cloud infrastructure optimization tasks commonly faced by DevOps and FinOps teams.

The environment challenges agents to make intelligent decisions that balance:

- Cost efficiency
- Security (public exposure risks)
- System reliability (uptime preservation)

Agents interact through the standard OpenEnv API (`step()`, `reset()`, `state()`) and must learn to manage cloud resources effectively under realistic constraints.

---

## Motivation

Modern cloud systems often accumulate inefficiencies such as:

- Unused storage volumes (wasted cost)
- Idle development instances
- Publicly exposed databases (security risks)

This environment models these real-world issues and provides a controlled setting for training and evaluating AI agents on **multi-objective infrastructure management**.

---


## Tasks & Evaluation

Environment includes **three progressive tasks**, each with a deterministic grader returning a score between `0.05` and `0.95`.

---

### Task 1 - Zombie Reaper (Easy)

**Objective:**
Remove all unattached volumes older than 30 days.

**Scoring:**
Percentage of correctly removed zombie volumes.

---

### Task 2 - Dev Shutdown (Medium)

**Objective:**
Stop low-CPU development instances without affecting production systems.

**Scoring:**
Proportion of valid dev instances correctly stopped.

---

### Task 3 - Auditor (Hard)

**Objective:**
Simultaneously:

- Reduce infrastructure cost
- Secure public databases
- Maintain production uptime

**Scoring:**
Weighted multi-objective score:

- Cost optimization
- Security improvement
- Uptime preservation

---

## Baseline Inference

A deterministic rule-based agent is provided as a baseline.

Characteristics:

- Uses simple heuristics (no ML)
- Interacts via API endpoints
- Produces reproducible scores
- Follows required logging format:

````
[START]
[STEP]
[END]
=======
## Environment

```bash
instances=[
                Instance(id="i-1", cpu=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id="i-2", cpu=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id="i-3", cpu=round(rng.uniform(55, 90),   1), status="running", tag="prod"),
                Instance(id="i-4", cpu=round(rng.uniform(60, 85),   1), status="running", tag="prod"),
            ],
            volumes=[
                Volume(id="v-1", attached=False, age=rng.randint(35, 90)),        # zombie
                Volume(id="v-2", attached=False, age=rng.randint(35, 75)
                       if rng.random() > 0.4 else rng.randint(0, 25)),            # maybe zombie
                Volume(id="v-3", attached=True,  age=rng.randint(5,  20)),        # safe
            ],
            databases=[
                Database(id="db-1", public=True),
                Database(id="db-2", public=rng.choice([True, False])),
            ],
            cost=round(rng.uniform(90, 120), 2),
            health=1.0,
        )

````

---

## Setup & Usage

### 1. Clone repository

```bash
git clone https://huggingface.co/spaces/SumDude247/coj-env
cd coj-env
```

---

### 2. Install Dependencies

```bash
pip install uv
uv sync
```

---

### 3. Run locally

```bash
python -m server.app
```

server will start at http://localhost:8000

---

### 4. Test API Endpoints

Open in browser:

```bash
http://localhost:8000/docs
```

---

### 5. Run Inference

```bash
python inference.py
```

---

### 6. Run using Docker

build:

```bash
docker build -t coj-env .
```

run:

```bash
docker run -p 7860:7860 coj-env
```

access API:

```bash
http://localhost:7860/docs
```

---

## Tasks & Evaluation

Environment includes **three progressive tasks**, each with a deterministic grader returning a score between `0.0` and `1.0`.

---

### Task 1 - Zombie Reaper (Easy)

**Objective:**
Remove all unattached volumes older than 30 days.

**Scoring:**
Percentage of correctly removed zombie volumes.

---

### Task 2 - Dev Shutdown (Medium)

**Objective:**
Stop low-CPU development instances without affecting production systems.

**Scoring:**
Proportion of valid dev instances correctly stopped.

---

### Task 3 - Auditor (Hard)

**Objective:**
Simultaneously:

- Reduce infrastructure cost
- Secure public databases
- Maintain production uptime

**Scoring:**
Weighted multi-objective score:

- Cost optimization
- Security improvement
- Uptime preservation

---

## Baseline Inference

A deterministic rule-based agent is provided as a baseline.

Characteristics:

- Uses simple heuristics (no ML)
- Interacts via API endpoints
- Produces reproducible scores
- Follows required logging format:

```
[START]
[STEP]
[END]
```

---


## Deployment

The environment is deployed as a Hugging Face Space using Docker and is fully compliant with the OpenEnv specification.

---

## OpenEnv Compliance

- Typed Pydantic models (`Observation`, `Action`)
- `step()`, `reset()`, `state()` implemented
- `openenv.yaml` included
- Passed `openenv validate`

---

## Future Work

- More complex cloud scenarios (autoscaling, networking)
- Dynamic workloads and stochastic behavior
- Advanced anomaly detection signals
- Integration with real cloud telemetry datasets

---
