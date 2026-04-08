<<<<<<< HEAD
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
short_description: OpenEnv environment that simulates cloud infra optimization
---

# Cloud-Ops Janitor - OpenEnv Environment

## Introduction

**Cloud-Ops Janitor** is a real-world OpenEnv environment that simulates cloud infrastructure optimization tasks commonly faced by DevOps and FinOps teams.

The environment challenges agents to make intelligent decisions that balance:

* Cost efficiency
* Security (public exposure risks)
* System reliability (uptime preservation)

Agents interact through the standard OpenEnv API (`step()`, `reset()`, `state()`) and must learn to manage cloud resources effectively under realistic constraints.

---

=======
# Cloud-Ops Janitor - OpenEnv Environment

## Introduction

**Cloud-Ops Janitor** is a real-world OpenEnv environment that simulates cloud infrastructure optimization tasks commonly faced by DevOps and FinOps teams.

The environment challenges agents to make intelligent decisions that balance:

* Cost efficiency
* Security (public exposure risks)
* System reliability (uptime preservation)

Agents interact through the standard OpenEnv API (`step()`, `reset()`, `state()`) and must learn to manage cloud resources effectively under realistic constraints.

---

>>>>>>> ba72070a0ab6d80166a14921edae0e9bc16588b0
## Motivation

Modern cloud systems often accumulate inefficiencies such as:

* Unused storage volumes (wasted cost)
* Idle development instances
* Publicly exposed databases (security risks)

This environment models these real-world issues and provides a controlled setting for training and evaluating AI agents on **multi-objective infrastructure management**.

---

<<<<<<< HEAD
=======
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

* Reduce infrastructure cost
* Secure public databases
* Maintain production uptime

**Scoring:**
Weighted multi-objective score:

* Cost optimization
* Security improvement
* Uptime preservation

---

## Baseline Inference

A deterministic rule-based agent is provided as a baseline.

Characteristics:

* Uses simple heuristics (no ML)
* Interacts via API endpoints
* Produces reproducible scores
* Follows required logging format:

```
[START]
[STEP]
[END]
```

---

>>>>>>> ba72070a0ab6d80166a14921edae0e9bc16588b0
## Setup & Usage

### 1. Clone repository

```bash
git clone https://huggingface.co/spaces/Winter262005/coj-env
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

<<<<<<< HEAD
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

* Reduce infrastructure cost
* Secure public databases
* Maintain production uptime

**Scoring:**
Weighted multi-objective score:

* Cost optimization
* Security improvement
* Uptime preservation

---

## Baseline Inference

A deterministic rule-based agent is provided as a baseline.

Characteristics:

* Uses simple heuristics (no ML)
* Interacts via API endpoints
* Produces reproducible scores
* Follows required logging format:

```
[START]
[STEP]
[END]
```

---

=======
>>>>>>> ba72070a0ab6d80166a14921edae0e9bc16588b0
## Deployment

The environment is deployed as a Hugging Face Space using Docker and is fully compliant with the OpenEnv specification.

---

## OpenEnv Compliance

* Typed Pydantic models (`Observation`, `Action`)
* `step()`, `reset()`, `state()` implemented
* `openenv.yaml` included
* Passed `openenv validate`

---

## Future Work

* More complex cloud scenarios (autoscaling, networking)
* Dynamic workloads and stochastic behavior
* Advanced anomaly detection signals
* Integration with real cloud telemetry datasets

---
