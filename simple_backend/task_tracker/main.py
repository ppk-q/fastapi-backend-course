from classes import (
    CloudflareAIClient,
    JsonBinClient,
    RemoteTaskStore,
    Task,
    TaskService,
)
from fastapi import FastAPI
from schemas import TaskCreate, TaskScheme, TaskUpdate
from settings import get_settings

app = FastAPI()

# tracker = FileTaskStore('data/tasks.json')

settings = get_settings()
cf = CloudflareAIClient(
    base_url=str(settings.CF_LINK),
    api_token=settings.API_TOKEN,
    timeout=10.0,
)
jb = JsonBinClient(
    base_url=str(settings.JSONBIN_BASE_URL),
    bin_id=settings.JSONBIN_BIN_ID,
    master_key=settings.JSONBIN_MASTER_KEY.get_secret_value(),
    timeout=10.0,
)
store = RemoteTaskStore(jsonbin=jb)
service = TaskService(store, ai=cf, settings=settings)
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
