from fastapi import FastAPI

from classes import Task, RemoteTaskStore
from schemas import TaskScheme, TaskCreate, TaskUpdate

app = FastAPI()

# tracker = FileTaskStore('data/tasks.json')
tracker = RemoteTaskStore()


def task_out(task: Task) -> TaskScheme:
    return TaskScheme(id=task.id, title=task.title, status=task.status)


@app.get("/tasks", response_model=list[TaskScheme])
def get_tasks():
    tasks = tracker.get_all()
    return [task_out(task) for task in tasks]


@app.post("/tasks", response_model=TaskScheme)
def create_task(payload: TaskCreate):
    task = tracker.create_task(payload.title, payload.status)
    return task_out(task)


@app.put("/tasks/{task_id}", response_model=TaskScheme)
def update_task(task_id: int, payload: TaskUpdate):
    task = tracker.update_task(task_id, title=payload.title, status=payload.status)
    return task_out(task)


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    tracker.delete_task(task_id)
    return
