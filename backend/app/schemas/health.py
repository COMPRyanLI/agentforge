from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class RootResponse(BaseModel):
    app: str
    docs: str
