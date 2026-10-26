from typing import Literal
from pydantic import BaseModel,ConfigDict,Field

class ChangeStatusRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    new_status: Literal['confirmed','processing','shipped','delivered']

class CancelRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason: str=Field(default='',max_length=500)
