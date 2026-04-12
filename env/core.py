import random
from env.models import Observation, Instance, Volume, Database, Action
from env.pricing import DOWNGRADE_MAP, UPGRADE_MAP, instance_hourly_cost, volume_hourly_cost

# Per-task step budgets — compliance_sprint is deliberately tight
TASK_MAX_STEPS: dict[str, int] = {
    "spend_guard":       10,
    "compliance_sprint": 5,
    "rightsizer":        10,
    "cloud_auditor":     10,
}

# Health penalty when an instance is stopped (spend_guard task)
CRITICALITY_HEALTH_PENALTY: dict[str, float] = {
    "high":   0.45,
    "medium": 0.15,
    "low":    0.03,
}


def _clamp01_open(x: float) -> float:
    return float(min(0.99, max(0.01, x)))


def _hex_id(prefix: str, length: int = 17) -> str:
    """Generate a realistic-looking AWS resource ID."""
    chars = "0123456789abcdef"
    return f"{prefix}-{''.join(random.choice(chars) for _ in range(length))}"


def _compute_cost(obs: Observation) -> float:
    """Real-time hourly cost = sum of running instance rates + all volume rates."""
    inst_cost = sum(i.hourly_cost for i in obs.instances if i.status == "running")
    vol_cost  = sum(v.hourly_cost for v in obs.volumes)
    return round(inst_cost + vol_cost, 4)


class CloudEnv:
    def __init__(self):
        self._state: Observation | None = None
        self.steps: int = 0
        self._task: str = "cloud_auditor"
        self._max_counts: dict = {}

    # ── Health & Alerts ────────────────────────────────────────────────────────

    def _update_health(self) -> None:
        """Recompute health from current state.
        spend_guard health is cumulative (managed in step()), so we skip it here."""
        if self._task == "spend_guard":
            return
        health = 1.0
        if any(db.publicly_accessible for db in self._state.databases):
            health -= 0.25
        if any(not v.encrypted for v in self._state.volumes if v.state == "in-use"):
            health -= 0.10
        if any(i.tag == "prod" and i.status == "stopped" for i in self._state.instances):
            health -= 0.50
        if any(i.protected and i.status == "stopped" for i in self._state.instances):
            health -= 0.40
        if any(i.status == "running" and 5 <= i.cpu_utilization < 30 and i.downgrade_target
               for i in self._state.instances):
            health -= 0.05
        if any(i.status == "running" and i.cpu_utilization > 75 and i.upgrade_target
               for i in self._state.instances):
            health -= 0.10
        self._state.health = max(0.0, health)

    def _generate_alerts(self) -> list[str]:
        alerts = []
        if any(db.publicly_accessible for db in self._state.databases):
            alerts.append("SECURITY_HUB: RDS_PUBLICLY_ACCESSIBLE")
        if any(not v.encrypted for v in self._state.volumes if v.state == "in-use"):
            alerts.append("SECURITY_HUB: EBS_UNENCRYPTED")
        if any(v.state == "available" and v.age > 30 for v in self._state.volumes):
            alerts.append("TRUSTED_ADVISOR: UNATTACHED_EBS_VOLUME")
        if any(i.tag == "dev" and i.cpu_utilization < 5 and i.status == "running"
               and not i.protected for i in self._state.instances):
            alerts.append("TRUSTED_ADVISOR: IDLE_EC2_INSTANCE")
        if any(i.status == "running" and 5 <= i.cpu_utilization < 30 and i.downgrade_target
               for i in self._state.instances):
            alerts.append("TRUSTED_ADVISOR: OVERPROVISIONED_EC2")
        if any(i.status == "running" and i.cpu_utilization > 75 and i.upgrade_target
               for i in self._state.instances):
            alerts.append("TRUSTED_ADVISOR: UNDERPROVISIONED_EC2")
        return alerts

    # ── Potential-based reward shaping ─────────────────────────────────────────

    def _potential(self, obs: Observation) -> float:
        """Negative of remaining work. Task-specific formulation."""
        if self._task == "spend_guard":
            n_i = max(1, self._max_counts.get("stoppable", 1))
            n_z = max(1, self._max_counts.get("zombies", 1))
            low_running = sum(
                1 for i in obs.instances if i.status == "running" and i.criticality == "low"
            ) / n_i
            zombies = sum(
                1 for v in obs.volumes if v.state == "available" and v.age > 30
            ) / n_z
            return -(0.6 * low_running + 0.4 * zombies)

        elif self._task == "compliance_sprint":
            n_c = max(1, self._max_counts.get("critical", 1))
            n_h = max(1, self._max_counts.get("high", 1))
            n_m = max(1, self._max_counts.get("medium", 1))
            critical = sum(1 for db in obs.databases if db.publicly_accessible) / n_c
            high     = sum(1 for v in obs.volumes if not v.encrypted and v.state == "in-use") / n_h
            medium   = sum(
                1 for i in obs.instances
                if i.tag == "dev" and i.cpu_utilization < 5 and i.status == "running"
                and not i.protected
            ) / n_m
            return -(0.6 * critical + 0.3 * high + 0.1 * medium)

        elif self._task == "rightsizer":
            n_o = max(1, self._max_counts.get("overprovisioned", 1))
            n_u = max(1, self._max_counts.get("underprovisioned", 1))
            over  = sum(1 for i in obs.instances
                        if i.status == "running" and 5 <= i.cpu_utilization < 30
                        and i.downgrade_target) / n_o
            under = sum(1 for i in obs.instances
                        if i.status == "running" and i.cpu_utilization > 75
                        and i.upgrade_target) / n_u
            return -(0.5 * over + 0.5 * under)

        else:  # cloud_auditor
            n_b = max(1, self._max_counts.get("insecure", 1))
            n_z = max(1, self._max_counts.get("zombies", 1))
            n_o = max(1, self._max_counts.get("overprovisioned", 1))
            insecure = sum(1 for db in obs.databases if db.publicly_accessible) / n_b
            zombies  = sum(1 for v in obs.volumes if v.state == "available" and v.age > 30) / n_z
            over     = sum(
                1 for i in obs.instances
                if i.status == "running" and 5 <= i.cpu_utilization < 30
                and i.downgrade_target and not i.protected
            ) / n_o
            return -(0.5 * insecure + 0.3 * zombies + 0.2 * over)

    def _is_done(self) -> bool:
        if self._task == "spend_guard":
            return False  # runs to MAX_STEPS; grader evaluates final state

        if self._task == "compliance_sprint":
            return (
                not any(db.publicly_accessible for db in self._state.databases)
                and not any(
                    not v.encrypted for v in self._state.volumes if v.state == "in-use"
                )
            )

        if self._task == "rightsizer":
            return (
                not any(
                    i.status == "running" and 5 <= i.cpu_utilization < 30 and i.downgrade_target
                    for i in self._state.instances
                )
                and not any(
                    i.status == "running" and i.cpu_utilization > 75 and i.upgrade_target
                    for i in self._state.instances
                )
            )

        # cloud_auditor
        return (
            not any(db.publicly_accessible for db in self._state.databases)
            and not any(v.state == "available" and v.age > 30 for v in self._state.volumes)
            and not any(
                i.status == "running" and 5 <= i.cpu_utilization < 30
                and i.downgrade_target and not i.protected
                for i in self._state.instances
            )
        )

    # ── Reset Scenarios ────────────────────────────────────────────────────────

    def _reset_spend_guard(self, rng: random.Random) -> Observation:
        """
        Task 1 — Cost vs Availability.
        The HIGH-criticality prod instances are expensive (very tempting to stop) but stopping
        any of them drops health below the SLA threshold (0.65) → near-zero grader score.
        Correct strategy: stop LOW instances, delete zombies, optionally downgrade MEDIUM.
        """
        inst_low1 = Instance(
            id=_hex_id("i"), instance_type="g4dn.xlarge",
            cpu_utilization=round(rng.uniform(2, 12), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("g4dn.xlarge"), criticality="low",
        )
        inst_low2 = Instance(
            id=_hex_id("i"), instance_type="m5.large",
            cpu_utilization=round(rng.uniform(3, 10), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("m5.large"), criticality="low",
        )
        inst_med = Instance(
            id=_hex_id("i"), instance_type="m5.xlarge",
            cpu_utilization=round(rng.uniform(22, 38), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("m5.xlarge"), criticality="medium",
            downgrade_target=DOWNGRADE_MAP.get("m5.xlarge"),
        )
        inst_high1 = Instance(
            id=_hex_id("i"), instance_type="c6i.4xlarge",
            cpu_utilization=round(rng.uniform(60, 85), 1), status="running", tag="prod",
            hourly_cost=instance_hourly_cost("c6i.4xlarge"), criticality="high",
        )
        inst_high2 = Instance(
            id=_hex_id("i"), instance_type="m5.2xlarge",
            cpu_utilization=round(rng.uniform(55, 80), 1), status="running", tag="prod",
            hourly_cost=instance_hourly_cost("m5.2xlarge"), criticality="high",
        )
        vol_z1  = Volume(id=_hex_id("vol"), volume_type="io2", state="available",
                         age=rng.randint(40, 90), hourly_cost=volume_hourly_cost("io2"))
        vol_z2  = Volume(id=_hex_id("vol"), volume_type="gp3", state="available",
                         age=rng.randint(35, 70), hourly_cost=volume_hourly_cost("gp3"))
        vol_use = Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use",
                         age=rng.randint(5, 30),  hourly_cost=volume_hourly_cost("gp3"))
        obs = Observation(
            instances=[inst_low1, inst_low2, inst_med, inst_high1, inst_high2],
            volumes=[vol_z1, vol_z2, vol_use],
            databases=[Database(id=_hex_id("rds"), publicly_accessible=False)],
            cost=0.0, health=1.0,
        )
        obs.cost = _compute_cost(obs)
        return obs

    def _reset_compliance_sprint(self, rng: random.Random) -> Observation:
        """
        Task 2 — Security Compliance Under Step Budget (MAX_STEPS = 5).
        CRITICAL: 2 public DBs (fix: secure_database).
        HIGH:     3 unencrypted in-use volumes (fix: encrypt_volume).
        MEDIUM:   1 idle dev instance (fix: stop_instance).
        Decoy:    1 zombie volume — a COST issue, NOT a compliance issue.
        6 issues, 5 steps → agent MUST skip the MEDIUM to maximise score.
        """
        db1 = Database(id=_hex_id("rds"), publicly_accessible=True)   # CRITICAL
        db2 = Database(id=_hex_id("rds"), publicly_accessible=True)   # CRITICAL
        db3 = Database(id=_hex_id("rds"), publicly_accessible=False)  # safe reference
        vol_e1 = Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use",
                        age=rng.randint(10, 40), hourly_cost=volume_hourly_cost("gp3"),
                        encrypted=False)  # HIGH
        vol_e2 = Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use",
                        age=rng.randint(10, 40), hourly_cost=volume_hourly_cost("gp3"),
                        encrypted=False)  # HIGH
        vol_e3 = Volume(id=_hex_id("vol"), volume_type="io2", state="in-use",
                        age=rng.randint(5,  30), hourly_cost=volume_hourly_cost("io2"),
                        encrypted=False)  # HIGH
        vol_zombie = Volume(id=_hex_id("vol"), volume_type="gp3", state="available",
                            age=rng.randint(40, 80), hourly_cost=volume_hourly_cost("gp3"),
                            encrypted=True)   # DECOY — cost issue, not compliance
        inst_idle = Instance(
            id=_hex_id("i"), instance_type="t3.medium",
            cpu_utilization=round(rng.uniform(0.5, 4.0), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("t3.medium"),
        )  # MEDIUM compliance issue
        obs = Observation(
            instances=[inst_idle],
            volumes=[vol_e1, vol_e2, vol_e3, vol_zombie],
            databases=[db1, db2, db3],
            cost=0.0, health=1.0,
        )
        obs.cost = _compute_cost(obs)
        return obs

    def _reset_rightsizer(self, rng: random.Random) -> Observation:
        """
        Task 3 — Bidirectional Fleet Rightsizing.
        Overprovisioned (downgrade_target set, CPU 7-20%): downgrade them.
        Underprovisioned (upgrade_target set, CPU 82-97%): upgrade them.
        Right-sized (no target, CPU 42-65%): DO NOT TOUCH — they are traps.
        Wrong direction or touching right-sized = 0.25 penalty per mistake.
        """
        # Overprovisioned
        inst_over1 = Instance(
            id=_hex_id("i"), instance_type="m5.xlarge",
            cpu_utilization=round(rng.uniform(7, 18), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("m5.xlarge"),
            downgrade_target=DOWNGRADE_MAP.get("m5.xlarge"),
        )
        inst_over2 = Instance(
            id=_hex_id("i"), instance_type="c6i.4xlarge",
            cpu_utilization=round(rng.uniform(8, 20), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("c6i.4xlarge"),
            downgrade_target=DOWNGRADE_MAP.get("c6i.4xlarge"),
        )
        # Underprovisioned
        inst_under1 = Instance(
            id=_hex_id("i"), instance_type="t3.medium",
            cpu_utilization=round(rng.uniform(82, 97), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("t3.medium"),
            upgrade_target=UPGRADE_MAP.get("t3.medium"),
        )
        inst_under2 = Instance(
            id=_hex_id("i"), instance_type="g4dn.medium",
            cpu_utilization=round(rng.uniform(85, 97), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("g4dn.medium"),
            upgrade_target=UPGRADE_MAP.get("g4dn.medium"),
        )
        # Right-sized traps (CPU 42-65%, no targets)
        inst_right1 = Instance(
            id=_hex_id("i"), instance_type="m5.large",
            cpu_utilization=round(rng.uniform(42, 62), 1), status="running", tag="prod",
            hourly_cost=instance_hourly_cost("m5.large"),
        )
        inst_right2 = Instance(
            id=_hex_id("i"), instance_type="c6i.2xlarge",
            cpu_utilization=round(rng.uniform(45, 65), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("c6i.2xlarge"),
        )
        vol1 = Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use",
                      age=rng.randint(10, 50), hourly_cost=volume_hourly_cost("gp3"))
        obs = Observation(
            instances=[inst_over1, inst_over2, inst_under1, inst_under2,
                       inst_right1, inst_right2],
            volumes=[vol1],
            databases=[Database(id=_hex_id("rds"), publicly_accessible=False)],
            cost=0.0, health=1.0,
        )
        obs.cost = _compute_cost(obs)
        return obs

    def _reset_cloud_auditor(self, rng: random.Random) -> Observation:
        """
        Task 4 — Multi-domain Audit with Protected Resource Trap.
        Security issue: 1 publicly accessible DB.
        Cost issues: 1 overprovisioned instance + 2 zombie volumes.
        Trap: 1 PROTECTED idle dev instance — looks exactly stoppable but must NOT be touched.
        Hard fail if protected instance is stopped or downgraded.
        """
        db_public  = Database(id=_hex_id("rds"), publicly_accessible=True)   # SECURITY
        db_private = Database(id=_hex_id("rds"), publicly_accessible=False)  # background
        inst_over  = Instance(
            id=_hex_id("i"), instance_type="m5.xlarge",
            cpu_utilization=round(rng.uniform(8, 18), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("m5.xlarge"),
            downgrade_target=DOWNGRADE_MAP.get("m5.xlarge"),
        )
        inst_protected = Instance(
            id=_hex_id("i"), instance_type="t3.medium",
            cpu_utilization=round(rng.uniform(1, 4), 1), status="running", tag="dev",
            hourly_cost=instance_hourly_cost("t3.medium"),
            protected=True,   # Looks like idle dev → intentional TRAP
        )
        inst_prod = Instance(
            id=_hex_id("i"), instance_type="c6i.4xlarge",
            cpu_utilization=round(rng.uniform(60, 85), 1), status="running", tag="prod",
            hourly_cost=instance_hourly_cost("c6i.4xlarge"),
        )
        vol_z1  = Volume(id=_hex_id("vol"), volume_type="io2", state="available",
                         age=rng.randint(40, 90), hourly_cost=volume_hourly_cost("io2"))
        vol_z2  = Volume(id=_hex_id("vol"), volume_type="gp3", state="available",
                         age=rng.randint(35, 75), hourly_cost=volume_hourly_cost("gp3"))
        vol_use = Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use",
                         age=rng.randint(5, 20),  hourly_cost=volume_hourly_cost("gp3"))
        obs = Observation(
            instances=[inst_over, inst_protected, inst_prod],
            volumes=[vol_z1, vol_z2, vol_use],
            databases=[db_public, db_private],
            cost=0.0, health=1.0,
        )
        obs.cost = _compute_cost(obs)
        return obs

    # ── Public API ─────────────────────────────────────────────────────────────

    def reset(self, task: str = "cloud_auditor") -> dict:
        self.steps = 0
        self._task = task
        rng = random.Random()

        if task == "spend_guard":
            self._state = self._reset_spend_guard(rng)
        elif task == "compliance_sprint":
            self._state = self._reset_compliance_sprint(rng)
        elif task == "rightsizer":
            self._state = self._reset_rightsizer(rng)
        else:
            self._state = self._reset_cloud_auditor(rng)

        self._state.alerts = self._generate_alerts()
        self._max_counts = {
            # spend_guard
            "stoppable":       max(1, sum(1 for i in self._state.instances
                                         if i.criticality in ("low", "medium") and i.status == "running")),
            "zombies":         max(1, sum(1 for v in self._state.volumes
                                         if v.state == "available" and v.age > 30)),
            # compliance_sprint
            "critical":        max(1, sum(1 for db in self._state.databases
                                         if db.publicly_accessible)),
            "high":            max(1, sum(1 for v in self._state.volumes
                                         if not v.encrypted and v.state == "in-use")),
            "medium":          max(1, sum(1 for i in self._state.instances
                                         if i.tag == "dev" and i.cpu_utilization < 5
                                         and i.status == "running" and not i.protected)),
            # rightsizer + cloud_auditor
            "overprovisioned": max(1, sum(1 for i in self._state.instances
                                         if i.status == "running"
                                         and 5 <= i.cpu_utilization < 30
                                         and i.downgrade_target)),
            "underprovisioned": max(1, sum(1 for i in self._state.instances
                                          if i.status == "running"
                                          and i.cpu_utilization > 75
                                          and i.upgrade_target)),
            # cloud_auditor
            "insecure":        max(1, sum(1 for db in self._state.databases
                                         if db.publicly_accessible)),
        }
        return self._state.model_dump()

    def state(self) -> dict:
        if self._state is None:
            self.reset()
        return self._state.model_dump()

    def step(self, action: dict) -> tuple[dict, float, bool, dict]:
        if self._state is None:
            self.reset()

        action_obj = Action(**action)
        self.steps += 1

        step_reward  = -0.01
        terminal_bonus = 0.0
        done = False
        info: dict = {"action_success": False, "reason": ""}

        phi_before = self._potential(self._state)

        # ── delete_volume ───────────────────────────────────────────────────────
        if action_obj.action_type == "delete_volume":
            found = False
            for v in self._state.volumes:
                if v.id == action_obj.target_id:
                    found = True
                    if v.state == "available" and v.age > 30:
                        self._state.volumes.remove(v)
                        self._state.cost = _compute_cost(self._state)
                        step_reward += 0.15
                        info = {"action_success": True,
                                "reason": f"deleted zombie {v.volume_type} volume (saved ${v.hourly_cost:.4f}/hr)"}
                    elif v.state == "in-use":
                        step_reward -= 0.30
                        info["reason"] = "attempted to delete an attached (in-use) volume"
                    else:
                        step_reward -= 0.05
                        info["reason"] = "volume age < 30 days — not a zombie yet"
                    break
            if not found:
                step_reward -= 0.20
                info["reason"] = "EBS volume not found"

        # ── stop_instance ───────────────────────────────────────────────────────
        elif action_obj.action_type == "stop_instance":
            found = False
            for inst in self._state.instances:
                if inst.id == action_obj.target_id:
                    found = True
                    if inst.protected:
                        step_reward -= 0.50
                        info["reason"] = "CRITICAL: instance is protected — must not be stopped"
                    elif inst.tag == "prod" and self._task != "spend_guard":
                        step_reward -= 0.50
                        info["reason"] = "CRITICAL: cannot stop a production instance"
                    elif inst.status == "running":
                        inst.status = "stopped"
                        self._state.cost = _compute_cost(self._state)
                        if self._task == "spend_guard":
                            penalty = CRITICALITY_HEALTH_PENALTY.get(inst.criticality, 0.10)
                            self._state.health = max(0.0, self._state.health - penalty)
                        step_reward += 0.30
                        info = {"action_success": True,
                                "reason": f"stopped {inst.criticality}-criticality "
                                          f"{inst.instance_type} (saved ${inst.hourly_cost:.4f}/hr)"}
                    else:
                        step_reward -= 0.05
                        info["reason"] = "instance already stopped"
                    break
            if not found:
                step_reward -= 0.20
                info["reason"] = "EC2 instance not found"

        # ── secure_database ─────────────────────────────────────────────────────
        elif action_obj.action_type == "secure_database":
            found = False
            for db in self._state.databases:
                if db.id == action_obj.target_id:
                    found = True
                    if db.publicly_accessible:
                        db.publicly_accessible = False
                        step_reward += 0.50
                        info = {"action_success": True,
                                "reason": "secured publicly accessible RDS database"}
                    else:
                        step_reward -= 0.05
                        info["reason"] = "RDS database is already private"
                    break
            if not found:
                step_reward -= 0.20
                info["reason"] = "RDS database not found"

        # ── downgrade_instance ──────────────────────────────────────────────────
        elif action_obj.action_type == "downgrade_instance":
            found = False
            for inst in self._state.instances:
                if inst.id == action_obj.target_id:
                    found = True
                    if inst.protected:
                        step_reward -= 0.40
                        info["reason"] = "CRITICAL: instance is protected — must not be downgraded"
                    elif inst.downgrade_target and inst.status == "running":
                        old_cost  = inst.hourly_cost
                        new_type  = inst.downgrade_target
                        inst.instance_type  = new_type
                        inst.hourly_cost    = instance_hourly_cost(new_type)
                        inst.downgrade_target = None   # single-step action, target cleared
                        self._state.cost = _compute_cost(self._state)
                        savings = round(old_cost - inst.hourly_cost, 4)
                        step_reward += 0.40
                        info = {"action_success": True,
                                "reason": f"downgraded to {new_type} (saved ${savings:.4f}/hr)"}
                    else:
                        step_reward -= 0.10
                        info["reason"] = "instance not eligible for downgrade (no path or not running)"
                    break
            if not found:
                step_reward -= 0.20
                info["reason"] = "EC2 instance not found"

        # ── upgrade_instance (new) ──────────────────────────────────────────────
        elif action_obj.action_type == "upgrade_instance":
            found = False
            for inst in self._state.instances:
                if inst.id == action_obj.target_id:
                    found = True
                    if inst.upgrade_target and inst.status == "running":
                        old_cost  = inst.hourly_cost
                        new_type  = inst.upgrade_target
                        inst.instance_type  = new_type
                        inst.hourly_cost    = instance_hourly_cost(new_type)
                        inst.upgrade_target = None   # single-step action, target cleared
                        self._state.cost = _compute_cost(self._state)
                        extra = round(inst.hourly_cost - old_cost, 4)
                        step_reward += 0.40
                        info = {"action_success": True,
                                "reason": f"upgraded to {new_type} (+${extra:.4f}/hr — resolves performance bottleneck)"}
                    elif not inst.upgrade_target:
                        step_reward -= 0.15
                        info["reason"] = "instance has no upgrade path (not underprovisioned)"
                    else:
                        step_reward -= 0.05
                        info["reason"] = "instance is not running"
                    break
            if not found:
                step_reward -= 0.20
                info["reason"] = "EC2 instance not found"

        # ── encrypt_volume (new) ────────────────────────────────────────────────
        elif action_obj.action_type == "encrypt_volume":
            found = False
            for v in self._state.volumes:
                if v.id == action_obj.target_id:
                    found = True
                    if not v.encrypted and v.state == "in-use":
                        v.encrypted = True
                        step_reward += 0.35
                        info = {"action_success": True,
                                "reason": f"encrypted {v.volume_type} volume (HIGH compliance issue resolved)"}
                    elif v.encrypted:
                        step_reward -= 0.05
                        info["reason"] = "volume is already encrypted"
                    else:
                        step_reward -= 0.10
                        info["reason"] = "can only encrypt in-use volumes; unattached should be deleted"
                    break
            if not found:
                step_reward -= 0.20
                info["reason"] = "EBS volume not found"

        # ── noop ────────────────────────────────────────────────────────────────
        elif action_obj.action_type == "noop":
            step_reward -= 0.05
            info["reason"] = "no operation performed"

        # ── Reward shaping ──────────────────────────────────────────────────────
        phi_after   = self._potential(self._state)
        step_reward += 0.99 * phi_after - phi_before
        step_reward = _clamp01_open(max(0.0, min(1.0, step_reward)))

        # ── Terminal check ──────────────────────────────────────────────────────
        max_steps = TASK_MAX_STEPS.get(self._task, 10)
        if self._is_done():
            done = True
            efficiency     = (max_steps - self.steps) / max_steps
            terminal_bonus = _clamp01_open(round(0.20 + 0.25 * efficiency, 4))
            info["reason"] = "all infrastructure issues resolved"
        elif self.steps >= max_steps:
            done = True
            info["reason"] = "step budget exhausted"

        # ── State refresh ───────────────────────────────────────────────────────
        self._update_health()
        self._state.alerts = self._generate_alerts()

        total = max(0.05, min(0.95, round(step_reward + terminal_bonus, 4)))
        return self._state.model_dump(), total, done, info