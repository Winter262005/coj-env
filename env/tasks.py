def zombie_reaper_grader(initial: dict, final: dict) -> float:
    initial_zombies = [v for v in initial.get("volumes", [])
                       if not v.get("attached") and v.get("age", 0) > 30]
    total = len(initial_zombies)

    # Integrity check: penalise deleting attached volumes
    initial_ids   = {v["id"] for v in initial.get("volumes", [])}
    final_ids     = {v["id"] for v in final.get("volumes", [])}
    deleted_ids   = initial_ids - final_ids
    was_attached  = {v["id"] for v in initial.get("volumes", []) if v.get("attached")}
    
    if deleted_ids & was_attached:
        return 0.01   # mapped from 0.0 (integrity violation)

    if total == 0:
        return 0.99   # mapped from 1.0 (nothing to do, full marks)

    remaining = [v for v in final.get("volumes", [])
                 if not v.get("attached") and v.get("age", 0) > 30]
    deleted = total - len(remaining)
    
    # Mathematically squeeze [0, 1] into [0.01, 0.99] natively
    raw_score = deleted / total
    return round(0.01 + 0.98 * raw_score, 4)


def dev_shutdown_grader(initial: dict, final: dict) -> float:
    # Integrity check: penalise stopping prod instances
    prod_stopped = any(
        i.get("tag") == "prod" and i.get("status") == "stopped"
        for i in final.get("instances", [])
    )
    if prod_stopped:
        return 0.01

    initial_targets = [i for i in initial.get("instances", [])
                       if i.get("tag") == "dev" and i.get("cpu", 100) < 5]
    total = len(initial_targets)

    if total == 0:
        return 0.99

    target_ids   = {i["id"] for i in initial_targets}
    final_stopped = [i for i in final.get("instances", [])
                     if i["id"] in target_ids and i.get("status") == "stopped"]
    stopped = len(final_stopped)
    
    raw_score = stopped / total
    return round(0.01 + 0.98 * raw_score, 4)


def auditor_grader(initial: dict, final: dict) -> float:
    # Cost score (weight 0.40)
    initial_cost = initial.get("cost", 0)
    final_cost   = final.get("cost", 0)

    dev_targets = [i for i in initial.get("instances", [])
                   if i.get("tag") == "dev" and i.get("cpu", 100) < 5]
    zombies     = [v for v in initial.get("volumes", [])
                   if not v.get("attached") and v.get("age", 0) > 30]
    max_savings = len(dev_targets) * 10 + len(zombies) * 5
    if max_savings == 0:
        max_savings = 20  # fallback to avoid div/0

    cost_score = max(0.0, min(1.0, (initial_cost - final_cost) / max_savings))

    # Security score (weight 0.35)
    initial_public = [db for db in initial.get("databases", []) if db.get("public")]
    final_public   = [db for db in final.get("databases",   []) if db.get("public")]
    if len(initial_public) == 0:
        security_score = 1.0
    else:
        secured = len(initial_public) - len(final_public)
        # Ensure security score doesn't dip below 0 if they expose more DBs
        security_score = max(0.0, secured / len(initial_public)) 

    # Efficiency score (weight 0.15)
    final_alerts  = len(final.get("alerts", []))
    initial_alerts = len(initial.get("alerts", []))
    efficiency_score = 1.0 if initial_alerts > 0 and final_alerts == 0 else (
        max(0.0, (initial_alerts - final_alerts) / max(1, initial_alerts))
    )

    # Integrity score (weight 0.10)
    prod_down = any(
        i.get("tag") == "prod" and i.get("status") == "stopped"
        for i in final.get("instances", [])
    )
    initial_ids  = {v["id"] for v in initial.get("volumes", [])}
    final_ids    = {v["id"] for v in final.get("volumes", [])}
    deleted_ids  = initial_ids - final_ids
    was_attached = {v["id"] for v in initial.get("volumes", []) if v.get("attached")}
    
    integrity_score = 1.0 if (not prod_down and not (deleted_ids & was_attached)) else 0.0

    raw = (
        0.40 * cost_score +
        0.35 * security_score +
        0.15 * efficiency_score +
        0.10 * integrity_score
    )
    
    # Scale raw (0.0 to 1.0) into strictly (0.01 to 0.99)
    return round(0.01 + 0.98 * raw, 4)