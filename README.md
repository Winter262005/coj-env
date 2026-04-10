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

Environment includes **three progressive tasks**, each with a deterministic grader returning a score strictly between `0.05` and `0.95`.

### Task 1 - Zombie Reaper (Easy)

**Objective:** Remove all unattached volumes older than 30 days.

**Scoring:** Percentage of correctly removed zombie volumes.

---

### Task 2 - Dev Shutdown (Medium)

**Objective:** Stop low-CPU development instances without affecting production systems.

**Scoring:** Proportion of valid dev instances correctly stopped.

---

### Task 3 - Auditor (Hard)

**Objective:** Simultaneously reduce cost, secure public databases, and maintain production uptime.

**Scoring:** Weighted multi-objective score across cost, security, and uptime preservation.

---

## Baseline Inference

A deterministic rule-based agent is provided as a baseline.

- Uses simple heuristics (no ML)
- Interacts via API endpoints
- Produces reproducible scores
- Follows required logging format:

[START]
[STEP]
[END]


---

## Setup & Usage

### 1. Clone repository

```bash
git clone https://huggingface.co/spaces/SumDude247/coj-env
cd coj-env
```

### 2. Install Dependencies

```bash
pip install uv
uv sync
```

### 3. Run locally

```bash
python -m server.app
```

Server will start at `http://localhost:8000`

### 4. Run using Docker

```bash
docker build -t coj-env .
docker run -p 7860:7860 coj-env
```

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