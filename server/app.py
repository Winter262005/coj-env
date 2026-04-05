from fastapi import FastAPI
from env.core import CloudEnv

app = FastAPI()
env = CloudEnv()


@app.post("/reset")
def reset():
    return env.reset()


@app.post("/step")
def step(action: dict):
    state, reward, done, info = env.step(action)
    return {
        "observation": state,
        "reward": reward,
        "done": done,
        "info": info
    }


@app.get("/state")
def state():
    return env.get_state()


@app.get("/")
def root():
    return {"status": "ok"}

import uvicorn

def main():
    uvicorn.run("server.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()