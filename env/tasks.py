def _clamp01_open(score: float) -> float:
    """
    Enforce strict open interval (0.0, 1.0) — never exactly 0 or 1.
    We use 0.01 and 0.99 so even if the platform rounds to 2 decimals,
    the value stays strictly inside (0, 1).
    """
    return float(min(0.99, max(0.01, score)))


def zombie_reaper_grader(initial: dict, final: dict) -> float:
    initial_zombies = [
        v for v in initial.get("volumes", [])
        if not v.get("attached") and v.get("age", 0) > 30
    ]
    total = len(initial_zombies)

    # Integrity check – penalise deleting attached volumes
    initial_ids = {v["id"] for v in initial.get("volumes", [])}
    final_ids = {v["id"] for v in final.get("volumes", [])}
    deleted_ids = initial_ids - final_ids
    was_attached = {
        v["id"] for v in initial.get("volumes", []) if v.get("attached")
    }
    if deleted_ids & was_attached:
        # worst score but strictly > 0
        return _clamp01_open(0.0)

    if total == 0:
        # best score but strictly < 1
        return _clamp01_open(1.0)

    remaining = [
        v for v in final.get("volumes", [])
        if not v.get("attached") and v.get("age", 0) > 30
    ]
    deleted = total - len(remaining)
    return _clamp01_open(deleted / total)


def dev_shutdown_grader(initial: dict, final: dict) -> float:
    # Integrity check – penalise stopping prod instances
    prod_stopped = any(
        i.get("tag") == "prod" and i.get("status") == "stopped"
        for i in final.get("instances", [])
    )
    if prod_stopped:
        return _clamp01_open(0.0)

    initial_targets = [
        i for i in initial.get("instances", [])
        if i.get("tag") == "dev" and i.get("cpu", 100) < 5
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
    return _clamp01_open(stopped / total)


def auditor_grader(initial: dict, final: dict) -> float:
    # Cost score (weight 0.40)
    initial_cost = initial.get("cost", 0)
    final_cost = final.get("cost", 0)

    dev_targets = [
        i for i in initial.get("instances", [])
        if i.get("tag") == "dev" and i.get("cpu", 100) < 5
    ]
    zombies = [
        v for v in initial.get("volumes", [])
        if not v.get("attached") and v.get("age", 0) > 30
    ]
    max_savings = len(dev_targets) * 10 + len(zombies) * 5
    if max_savings == 0:
        max_savings = 20

    cost_score = (initial_cost - final_cost) / max_savings
    cost_score = _clamp01_open(cost_score)

    # Security score (weight 0.35)
    initial_public = [
        db for db in initial.get("databases", []) if db.get("public")
    ]
    final_public = [
        db for db in final.get("databases", []) if db.get("public")
    ]
    if len(initial_public) == 0:
        security_score = _clamp01_open(1.0)
    else:
        secured = len(initial_public) - len(final_public)
        security_score = _clamp01_open(secured / len(initial_public))

    # Efficiency score (weight 0.15)
    final_alerts = len(final.get("alerts", []))
    initial_alerts = len(initial.get("alerts", []))
    if initial_alerts > 0 and final_alerts == 0:
        efficiency_score = _clamp01_open(1.0)
    else:
        efficiency_score = _clamp01_open(
            (initial_alerts - final_alerts) / max(1, initial_alerts)
        )

    # Integrity score (weight 0.10)
    prod_down = any(
        i.get("tag") == "prod" and i.get("status") == "stopped"
        for i in final.get("instances", [])
    )
    initial_ids = {v["id"] for v in initial.get("volumes", [])}
    final_ids = {v["id"] for v in final.get("volumes", [])}
    deleted_ids = initial_ids - final_ids
    was_attached = {
        v["id"] for v in initial.get("volumes", []) if v.get("attached")
    }
    integrity_ok = not prod_down and not (deleted_ids & was_attached)
    integrity_score = _clamp01_open(1.0 if integrity_ok else 0.0)

    raw = (
        0.40 * cost_score +
        0.35 * security_score +
        0.15 * efficiency_score +
        0.10 * integrity_score
    )
    return _clamp01_open(raw)