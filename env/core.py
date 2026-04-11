import random
from env.models import Observation, Instance, Volume, Database, Action

MAX_STEPS = 10

def _clamp01_open(x: float) -> float:
    return float(min(0.99, max(0.01, x)))

def _hex_id(prefix: str, length: int = 17) -> str:
    """Helper to generate realistic AWS Resource IDs."""
    chars = "0123456789abcdef"
    return f"{prefix}-{''.join(random.choice(chars) for _ in range(length))}"

class CloudEnv:
    def __init__(self):
        self._state: Observation | None = None
        self.steps: int = 0
        self._task: str = "auditor"  
        self._max_counts: dict = {}

    def _update_health(self) -> None:
        health = 1.0
        if any(db.publicly_accessible for db in self._state.databases):
            health -= 0.3
        if any(i.tag == "prod" and i.status == "stopped" for i in self._state.instances):
            health -= 0.5
        self._state.health = max(0.0, health)

    def _generate_alerts(self) -> list[str]:
        alerts = []
        if any(v.state == "available" and v.age > 30 for v in self._state.volumes):
            alerts.append("TRUSTED_ADVISOR: UNATTACHED_EBS_VOLUME")
        if any(db.publicly_accessible for db in self._state.databases):
            alerts.append("SECURITY_HUB: RDS_PUBLICLY_ACCESSIBLE")
        if any(i.tag == "dev" and i.cpu_utilization < 5 and i.status == "running" for i in self._state.instances):
            alerts.append("TRUSTED_ADVISOR: IDLE_EC2_INSTANCE")
        return alerts

    def _potential(self, obs: Observation) -> float:
        n_z = self._max_counts.get("zombies", 1)
        n_d = self._max_counts.get("devs", 1)
        n_b = self._max_counts.get("insecure", 1)
        z = sum(1 for v in obs.volumes if v.state == "available" and v.age > 30) / n_z
        d = sum(1 for i in obs.instances if i.tag == "dev" and i.cpu_utilization < 5 and i.status == "running") / n_d
        b = sum(1 for db in obs.databases if db.publicly_accessible) / n_b
        return -(0.5 * b + 0.3 * d + 0.2 * z)

    def _is_done(self) -> bool:
        if self._task == "zombie_reaper":
            return not any(v.state == "available" and v.age > 30 for v in self._state.volumes)
        if self._task == "dev_shutdown":
            return not any(i.tag == "dev" and i.cpu_utilization < 5 and i.status == "running" for i in self._state.instances)
        
        return (
            not any(v.state == "available" and v.age > 30 for v in self._state.volumes)
            and not any(i.tag == "dev" and i.cpu_utilization < 5 and i.status == "running" for i in self._state.instances)
            and not any(db.publicly_accessible for db in self._state.databases)
        )

    def _reset_zombie_reaper(self, rng: random.Random) -> Observation:
        return Observation(
            instances=[
                Instance(id=_hex_id("i"), instance_type="t3.medium", cpu_utilization=round(rng.uniform(20, 80), 1), status="running", tag="dev"),
                Instance(id=_hex_id("i"), instance_type="m5.large", cpu_utilization=round(rng.uniform(55, 90), 1), status="running", tag="prod"),
            ],
            volumes=[
                Volume(id=_hex_id("vol"), volume_type="io2", state="available", age=rng.randint(35, 90)),
                Volume(id=_hex_id("vol"), volume_type="gp3", state="available", age=rng.randint(35, 75)),
                Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use", age=rng.randint(5, 20)),
            ],
            databases=[Database(id=_hex_id("rds"), publicly_accessible=False)],
            cost=round(rng.uniform(150, 300), 2), health=1.0,
        )

    def _reset_dev_shutdown(self, rng: random.Random) -> Observation:
        return Observation(
            instances=[
                Instance(id=_hex_id("i"), instance_type="g4dn.xlarge", cpu_utilization=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id=_hex_id("i"), instance_type="p4d.24xlarge", cpu_utilization=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id=_hex_id("i"), instance_type="c6i.4xlarge", cpu_utilization=round(rng.uniform(55, 90), 1), status="running", tag="prod"),
            ],
            volumes=[Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use", age=rng.randint(5, 30))],
            databases=[Database(id=_hex_id("rds"), publicly_accessible=False)],
            cost=round(rng.uniform(400, 800), 2), health=1.0,
        )

    def _reset_auditor(self, rng: random.Random) -> Observation:
        return Observation(
            instances=[
                Instance(id=_hex_id("i"), instance_type="g4dn.xlarge", cpu_utilization=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id=_hex_id("i"), instance_type="m5.large", cpu_utilization=round(rng.uniform(60, 85), 1), status="running", tag="prod"),
            ],
            volumes=[
                Volume(id=_hex_id("vol"), volume_type="io2", state="available", age=rng.randint(35, 90)),
                Volume(id=_hex_id("vol"), volume_type="gp3", state="in-use", age=rng.randint(5, 20)),
            ],
            databases=[
                Database(id=_hex_id("rds"), publicly_accessible=True),
                Database(id=_hex_id("rds"), publicly_accessible=rng.choice([True, False])),
            ],
            cost=round(rng.uniform(500, 900), 2), health=1.0,
        )

    def reset(self, task: str = "auditor") -> dict:
        self.steps = 0
        self._task = task
        rng = random.Random()

        if task == "zombie_reaper":
            self._state = self._reset_zombie_reaper(rng)
        elif task == "dev_shutdown":
            self._state = self._reset_dev_shutdown(rng)
        else:
            self._state = self._reset_auditor(rng)

        self._state.alerts = self._generate_alerts()
        self._max_counts = {
            "zombies": max(1, sum(1 for v in self._state.volumes if v.state == "available" and v.age > 30)),
            "devs": max(1, sum(1 for i in self._state.instances if i.tag == "dev" and i.cpu_utilization < 5 and i.status == "running")),
            "insecure": max(1, sum(1 for db in self._state.databases if db.publicly_accessible)),
        }
        return self._state.model_dump()

    def state(self) -> dict:
        if self._state is None: self.reset()
        return self._state.model_dump()

    def step(self, action: dict) -> tuple[dict, float, bool, dict]:
        if self._state is None: self.reset()

        action_obj = Action(**action)
        self.steps += 1

        step_reward = -0.01
        terminal_bonus = 0.0
        done = False
        info: dict = {"action_success": False, "reason": ""}

        phi_before = self._potential(self._state)

        if action_obj.action_type == "delete_volume":
            found = False
            for v in self._state.volumes:
                if v.id == action_obj.target_id:
                    found = True
                    if v.state == "available" and v.age > 30:
                        self._state.volumes.remove(v)
                        savings = 50.0 if v.volume_type == "io2" else 10.0
                        self._state.cost = max(0.0, self._state.cost - savings)
                        step_reward += 0.15
                        info = {"action_success": True, "reason": f"deleted unattached {v.volume_type} volume"}
                    elif v.state == "in-use":
                        step_reward -= 0.30
                        info["reason"] = "attempted to delete an attached volume (in-use)"
                    else:
                        step_reward -= 0.10
                        info["reason"] = "volume age < 30 days, not considered a zombie yet"
                    break
            if not found:
                step_reward -= 0.30
                info["reason"] = "EBS volume not found"

        elif action_obj.action_type == "stop_instance":
            found = False
            for inst in self._state.instances:
                if inst.id == action_obj.target_id:
                    found = True
                    if inst.tag == "prod":
                        step_reward -= 0.50
                        info["reason"] = "CRITICAL: cannot stop production EC2 instance"
                    elif inst.tag == "dev" and inst.cpu_utilization < 5 and inst.status == "running":
                        inst.status = "stopped"
                        savings = 30.0 if "g4dn" in inst.instance_type or "p4d" in inst.instance_type else 5.0
                        self._state.cost = max(0.0, self._state.cost - savings)
                        step_reward += 0.35
                        info = {"action_success": True, "reason": f"stopped idle {inst.instance_type} dev instance"}
                    else:
                        step_reward -= 0.10
                        info["reason"] = "EC2 instance not eligible for shutdown"
                    break
            if not found:
                step_reward -= 0.30
                info["reason"] = "EC2 instance not found"

        elif action_obj.action_type == "secure_database":
            found = False
            for db in self._state.databases:
                if db.id == action_obj.target_id:
                    found = True
                    if db.publicly_accessible:
                        db.publicly_accessible = False
                        step_reward += 0.50
                        info = {"action_success": True, "reason": "secured public RDS database"}
                    else:
                        step_reward -= 0.10
                        info["reason"] = "RDS database already private"
                    break
            if not found:
                step_reward -= 0.30
                info["reason"] = "RDS database not found"

        elif action_obj.action_type == "noop":
            step_reward -= 0.05
            info["reason"] = "no operation performed"

        phi_after = self._potential(self._state)
        step_reward += 0.99 * phi_after - phi_before
        step_reward = _clamp01_open(max(0.0, min(1.0, step_reward)))

        if self._is_done():
            done = True
            efficiency = (MAX_STEPS - self.steps) / MAX_STEPS
            terminal_bonus = _clamp01_open(round(0.20 + 0.25 * efficiency, 4))
            info["reason"] = "all AWS infrastructure issues resolved"
        elif self.steps >= MAX_STEPS:
            done = True
            info["reason"] = "max steps reached"

        self._update_health()
        self._state.alerts = self._generate_alerts()

        total = max(0.05, min(0.95, round(step_reward + terminal_bonus, 4)))
        return self._state.model_dump(), total, done, info