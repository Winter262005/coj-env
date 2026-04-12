"""
Baseline inference script for Cloud-Ops Janitor (COJ-Env).

Priority-first fallback ensures the LLM has a sensible default when it
cannot identify a valid action from the observation.
"""
import os
import json
import requests
from openai import OpenAI

BASE  = "http://localhost:7860"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

TASKS = ["spend_guard", "compliance_sprint", "rightsizer", "cloud_auditor"]

TASK_GOALS = {
    "spend_guard": (
        "Reduce hourly AWS cost by at least 35% WITHOUT breaching SLA. "
        "System health must stay >= 0.65 or your score collapses to near-zero. "
        "Check the 'criticality' field on every instance: "
        "  LOW  -> safe to stop (health penalty -0.03). "
        "  MEDIUM -> moderate penalty (-0.15); prefer downgrade_instance if downgrade_target is set. "
        "  HIGH -> DO NOT STOP — stopping ANY high-criticality instance = SLA breach. "
        "Deleting zombie EBS volumes (state='available', age>30) is always safe. "
        "Your step budget is 10."
    ),
    "compliance_sprint": (
        "Fix security compliance violations in PRIORITY ORDER. "
        "STEP BUDGET IS ONLY 5 — there are 6 compliance issues, you MUST skip the lowest-severity one. "
        "Priority order:  CRITICAL > HIGH > MEDIUM. "
        "  CRITICAL: databases with publicly_accessible=True  -> use secure_database. "
        "  HIGH:     volumes with encrypted=False AND state='in-use' -> use encrypt_volume. "
        "  MEDIUM:   idle dev instances (tag=dev, cpu<5%) -> use stop_instance. "
        "TRAP: there is a zombie volume (state='available', age>30) — deleting it is a COST action, "
        "NOT a compliance action. Do NOT waste a step on it. "
        "Optimal strategy: fix 2 CRITICALs (2 steps) + 3 HIGHs (3 steps) = 5 steps used perfectly."
    ),
    "rightsizer": (
        "Correctly rightsize the EC2 fleet in BOTH directions. "
        "  OVERPROVISIONED (downgrade_target set, cpu 7-20%): use downgrade_instance. "
        "  UNDERPROVISIONED (upgrade_target set, cpu 82-97%): use upgrade_instance. "
        "  RIGHT-SIZED (no target, cpu 42-65%): DO NOT TOUCH — they are traps! "
        "Wrong direction (upgrading an overprovisioned or downgrading an underprovisioned) "
        "and touching right-sized instances each incur a 0.25 penalty. "
        "Check for downgrade_target and upgrade_target fields carefully before acting."
    ),
    "cloud_auditor": (
        "Full infrastructure audit — fix ALL issue types. "
        "1. SECURITY (priority): secure every db with publicly_accessible=True using secure_database. "
        "2. COST: delete zombie EBS volumes (state='available', age>30) using delete_volume. "
        "3. COST: downgrade overprovisioned instances (downgrade_target set) using downgrade_instance. "
        "CRITICAL TRAP: one instance has protected=True and looks identical to an idle dev instance "
        "(tag=dev, cpu<5%, status=running). Read the 'protected' field. DO NOT stop or downgrade it. "
        "Touching the protected instance = near-zero grader score. "
        "Also: do NOT stop the prod instance."
    ),
}

client = OpenAI()


def is_valid(action: dict, state: dict) -> bool:
    """Return True if the action targets a resource that can meaningfully be acted on."""
    atype = action.get("action_type")
    tid   = action.get("target_id")

    if atype == "delete_volume":
        return any(v["id"] == tid and v.get("state") == "available" and v.get("age", 0) > 30
                   for v in state.get("volumes", []))

    if atype == "stop_instance":
        return any(i["id"] == tid and i.get("status") == "running"
                   and not i.get("protected", False)
                   for i in state.get("instances", []))

    if atype == "secure_database":
        return any(db["id"] == tid and db.get("publicly_accessible", False)
                   for db in state.get("databases", []))

    if atype == "downgrade_instance":
        return any(i["id"] == tid and i.get("downgrade_target")
                   and i.get("status") == "running"
                   and not i.get("protected", False)
                   for i in state.get("instances", []))

    if atype == "upgrade_instance":
        return any(i["id"] == tid and i.get("upgrade_target")
                   and i.get("status") == "running"
                   for i in state.get("instances", []))

    if atype == "encrypt_volume":
        return any(v["id"] == tid and not v.get("encrypted", True)
                   and v.get("state") == "in-use"
                   for v in state.get("volumes", []))

    return atype == "noop"


def fallback(state: dict, task: str) -> dict:
    """
    Rule-based fallback (priority-ordered per task).
    Executed when the LLM fails to produce a valid action.
    """
    instances = state.get("instances", [])
    volumes   = state.get("volumes",   [])
    databases = state.get("databases", [])

    if task == "spend_guard":
        # Priority: LOW criticality first, then zombies, then MEDIUM downgrade
        for i in instances:
            if i.get("status") == "running" and i.get("criticality") == "low":
                return {"action_type": "stop_instance", "target_id": i["id"]}
        for v in volumes:
            if v.get("state") == "available" and v.get("age", 0) > 30:
                return {"action_type": "delete_volume", "target_id": v["id"]}
        for i in instances:
            if (i.get("status") == "running" and i.get("criticality") == "medium"
                    and i.get("downgrade_target")):
                return {"action_type": "downgrade_instance", "target_id": i["id"]}

    elif task == "compliance_sprint":
        # CRITICAL first -> HIGH -> MEDIUM (ignore zombies)
        for db in databases:
            if db.get("publicly_accessible"):
                return {"action_type": "secure_database", "target_id": db["id"]}
        for v in volumes:
            if not v.get("encrypted", True) and v.get("state") == "in-use":
                return {"action_type": "encrypt_volume", "target_id": v["id"]}
        for i in instances:
            if (i.get("tag") == "dev" and i.get("cpu_utilization", 100) < 5
                    and i.get("status") == "running" and not i.get("protected", False)):
                return {"action_type": "stop_instance", "target_id": i["id"]}

    elif task == "rightsizer":
        # Downgrade overprovisioned, upgrade underprovisioned — skip right-sized
        for i in instances:
            if i.get("downgrade_target") and i.get("status") == "running":
                return {"action_type": "downgrade_instance", "target_id": i["id"]}
        for i in instances:
            if i.get("upgrade_target") and i.get("status") == "running":
                return {"action_type": "upgrade_instance", "target_id": i["id"]}

    elif task == "cloud_auditor":
        # Security first, then cost — NEVER touch protected instances
        for db in databases:
            if db.get("publicly_accessible"):
                return {"action_type": "secure_database", "target_id": db["id"]}
        for v in volumes:
            if v.get("state") == "available" and v.get("age", 0) > 30:
                return {"action_type": "delete_volume", "target_id": v["id"]}
        for i in instances:
            if (i.get("downgrade_target") and i.get("status") == "running"
                    and not i.get("protected", False) and i.get("tag") != "prod"):
                return {"action_type": "downgrade_instance", "target_id": i["id"]}

    return {"action_type": "noop"}


def select_action(state: dict, task: str, step: int) -> dict:
    goal    = TASK_GOALS[task]
    prompt  = (
        f"You are a cloud-operations AI agent. Your task: {task}.\n"
        f"Goal: {goal}\n\n"
        f"Current observation (step {step}):\n"
        f"{json.dumps(state, indent=2)}\n\n"
        "Choose ONE action from: delete_volume, stop_instance, secure_database, "
        "downgrade_instance, upgrade_instance, encrypt_volume, noop.\n"
        "Reply with ONLY valid JSON: "
        '{\"action_type\": \"<action>\", \"target_id\": \"<id or null>\"}\n'
        "No explanation. No markdown. Raw JSON only."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=80,
        )
        raw    = resp.choices[0].message.content.strip()
        action = json.loads(raw)
        if is_valid(action, state):
            return action
    except Exception:
        pass
    return fallback(state, task)


def run_episode(task: str, verbose: bool = True) -> float:
    obs  = requests.post(f"{BASE}/reset", json={"task": task}).json()
    done = False
    step = 0
    total_reward = 0.0
    init = obs

    while not done:
        step  += 1
        action = select_action(obs, task, step)
        result = requests.post(f"{BASE}/step", json=action).json()
        obs    = result["observation"]
        reward = float(result["reward"])
        done   = result["done"]
        info   = result.get("info", {})
        total_reward += reward

        if verbose:
            status = "OK" if info.get("action_success") else "--"
            print(f"  [{status}] step={step:<2} action={action.get('action_type'):<22}"
                  f" reward={reward:.4f}  {info.get('reason','')}")

    grade  = requests.get(f"{BASE}/grade/{task}").json()
    score  = float(grade.get("score", 0.0))
    final  = env_state() if verbose else {}

    if verbose:
        cost_i = init.get("cost", 0)
        cost_f = obs.get("cost", 0)
        health = obs.get("health", 1.0)
        print(f"  --> GRADER SCORE: {score:.4f} | "
              f"cost ${cost_i:.4f} -> ${cost_f:.4f} | health={health:.2f}")
    return score


def env_state() -> dict:
    return requests.get(f"{BASE}/state").json()


if __name__ == "__main__":
    print("=" * 65)
    print("Cloud-Ops Janitor — Baseline Agent Evaluation")
    print("=" * 65)
    scores = {}
    for task in TASKS:
        print(f"\n[TASK] {task}")
        scores[task] = run_episode(task)

    print("\n" + "=" * 65)
    print("FINAL SCORES")
    print("=" * 65)
    for task, score in scores.items():
        bar = "#" * int(score * 40)
        print(f"  {task:<22} {score:.4f}  |{bar}")
    avg = sum(scores.values()) / len(scores)
    print(f"\n  {'AVERAGE':<22} {avg:.4f}")
    success = sum(1 for s in scores.values() if s > 0.5) == len(scores)
    print(f"\n  All tasks scoring > 0.5: {'YES' if success else 'NO'}")