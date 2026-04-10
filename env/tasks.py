def _clamp01_open(score: float) -> float:
    """
    Enforce strict open interval (0.0, 1.0) — never exactly 0 or 1.

    We deliberately clamp to [0.01, 0.99] so that even if the platform
    rounds to 2 decimal places, the values remain strictly inside (0, 1).
    """
    # First ensure it's a finite float
    s = float(score)
    if s != s or s == float("inf") or s == float("-inf"):
        # NaN or infinities should be handled as worst case but still in (0,1)
        return 0.05
    return 0.99 if s >= 0.99 else (0.01 if s <= 0.01 else s)


def zombie_reaper_grader(initial: dict, final: dict) -> float:
    # Identify zombie volumes in the initial state
    initial_zombies = [
        v for v in initial.get("volumes", [])
        if (not v.get("attached")) and v.get("age", 0) > 30
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
        # worst-case score, but strictly > 0 after clamp
        return _clamp01_open(0.0)

    if total == 0:
        # nothing to clean up -> best score, but strictly < 1 after clamp
        return _clamp01_open(1.0)

    remaining = [
        v for v in final.get("volumes", [])
        if (not v.get("attached")) and v.get("age", 0) > 30
    ]
    deleted = total - len(remaining)

    raw = deleted / total if total > 0 else 0.0
    return _clamp01_open(raw)


def dev_shutdown_grader(initial: dict, final: dict) -> float:
    # Integrity check – penalise stopping prod instances
    prod_stopped = any(
        i.get("tag") == "prod" and i.get("status") == "stopped"
        for i in final.get("instances", [])
    )
    if prod_stopped:
        return _clamp01_open(0.0)

    # Target dev instances: low CPU usage and running
    initial_targets = [
        i for i in initial.get("instances", [])
        if (
            i.get("tag") == "dev"
            and i.get("cpu", 100) < 5
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
    """
    Combined task: cost savings, security, efficiency, and integrity.
    Returns a single score strictly in (0,1).
    """

    # ---- Cost score (weight 0.40) ----
    initial_cost = float(initial.get("cost", 0.0))
    final_cost = float(final.get("cost", 0.0))

    dev_targets = [
        i for i in initial.get("instances", [])
        if i.get("tag") == "dev" and i.get("cpu", 100) < 5
    ]
    zombies = [
        v for v in initial.get("volumes", [])
        if (not v.get("attached")) and v.get("age", 0) > 30
    ]
    max_savings = len(dev_targets) * 10 + len(zombies) * 5
    if max_savings <= 0:
        max_savings = 20.0

    cost_raw = (initial_cost - final_cost) / max_savings
    # allow over/under and then clamp into (0,1)
    cost_score = _clamp01_open(cost_raw)

    # ---- Security score (weight 0.35) ----
    initial_public = [
        db for db in initial.get("databases", []) if db.get("public")
    ]
    final_public = [
        db for db in final.get("databases", []) if db.get("public")
    ]
    if len(initial_public) == 0:
        sec_raw = 1.0
    else:
        secured = len(initial_public) - len(final_public)
        sec_raw = secured / len(initial_public)
    security_score = _clamp01_open(sec_raw)

    # ---- Efficiency score (weight 0.15) ----
    final_alerts = len(final.get("alerts", []))
    initial_alerts = len(initial.get("alerts", []))
    if initial_alerts > 0 and final_alerts == 0:
        eff_raw = 1.0
    elif initial_alerts <= 0:
        # nothing to reduce -> treat as neutral mid-score
        eff_raw = 0.5
    else:
        eff_raw = (initial_alerts - final_alerts) / max(1, initial_alerts)
    efficiency_score = _clamp01_open(eff_raw)

    # ---- Integrity score (weight 0.10) ----
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
    integrity_ok = (not prod_down) and not (deleted_ids & was_attached)

    int_raw = 1.0 if integrity_ok else 0.0
    integrity_score = _clamp01_open(int_raw)

    # ---- Weighted aggregate ----
    raw = (
        0.40 * cost_score +
        0.35 * security_score +
        0.15 * efficiency_score +
        0.10 * integrity_score
    )

    return _clamp01_open(raw)