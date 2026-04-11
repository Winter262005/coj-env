import math

def _clamp01_open(score: float) -> float:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return 0.05
    if not math.isfinite(s):
        return 0.05
    return min(0.99, max(0.01, s))


def zombie_reaper_grader(initial: dict, final: dict) -> float:
    # Identify zombie EBS volumes (state="available" and age > 30)
    initial_zombies = [
        v for v in initial.get("volumes", [])
        if v.get("state") == "available" and v.get("age", 0) > 30
    ]
    total = len(initial_zombies)

    # Integrity check – penalise deleting in-use volumes
    initial_ids = {v["id"] for v in initial.get("volumes", [])}
    final_ids = {v["id"] for v in final.get("volumes", [])}
    deleted_ids = initial_ids - final_ids
    was_in_use = {
        v["id"] for v in initial.get("volumes", []) if v.get("state") == "in-use"
    }
    if deleted_ids & was_in_use:
        return _clamp01_open(0.0)

    if total == 0:
        return _clamp01_open(1.0)

    remaining = [
        v for v in final.get("volumes", [])
        if v.get("state") == "available" and v.get("age", 0) > 30
    ]
    deleted = total - len(remaining)

    raw = deleted / total if total > 0 else 0.0
    return _clamp01_open(raw)


def dev_shutdown_grader(initial: dict, final: dict) -> float:
    # Integrity check – penalise stopping prod EC2 instances
    prod_stopped = any(
        i.get("tag") == "prod" and i.get("status") == "stopped"
        for i in final.get("instances", [])
    )
    if prod_stopped:
        return _clamp01_open(0.0)

    # Target dev EC2 instances: low CPU utilization and running
    initial_targets = [
        i for i in initial.get("instances", [])
        if (
            i.get("tag") == "dev"
            and i.get("cpu_utilization", 100) < 5
            and i.get("status") == "running"
        )
    ]
    total = len(initial_targets)

    if total == 0:
        return _clamp01_open(1.0)

    target_ids = {i["id"] for i in initial_targets}
    final_stopped = [
        i for i in final.get("instances", [])
        if i["id"] in target_ids and i.get("status") == "stopped"
    ]
    stopped = len(final_stopped)

    raw = stopped / total if total > 0 else 0.0
    return _clamp01_open(raw)


def auditor_grader(initial: dict, final: dict) -> float:
    initial_cost = float(initial.get("cost", 0.0))
    final_cost = float(final.get("cost", 0.0))

    dev_targets = [
        i for i in initial.get("instances", [])
        if i.get("tag") == "dev" and i.get("cpu_utilization", 100) < 5
    ]
    zombies = [
        v for v in initial.get("volumes", [])
        if v.get("state") == "available" and v.get("age", 0) > 30
    ]
    max_savings = len(dev_targets) * 20 + len(zombies) * 30  # Adjusted weighting for realistic costs
    if max_savings <= 0:
        max_savings = 50.0

    cost_raw = (initial_cost - final_cost) / max_savings
    cost_score = _clamp01_open(cost_raw)

    initial_public = [db for db in initial.get("databases", []) if db.get("publicly_accessible")]
    final_public = [db for db in final.get("databases", []) if db.get("publicly_accessible")]
    
    if len(initial_public) == 0:
        sec_raw = 1.0
    else:
        secured = len(initial_public) - len(final_public)
        sec_raw = secured / len(initial_public)
    security_score = _clamp01_open(sec_raw)

    final_alerts = len(final.get("alerts", []))
    initial_alerts = len(initial.get("alerts", []))
    if initial_alerts > 0 and final_alerts == 0:
        eff_raw = 1.0
    elif initial_alerts <= 0:
        eff_raw = 0.5
    else:
        eff_raw = (initial_alerts - final_alerts) / max(1, initial_alerts)
    efficiency_score = _clamp01_open(eff_raw)

    prod_down = any(
        i.get("tag") == "prod" and i.get("status") == "stopped"
        for i in final.get("instances", [])
    )
    initial_ids = {v["id"] for v in initial.get("volumes", [])}
    final_ids = {v["id"] for v in final.get("volumes", [])}
    deleted_ids = initial_ids - final_ids
    was_in_use = {
        v["id"] for v in initial.get("volumes", []) if v.get("state") == "in-use"
    }
    integrity_ok = (not prod_down) and not (deleted_ids & was_in_use)

    int_raw = 1.0 if integrity_ok else 0.0
    integrity_score = _clamp01_open(int_raw)

    raw = (
        0.40 * cost_score +
        0.35 * security_score +
        0.15 * efficiency_score +
        0.10 * integrity_score
    )

    return _clamp01_open(raw)