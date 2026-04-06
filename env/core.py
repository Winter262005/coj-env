from env.models import Observation, Instance, Volume, Database, Action

class CloudEnv:
    def __init__(self):
        self.state = None

    def update_health(self):
        health = 1.0

        # Security issue → public DB
        if any(db.public for db in self.state.databases):
            health -= 0.3

        # Critical issue → stopping prod instance
        if any(i.tag == "prod" and i.status == "stopped" for i in self.state.instances):
            health -= 0.5

        self.state.health = max(0.0, health)
    
    def reset(self):
        self.state = Observation(
            instances=[
                Instance(id="i-1", cpu=2.0, status="running", tag="dev"),
                Instance(id="i-2", cpu=3.0, status="running", tag="dev"),
                Instance(id="i-3", cpu=70.0, status="running", tag="prod"),
            ],
            volumes=[
                Volume(id="v-1", attached=False, age=45),  # zombie
                Volume(id="v-2", attached=True, age=10),   # active
            ],
            databases=[
                Database(id="db-1", public=True),  # insecure
            ],
            cost=100.0,
            health=1.0
        )
        return self.state.model_dump()

    def get_state(self):
        return self.state.model_dump()

    def step(self, action: dict):
        action = Action(**action)

        reward = 0.0
        done = False

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
                        reward += 0.1
                    else:
                        reward -= 0.2
                    break

            if not found:
                reward -= 0.3  # invalid target

        elif action.action_type == "stop_instance":
            target_id = action.target_id
            found = False

            for inst in self.state.instances:
                if inst.id == target_id:
                    found = True
                    if inst.tag == "dev" and inst.cpu < 5 and inst.status == "running":
                        inst.status = "stopped"
                        self.state.cost = max(0.0, self.state.cost - 10)
                        reward += 0.2
                    elif inst.tag == "prod":
                        reward -= 0.5
                    else:
                        reward -= 0.1
                    break

            if not found:
                reward -= 0.3  # invalid target

        elif action.action_type == "secure_database":
            target_id = action.target_id
            found = False

            for db in self.state.databases:
                if db.id == target_id:
                    found = True
                    if db.public:
                        db.public = False
                        reward += 0.3
                    else:
                        reward -= 0.1
                    break

            if not found:
                reward -= 0.3  # invalid target

        # Handle noop
        elif action.action_type == "noop":
            reward -= 0.01

        # Done condition → no more zombie volumes left
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

        if len(dev_targets) == 0 and len(zombies_left) == 0 and len(insecure_dbs) == 0:
            done = True

        self.update_health()
        return self.state.model_dump(), reward, done, {}
    
if __name__ == "__main__":
    env = CloudEnv()
    state = env.reset()

    print("Initial:", state)

    action = {"action_type": "stop_instance", "target_id": "i-3"}
    state, reward, done, _ = env.step(action)

    print("After Action:", state)
    print("Reward:", reward)
    print("Done:", done)
    print(state["health"])