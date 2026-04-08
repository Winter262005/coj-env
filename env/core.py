import random
from env.models import Observation, Instance, Volume, Database, Action

MAX_STEPS = 10


class CloudEnv:
    def _init_(self):
        self._state: Observation | None = None
        self.steps:  int                = 0
        self._task:  str                = "auditor"   # set by reset()
        self._max_counts: dict          = {}
        self._initial_snapshot: dict | None = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _update_health(self) -> None:
        health = 1.0
        if any(db.public for db in self._state.databases):
            health -= 0.3
        if any(i.tag == "prod" and i.status == "stopped" for i in self._state.instances):
            health -= 0.5
        self._state.health = max(0.0, health)

    def _generate_alerts(self) -> list[str]:
        alerts = []
        if any(not v.attached and v.age > 30 for v in self._state.volumes):
            alerts.append("UNUSED_VOLUME")
        if any(db.public for db in self._state.databases):
            alerts.append("PUBLIC_DB")
        if any(i.tag == "dev" and i.cpu < 5 and i.status == "running" for i in self._state.instances):
            alerts.append("IDLE_DEV_INSTANCE")
        return alerts

    def _potential(self, obs: Observation) -> float:
        n_z = self._max_counts.get("zombies",  1)
        n_d = self._max_counts.get("devs",     1)
        n_b = self._max_counts.get("insecure", 1)
        z = sum(1 for v  in obs.volumes    if not v.attached and v.age > 30)     / n_z
        d = sum(1 for i  in obs.instances  if i.tag == "dev" and i.cpu < 5 and i.status == "running") / n_d
        b = sum(1 for db in obs.databases  if db.public)                          / n_b
        return -(0.5 * b + 0.3 * d + 0.2 * z)

    def _is_done(self) -> bool:
        """Task-specific done conditions — each task has a distinct objective."""
        if self._task == "zombie_reaper":
            return not any(not v.attached and v.age > 30 for v in self._state.volumes)

        if self._task == "dev_shutdown":
            return not any(
                i.tag == "dev" and i.cpu < 5 and i.status == "running"
                for i in self._state.instances
            )

        # auditor: all three problems resolved
        return (
            not any(not v.attached and v.age > 30 for v in self._state.volumes)
            and not any(i.tag == "dev" and i.cpu < 5 and i.status == "running" for i in self._state.instances)
            and not any(db.public for db in self._state.databases)
        )

    # ── Task-specific reset states ────────────────────────────────────────────

    def _reset_zombie_reaper(self, rng: random.Random) -> Observation:
        """Easy: only zombie volumes. No public DBs, no idle devs."""
        return Observation(
            instances=[
                Instance(id="i-1", cpu=round(rng.uniform(20, 80), 1), status="running", tag="dev"),
                Instance(id="i-2", cpu=round(rng.uniform(20, 80), 1), status="running", tag="dev"),
                Instance(id="i-3", cpu=round(rng.uniform(55, 90), 1), status="running", tag="prod"),
            ],
            volumes=[
                Volume(id="v-1", attached=False, age=rng.randint(35, 90)),        # zombie
                Volume(id="v-2", attached=False, age=rng.randint(35, 75)),        # zombie
                Volume(id="v-3", attached=True,  age=rng.randint(5,  20)),        # safe
                Volume(id="v-4", attached=False, age=rng.randint(0,  25)),        # young orphan
            ],
            databases=[
                Database(id="db-1", public=False),
                Database(id="db-2", public=False),
            ],
            cost=round(rng.uniform(60, 90), 2),
            health=1.0,
        )

    def _reset_dev_shutdown(self, rng: random.Random) -> Observation:
        """Medium: only idle dev instances. No public DBs, no zombie volumes."""
        return Observation(
            instances=[
                Instance(id="i-1", cpu=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id="i-2", cpu=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id="i-3", cpu=round(rng.uniform(55, 90),   1), status="running", tag="prod"),
                Instance(id="i-4", cpu=round(rng.uniform(60, 85),   1), status="running", tag="prod"),
            ],
            volumes=[
                Volume(id="v-1", attached=True,  age=rng.randint(5,  30)),        # safe
                Volume(id="v-2", attached=False, age=rng.randint(0,  25)),        # young orphan
            ],
            databases=[
                Database(id="db-1", public=False),
                Database(id="db-2", public=False),
            ],
            cost=round(rng.uniform(80, 110), 2),
            health=1.0,
        )

    def _reset_auditor(self, rng: random.Random) -> Observation:
        """Hard: all three problem types active simultaneously."""
        return Observation(
            instances=[
                Instance(id="i-1", cpu=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id="i-2", cpu=round(rng.uniform(0.5, 4.5), 1), status="running", tag="dev"),
                Instance(id="i-3", cpu=round(rng.uniform(55, 90),   1), status="running", tag="prod"),
                Instance(id="i-4", cpu=round(rng.uniform(60, 85),   1), status="running", tag="prod"),
            ],
            volumes=[
                Volume(id="v-1", attached=False, age=rng.randint(35, 90)),        # zombie
                Volume(id="v-2", attached=False, age=rng.randint(35, 75)
                       if rng.random() > 0.4 else rng.randint(0, 25)),            # maybe zombie
                Volume(id="v-3", attached=True,  age=rng.randint(5,  20)),        # safe
            ],
            databases=[
                Database(id="db-1", public=True),
                Database(id="db-2", public=rng.choice([True, False])),
            ],
            cost=round(rng.uniform(90, 120), 2),
            health=1.0,
        )

    # ── OpenEnv API ───────────────────────────────────────────────────────────

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
            "zombies":  max(1, sum(1 for v  in self._state.volumes    if not v.attached and v.age > 30)),
            "devs":     max(1, sum(1 for i  in self._state.instances  if i.tag == "dev" and i.cpu < 5 and i.status == "running")),
            "insecure": max(1, sum(1 for db in self._state.databases  if db.public)),
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
                    if not v.attached and v.age > 30:
                        self._state.volumes.remove(v)
                        self._state.cost = max(0.0, self._state.cost - 5)
                        step_reward += 0.15
                        info = {"action_success": True, "reason": "deleted zombie volume"}
                    elif v.attached:
                        step_reward -= 0.30
                        info["reason"] = "attempted to delete attached volume"
                    else:
                        step_reward -= 0.10
                        info["reason"] = "volume age < 30 days, not a zombie"
                    break
            if not found:
                step_reward -= 0.30
                info["reason"] = "volume not found"

        elif action_obj.action_type == "stop_instance":
            found = False
            for inst in self._state.instances:
                if inst.id == action_obj.target_id:
                    found = True
                    if inst.tag == "prod":
                        step_reward -= 0.50
                        info["reason"] = "cannot stop production instance"
                    elif inst.tag == "dev" and inst.cpu < 5 and inst.status == "running":
                        inst.status = "stopped"
                        self._state.cost = max(0.0, self._state.cost - 10)
                        step_reward += 0.35
                        info = {"action_success": True, "reason": "stopped idle dev instance"}
                    else:
                        step_reward -= 0.10
                        info["reason"] = "instance not eligible"
                    break
            if not found:
                step_reward -= 0.30
                info["reason"] = "instance not found"

        elif action_obj.action_type == "secure_database":
            found = False
            for db in self._state.databases:
                if db.id == action_obj.target_id:
                    found = True
                    if db.public:
                        db.public = False
                        step_reward += 0.50
                        info = {"action_success": True, "reason": "secured public database"}
                    else:
                        step_reward -= 0.10
                        info["reason"] = "database already private"
                    break
            if not found:
                step_reward -= 0.30
                info["reason"] = "database not found"

        elif action_obj.action_type == "noop":
            step_reward -= 0.05
            info["reason"] = "no operation performed"

        phi_after  = self._potential(self._state)
        step_reward += 0.99 * phi_after - phi_before
        step_reward  = max(-1.0, min(1.0, step_reward))

        if self._is_done():
            done = True
            efficiency     = (MAX_STEPS - self.steps) / MAX_STEPS
            terminal_bonus = max(0.0, 1.0 - step_reward) * (0.5 + 0.5 * efficiency)
            info["reason"] = "all issues resolved"
        elif self.steps >= MAX_STEPS:
            done = True
            info["reason"] = "max steps reached"

        self._update_health()
        self._state.alerts = self._generate_alerts()

        return self._state.model_dump(), round(step_reward + terminal_bonus, 4), done, info