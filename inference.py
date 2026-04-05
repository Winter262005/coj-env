import os
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
MODEL_NAME = os.getenv("MODEL_NAME", "dummy-model")

MAX_STEPS = 10


def log_start():
    print("[START]")
    print(f"Model: {MODEL_NAME}")


def log_step(step, action, reward, done):
    print(f"[STEP {step}]")
    print(f"Action: {action}")
    print(f"Reward: {reward}")
    print(f"Done: {done}")


def log_end(score):
    print("[END]")
    print(f"Final Score: {score}")


def main():
    log_start()

    # reset env
    res = requests.post(f"{API_BASE_URL}/reset")
    state = res.json()

    total_reward = 0

    for step in range(1, MAX_STEPS + 1):

        # --- SIMPLE RULE-BASED AGENT ---

        action = {"action_type": "noop"}

        # 1. delete zombie volumes
        for v in state["volumes"]:
            if not v["attached"] and v["age"] > 30:
                action = {"action_type": "delete_volume", "target_id": v["id"]}
                break

        # 2. stop dev instances
        if action["action_type"] == "noop":
            for i in state["instances"]:
                if i["tag"] == "dev" and i["cpu"] < 5 and i["status"] == "running":
                    action = {"action_type": "stop_instance", "target_id": i["id"]}
                    break

        # 3. secure database
        if action["action_type"] == "noop":
            for db in state.get("databases", []):
                if db["public"]:
                    action = {"action_type": "secure_database", "target_id": db["id"]}
                    break

        # step env
        res = requests.post(f"{API_BASE_URL}/step", json=action)
        data = res.json()

        state = data["observation"]
        reward = data["reward"]
        done = data["done"]

        total_reward += reward

        log_step(step, action, reward, done)

        if done:
            break

    score = max(0.0, min(1.0, total_reward))

    log_end(score)


if __name__ == "__main__":
    main()