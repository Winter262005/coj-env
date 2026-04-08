from env.models import Observation, Instance, Volume, Database, Action

class CloudEnv:
    def __init__(self):
        self.state = None
        self.steps = 0          #FIXED : AttributeError

    def update_health(self):
        health = 1.0

        # Security issue → public DB
        if any(db.public for db in self.state.databases):
            health -= 0.3

        # Critical issue → stopping prod instance
        if any(i.tag == "prod" and i.status == "stopped" for i in self.state.instances):
            health -= 0.5

        self.state.health = max(0.0, health)

    def generate_alerts(self):
        alerts = []

        # Zombie volumes
        if any(not v.attached and v.age > 30 for v in self.state.volumes):
            alerts.append("UNUSED_VOLUME")

        # Public DB (security risk)
        if any(db.public for db in self.state.databases):
            alerts.append("PUBLIC_DB")

        # Idle dev instances
        if any(i.tag == "dev" and i.cpu < 5 and i.status == "running" for i in self.state.instances):
            alerts.append("IDLE_DEV_INSTANCE")

        return alerts
    
    # ADDED : Potential Function added for better reward calculations
    def _potential(self, state):
        # Max counts in current scenario
        max_zombies  = 2   # you have 2 volumes
        max_devs     = 2   # 2 dev instances
        max_insec    = 1   # 1 database

        zombies = sum(
            1 for v in state.volumes
            if not v.attached and v.age > 30
        )
        idle_devs = sum(
            1 for i in state.instances
            if i.tag == "dev" and i.cpu < 5 and i.status == "running"
        )
        insecure = sum(
            1 for db in state.databases
            if db.public
        )

        # Normalised fractions in [0,1]
        z = zombies  / max_zombies if max_zombies else 0.0
        d = idle_devs / max_devs   if max_devs   else 0.0
        b = insecure  / max_insec  if max_insec  else 0.0

        # Weighted: security > dev shutdown > volume cleanup
        # Result always in [-1.0, 0.0]
        return -(0.2 * z + 0.3 * d + 0.5 * b)
    
    def reset(self):
        self.steps = 0
        self.state = Observation(
            instances=[
                Instance(id="i-1", cpu=2.0, status="running", tag="dev"),
                Instance(id="i-2", cpu=3.0, status="running", tag="dev"),
                Instance(id="i-3", cpu=70.0, status="running", tag="prod"),
                Instance(id="i-4", cpu=1.0, status="stopped", tag="dev"),
            ],
            volumes=[
                Volume(id="v-1", attached=False, age=45),
                Volume(id="v-2", attached=True, age=10),
                Volume(id="v-3", attached=False, age=5),
            ],
            databases=[
                Database(id="db-1", public=True),
                Database(id="db-2", public=False),
            ],
            cost=100.0,
            health=1.0
        )
        self.state.alerts = self.generate_alerts()
        return self.state.model_dump()

    def get_state(self):
        return self.state.model_dump()

    def step(self, action: dict):
        action = Action(**action)
        self.steps += 1

        reward = 0.0
        reward -= 0.01  # small penalty per step
        done = False
        info = {
            "action_success": False,
            "reason": ""
        }

        # FIXED : a None error when running an agent
        if self.state is None:
            self.reset()

        phi_before = self._potential(self.state)

        # Handle delete_volume
        if action.action_type == "delete_volume":
            target_id = action.target_id
            found = False

            for v in self.state.volumes:
                if v.id == target_id:
                    found = True
                    if not v.attached and v.age > 30:
                        self.state.volumes.remove(v)
                        self.state.cost = max(0.0, self.state.cost - 5)
                        reward += 0.15
                        info["action_success"] = True
                        info["reason"] = "deleted unused volume"
                    else:
                        reward -= 0.2
                        info["reason"] = "attempted to delete active volume"
                    break

            if not found:
                reward -= 0.3  # invalid target
                info["reason"] = "volume not found"

        elif action.action_type == "stop_instance":
            target_id = action.target_id
            found = False

            for inst in self.state.instances:
                if inst.id == target_id:
                    found = True
                    if inst.tag == "dev" and inst.cpu < 5 and inst.status == "running":
                        inst.status = "stopped"
                        self.state.cost = max(0.0, self.state.cost - 10)
                        reward += 0.35
                        info["action_success"] = True
                        info["reason"] = "stopped idle dev instance"
                    elif inst.tag == "prod":
                        reward -= 0.5
                        info["reason"] = "cannot stop production instance"
                    else:
                        reward -= 0.1
                        info["reason"] = "instance not suitable for stopping"
                    break

            if not found:
                reward -= 0.3  # invalid target
                info["reason"] = "instance not found"

        elif action.action_type == "secure_database":
            target_id = action.target_id
            found = False

            for db in self.state.databases:
                if db.id == target_id:
                    found = True
                    if db.public:
                        db.public = False
                        reward += 0.5
                        info["action_success"] = True
                        info["reason"] = "secured public database"
                    else:
                        reward -= 0.1
                        info["reason"] = "database already secure"
                    break

            if not found:
                reward -= 0.3  # invalid target
                info["reason"] = "database not found"

        # Handle noop
        elif action.action_type == "noop":
            reward -= 0.05
            info["reason"] = "no operation performed"

        # ADDED : Shaping Function
        # F(s,s') = gamma * phi_after - phi_before
        gamma = 0.99
        phi_after = self._potential(self.state)
        shaping = gamma * phi_after - phi_before
        reward += shaping

        # Done condition → no more zombie volumes left
        MAX_STEPS = 10
        dev_targets = [
            i for i in self.state.instances
            if i.tag == "dev" and i.cpu < 5 and i.status == "running"
        ]

        zombies_left = [
            v for v in self.state.volumes
            if not v.attached and v.age > 30
        ]

        insecure_dbs = [
            db for db in self.state.databases
            if db.public
        ]

        all_fixed = (
            len(dev_targets) == 0 and
            len(zombies_left) == 0 and
            len(insecure_dbs) == 0
        )

        if all_fixed:
            done = True
            # ADDED : Terminal Bonus = base + efficiency
            efficiency_bonus = 0.5 * (MAX_STEPS - self.steps) / MAX_STEPS
            reward += 1.0 + efficiency_bonus
            info["reason"] = "all issues resolved"

        elif self.steps >= MAX_STEPS:
            done = True
            info["reason"] = "max steps reached"

        self.update_health()
        self.state.alerts = self.generate_alerts()
        reward = max(-1.0, min(1.0, reward))
        return self.state.model_dump(), reward, done, info