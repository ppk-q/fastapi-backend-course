from classes import TaskStatus
from pydantic import BaseModel, Field


class TaskScheme(BaseModel):
    id: int
    title: str = Field(..., description="Название задачи")
    status: TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(..., description="Название задачи")
    status: TaskStatus


class TaskUpdate(BaseModel):
    title: str | None = Field(None, description="Новое название")
    status: TaskStatus | None
    notes: str | None
