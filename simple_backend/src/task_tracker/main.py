from fastapi import FastAPI

from classes import Task, RemoteTaskStore, TaskService
from schemas import TaskScheme, TaskCreate, TaskUpdate
from settings import get_settings

app = FastAPI()

# tracker = FileTaskStore('data/tasks.json')
settings = get_settings()
store = RemoteTaskStore(settings)
service = TaskService(store, settings)
tracker = store


def task_out(task: Task) -> TaskScheme:
    return TaskScheme(
        id=task.id, title=task.title, status=task.status, notes=task.notes
    )


@app.get("/tasks", response_model=list[TaskScheme])
def get_tasks():
    tasks = tracker.get_all()
    return [task_out(task) for task in tasks]


@app.post("/tasks", response_model=TaskScheme)
def create_task(payload: TaskCreate):
    task = service.create_task_and_enrich(payload.title, payload.status)
    return task_out(task)


@app.put("/tasks/{task_id}", response_model=TaskScheme)
def update_task(task_id: int, payload: TaskUpdate):
    task = tracker.update_task(
        task_id,
        title=payload.title,
        status=payload.status,
        notes=payload.notes,
    )
    return task_out(task)


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    tracker.delete_task(task_id)
    return
