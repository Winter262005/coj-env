"""
Run this locally to find EVERY out-of-range reward before submitting.
Usage:  python diagnose_rewards.py
Requires: the local server to be running on port 7860
"""
import requests

BASE = "http://localhost:7860"
TASKS = ["zombie_reaper", "dev_shutdown", "auditor"]
ACTIONS_PER_TASK = [
    # (action_type, target_id or None)
    ("noop",            None),
    ("delete_volume",   "v-1"),
    ("stop_instance",   "i-1"),
    ("secure_database", "db-1"),
    ("delete_volume",   "v-3"),   # attached â†’ should be penalised
    ("stop_instance",   "i-3"),   # prod â†’ should be penalised
]

violations = []

for task in TASKS:
    try:
        obs = requests.post(f"{BASE}/reset", json={"task": task}, timeout=10).json()
    except Exception as e:
        print(f"[ERROR] /reset failed for {task}: {e}")
        continue

    for atype, tid in ACTIONS_PER_TASK:
        action = {"action_type": atype}
        if tid:
            action["target_id"] = tid

        try:
            data   = requests.post(f"{BASE}/step", json=action, timeout=10).json()
            reward = float(data.get("reward", -999))
            done   = data.get("done", False)

            in_range = 0.0 < reward < 1.0
            status   = "âœ…" if in_range else "âŒ"
            if not in_range:
                violations.append((task, atype, tid, reward))

            print(f"{status} task={task:<14} action={atype:<18} target={str(tid):<6} reward={reward:.4f}")

            if done:
                # reset again for next test
                obs = requests.post(f"{BASE}/reset", json={"task": task}, timeout=10).json()
        except Exception as e:
            print(f"[ERROR] step failed: {e}")

    # Grade check
    try:
        grade = requests.get(f"{BASE}/grade/{task}", timeout=10).json()
        score = float(grade.get("score", -1))
        in_range = 0.0 < score < 1.0
        print(f"{'âœ…' if in_range else 'âŒ'} task={task:<14} GRADER SCORE={score:.4f}")
        if not in_range:
            violations.append((task, "GRADER", None, score))
    except Exception as e:
        print(f"[ERROR] grade failed: {e}")

print()
if violations:
    print(f"VIOLATIONS ({len(violations)}):")
    for task, atype, tid, val in violations:
        print(f"  âŒ task={task} action={atype} target={tid} value={val:.4f}  â† fix this")
else:
    print("All rewards and grader scores are strictly in (0.0, 1.0) âœ…")
    print("Safe to submit.")