from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from env.core import CloudEnv
from env.tasks import (
    spend_guard_grader,
    compliance_sprint_grader,
    rightsizer_grader,
    cloud_auditor_grader,
)

app = FastAPI(title="Cloud-Ops Janitor — OpenEnv", version="1.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

env = CloudEnv()

GRADERS = {
    "spend_guard":       spend_guard_grader,
    "compliance_sprint": compliance_sprint_grader,
    "rightsizer":        rightsizer_grader,
    "cloud_auditor":     cloud_auditor_grader,
}

_initial_state: dict = {}


# ── Core OpenEnv Endpoints ─────────────────────────────────────────────────────

@app.post("/reset")
def reset(task: str = "cloud_auditor"):
    global _initial_state
    obs = env.reset(task)
    _initial_state = obs
    return obs


@app.post("/step")
def step(action: dict):
    obs, reward, done, info = env.step(action)
    return {"observation": obs, "reward": reward, "done": done, "info": info}


@app.get("/state")
def get_state():
    return env.state()


@app.get("/grade/{task}")
def grade(task: str):
    if task not in GRADERS:
        raise HTTPException(status_code=404, detail=f"Unknown task: {task}. "
                            f"Valid: {list(GRADERS.keys())}")
    score = GRADERS[task](_initial_state, env.state())
    return {"task": task, "score": score}


# ── OpenEnv Schema / Metadata ──────────────────────────────────────────────────

@app.get("/metadata")
def metadata():
    return {
        "name":    "cloud-ops-janitor",
        "version": "1.2.0",
        "tasks":   list(GRADERS.keys()),
        "description": (
            "Cloud infrastructure RL environment. Four independent tasks each "
            "showcase distinct tradeoffs: cost vs availability, priority under "
            "step constraint, bidirectional fleet rightsizing, and multi-domain "
            "audit with protected-resource traps."
        ),
    }


@app.get("/schema")
def schema():
    return {
        "observation": {
            "instances": {
                "type": "array",
                "items": {
                    "id":              "string  — AWS instance ID",
                    "instance_type":   "string  — e.g. m5.xlarge, g4dn.xlarge",
                    "cpu_utilization": "float   — 0-100% from CloudWatch",
                    "status":          "string  — 'running' | 'stopped'",
                    "tag":             "string  — 'dev' | 'prod'",
                    "hourly_cost":     "float   — real AWS on-demand $/hr",
                    "criticality":     "string  — 'high' | 'medium' | 'low' (SLA impact)",
                    "protected":       "bool    — if True, MUST NOT be stopped or downgraded",
                    "downgrade_target":"string? — cheaper type to downgrade to (overprovisioned)",
                    "upgrade_target":  "string? — larger type to upgrade to (underprovisioned)",
                },
            },
            "volumes": {
                "type": "array",
                "items": {
                    "id":           "string  — EBS volume ID",
                    "volume_type":  "string  — 'io2' | 'gp3'",
                    "state":        "string  — 'available' (zombie) | 'in-use' (attached)",
                    "age":          "int     — days since creation",
                    "hourly_cost":  "float   — $/hr proxy rate",
                    "encrypted":    "bool    — False = HIGH compliance severity",
                },
            },
            "databases": {
                "type": "array",
                "items": {
                    "id":                  "string",
                    "publicly_accessible": "bool — True = CRITICAL security risk",
                },
            },
            "cost":    "float — total hourly AWS burn rate ($)",
            "health":  "float — 0-1 SLA/compliance posture",
            "alerts":  "list[string] — active Trusted Advisor / Security Hub alerts",
        },
        "actions": {
            "delete_volume":      "Delete an unattached zombie EBS volume (state=available, age>30)",
            "stop_instance":      "Stop an eligible EC2 instance (check criticality + protected flag!)",
            "secure_database":    "Make a publicly accessible RDS database private",
            "downgrade_instance": "Downgrade an overprovisioned instance (downgrade_target set)",
            "upgrade_instance":   "Upgrade an underprovisioned instance (upgrade_target set)",
            "encrypt_volume":     "Encrypt an unencrypted in-use EBS volume (encrypted=False)",
            "noop":               "No operation — wastes a step",
        },
        "tasks": {
            "spend_guard": {
                "difficulty": "Easy-Medium",
                "tradeoff":   "Cost reduction vs SLA availability. HIGH-criticality instances "
                              "save the most money but breach health < 0.65 -> near-zero score.",
                "max_steps":  10,
            },
            "compliance_sprint": {
                "difficulty": "Medium",
                "tradeoff":   "Severity-weighted coverage under a 5-step budget. 6 issues exist; "
                              "agent must skip MEDIUM to fix all CRITICAL+HIGH for best score.",
                "max_steps":  5,
            },
            "rightsizer": {
                "difficulty": "Medium-Hard",
                "tradeoff":   "Bidirectional fleet sizing. Downgrade overprovisioned, upgrade "
                              "underprovisioned, leave right-sized alone. Wrong direction = penalty.",
                "max_steps":  10,
            },
            "cloud_auditor": {
                "difficulty": "Hard",
                "tradeoff":   "Multi-domain audit with a protected-resource trap. Hard fail if "
                              "protected instance (looks idle but protected=True) is touched.",
                "max_steps":  10,
            },
        },
    }