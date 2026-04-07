from pydantic import BaseModel
from typing import List, Optional

class Instance(BaseModel):
    id: str
    cpu: float
    status: str  # "running" or "stopped"
    tag: str     # "dev" or "prod"

class Volume(BaseModel):
    id: str
    attached: bool
    age: int  # in days

class Database(BaseModel):
    id: str
    public: bool  # True = security risk

class Observation(BaseModel):
    instances: List[Instance]
    volumes: List[Volume]
    databases: List[Database]  
    cost: float
    health: float
    alerts: List[str] = []

class Action(BaseModel):
    action_type: str
    target_id: Optional[str] = None

obs = Observation(  
    instances=[],
    volumes=[],
    databases=[],
    cost=100.0,
    health=1.0
)
