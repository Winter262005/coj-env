"""
Run this locally to find EVERY out-of-range reward before submitting.
Usage:  python diagnose_rewards.py
Requires: the local server to be running on port 7860
"""
import requests

BASE  = "http://localhost:7860"
TASKS = ["spend_guard", "compliance_sprint", "rightsizer", "cloud_auditor"]

# Actions exercising all branches: valid, wrong-target, protected, prod, noop
ACTIONS_SAMPLE = [
    # (action_type, target_id_index_hint)
    # target_id will be resolved dynamically from the reset state
    ("noop",               None),
    ("delete_volume",      "zombie"),
    ("stop_instance",      "dev_low"),
    ("secure_database",    "public_db"),
    ("downgrade_instance", "overprovisioned"),
    ("upgrade_instance",   "underprovisioned"),
    ("encrypt_volume",     "unencrypted_vol"),
]

violations = []


def first_id(state: dict, kind: str):
    """Resolve a symbolic resource hint to an actual ID from the reset state."""
    instances = state.get("instances", [])
    volumes   = state.get("volumes",   [])
    databases = state.get("databases", [])

    if kind == "zombie":
        for v in volumes:
            if v.get("state") == "available" and v.get("age", 0) > 30:
                return v["id"]
    if kind == "dev_low":
        for i in instances:
            if i.get("tag") == "dev" and not i.get("protected", False):
                return i["id"]
    if kind == "public_db":
        for db in databases:
            if db.get("publicly_accessible"):
                return db["id"]
        return databases[0]["id"] if databases else None
    if kind == "overprovisioned":
        for i in instances:
            if i.get("downgrade_target"):
                return i["id"]
        return instances[0]["id"] if instances else None
    if kind == "underprovisioned":
        for i in instances:
            if i.get("upgrade_target"):
                return i["id"]
        return instances[0]["id"] if instances else None
    if kind == "unencrypted_vol":
        for v in volumes:
            if not v.get("encrypted", True) and v.get("state") == "in-use":
                return v["id"]
        return volumes[0]["id"] if volumes else None
    return None


for task in TASKS:
    try:
        obs = requests.post(f"{BASE}/reset", json={"task": task}, timeout=10).json()
    except Exception as e:
        print(f"[ERROR] /reset failed for {task}: {e}")
        continue

    for atype, hint in ACTIONS_SAMPLE:
        tid    = first_id(obs, hint) if hint else None
        action = {"action_type": atype}
        if tid:
            action["target_id"] = tid

        try:
            data   = requests.post(f"{BASE}/step", json=action, timeout=10).json()
            reward = float(data.get("reward", -999))
            done   = data.get("done", False)

            in_range = 0.0 < reward < 1.0
            status   = "OK " if in_range else "ERR"
            if not in_range:
                violations.append((task, atype, tid, reward))

            print(f"[{status}] task={task:<18} action={atype:<22} "
                  f"target={str(tid)[:20]:<20} reward={reward:.4f}")

            if done:
                obs = requests.post(f"{BASE}/reset", json={"task": task}, timeout=10).json()
        except Exception as e:
            print(f"[ERROR] step failed: {e}")

    # Grade check
    try:
        grade    = requests.get(f"{BASE}/grade/{task}", timeout=10).json()
        score    = float(grade.get("score", -1))
        in_range = 0.0 < score < 1.0
        print(f"[{'OK ' if in_range else 'ERR'}] task={task:<18} GRADER SCORE={score:.4f}")
        if not in_range:
            violations.append((task, "GRADER", None, score))
    except Exception as e:
        print(f"[ERROR] grade failed: {e}")
    print()

print("=" * 70)
if violations:
    print(f"VIOLATIONS ({len(violations)}):")
    for task, atype, tid, val in violations:
        print(f"  [ERR] task={task} action={atype} target={tid} value={val:.4f}  <- fix this")
else:
    print("All rewards and grader scores are strictly in (0.0, 1.0) -- Safe to submit.")