import json
import os
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any

import requests
from settings import Settings, get_settings


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class BaseHTTPClient(ABC):
    """Базовый класс для работы с клиентами."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    @abstractmethod
    def auth_headers(self) -> dict[str, str]:
        pass

    def _url(self, path: str = "") -> str:
        if not path:
            return self.base_url
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str = "",
        *,
        headers=None,
        params=None,
        json=None,
    ):
        url = self._url(path)
        merged_headers = {**self.auth_headers(), **(headers or {})}
        try:
            resp = requests.request(
                method=method.upper(),
                url=url,
                headers=merged_headers,
                params=params,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"HTTP запрос не удался: {e}") from e
        return resp

    def json(
        self,
        resp: requests.Response,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        status = resp.status_code
        if status not in expected:
            snippet = (resp.text or "")[:200]
            ct = resp.headers.get("Content-Type", "")
            raise RuntimeError(
                f"Неожиданный статус {status} (expected {expected}); "
                f"content-type={ct}; body={snippet}"
            )
        try:
            return resp.json()
        except ValueError as e:
            snippet = (resp.text or "")[:200]
            raise RuntimeError(f"Не удалось спарсить JSON: {e}") from e


class JsonBinClient(BaseHTTPClient):
    """Класс для работы с JSON."""

    def __init__(
        self,
        base_url: str,
        bin_id: str,
        master_key: str,
        timeout: float = 10.0,
    ):
        super().__init__(base_url=base_url, timeout=timeout)
        self.bin_id = bin_id
        self._master_key = master_key

    def auth_headers(self) -> dict[str, str]:
        return {
            "X-Master-Key": self._master_key,
            "Content-Type": "application/json",
        }

    def fetch_payload(self) -> dict[str, Any]:
        path = f"b/{self.bin_id}/latest"
        extra = {"X-Bin-Meta": "false"}
        resp = self.request("GET", path=path, headers=extra)
        data = self.json(resp, expected=(200,))
        tasks = data.get("tasks", [])
        if not isinstance(tasks, list):
            raise RuntimeError("Неправильный тип данных!")
        return data

    def push_payload(self, payload: dict[str, Any]) -> None:
        path = f"b/{self.bin_id}"
        resp = self.request("PUT", path=path, json=payload)
        self.json(resp, expected=(200, 201))
        return None


class CloudflareAIClient(BaseHTTPClient):
    """Класс для работы с LLM."""

    def __init__(self, base_url: str, api_token: str, timeout: float = 10):
        super().__init__(base_url=base_url, timeout=timeout)
        self._api_token = api_token

    def auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    def generate_plan(self, prompt: str) -> str:
        resp = self.request("POST", path="", json={"prompt": prompt})
        data = self.json(resp, expected=(200,))
        result = data.get("result", {})
        if isinstance(result, dict) and "response" in result:
            return str(result["response"]).strip()


class Task:
    """Класс для работы с таской."""

    def __init__(
        self,
        id: int,
        title: str,
        status: TaskStatus,
        notes: str | None = None,
    ) -> None:
        self.id = id
        self.title = title.strip()
        self.status = status
        self.notes = notes

    def rename_title(self, new_title: str) -> None:
        if not new_title.strip() or len(new_title.strip()) > 50:
            raise ValueError(
                "Поле название не может быть пустым или превышать 50 символов"
            )
        else:
            self.title = new_title.strip()

    def change_status(self, new_status: TaskStatus) -> None:
        if not isinstance(new_status, TaskStatus):
            raise ValueError("Такого статуса не существует!")
        self.status = new_status


class TaskStore:
    """Класс для работы с тасками in-memory."""

    def __init__(self):
        self.tasks: dict[int, Task] = {}
        self.next_id = 1

    def get_all(self):
        return list(self.tasks.values())

    def create_task(self, title: str, status: TaskStatus):
        new_id = self.next_id
        self.next_id += 1
        task = Task(new_id, title, status)
        self.tasks[new_id] = task
        return task

    def update_task(
        self,
        id: int,
        title: str | None,
        status: TaskStatus | None,
    ):
        if id not in self.tasks:
            raise ValueError("ID не найден!")
        task = self.tasks[id]
        if title:
            task.rename_title(title)
        if status:
            task.change_status(status)
        return task

    def delete_task(self, id: int) -> None:
        if id not in self.tasks:
            raise ValueError("ID не найден!")
        del self.tasks[id]


class FileTaskStore:
    """Класс для работы с тасками в файле."""

    def __init__(self, path: Path | str = "data/tasks.json"):
        self.path = Path(path)

    def get_all(self) -> list[Task]:
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        tasks = data.get("tasks", [])
        result = []
        for item in tasks:
            tid = int(item["id"])
            title = item["title"]
            status = TaskStatus(item["status"])
            task = Task(tid, title, status)
            result.append(task)
        result = sorted(result, key=lambda t: t.id)
        return result

    def dump_all(self, tasks: list[Task]) -> None:
        items = [
            {"id": t.id, "title": t.title, "status": t.status.value}
            for t in tasks
        ]
        payload = {"schema_version": 1, "tasks": items}
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
        os.replace(tmp_path, self.path)

    def create_task(self, title, status):
        tasks = self.get_all()
        new_id = 1 if not tasks else max(t.id for t in tasks) + 1
        new_task = Task(new_id, title, status)
        tasks.append(new_task)
        self.dump_all(tasks)
        return new_task

    def update_task(
        self,
        id: int,
        title: str | None = None,
        status: TaskStatus | None = None,
    ) -> Task:
        tasks = self.get_all()
        task = None
        for t in tasks:
            if t.id == id:
                task = t
                break
        if task is None:
            raise ValueError("ID не найден!")
        if title is not None:
            task.rename_title(title)
        if status is not None:
            task.change_status(status)
        self.dump_all(tasks)
        return task

    def delete_task(self, id: int) -> None:
        tasks = self.get_all()
        for index, task in enumerate(tasks):
            if task.id == id:
                tasks.pop(index)
        self.dump_all(tasks)
        return


class RemoteTaskStore:
    """Класс для работы с внешним хранилищем."""

    def __init__(self, jsonbin: JsonBinClient):
        self.jsonbin = jsonbin

    def get_all(self) -> list[Task]:
        payload = self.jsonbin.fetch_payload()
        tasks_raw = payload.get("tasks", [])
        result = []
        for item in tasks_raw:
            tid = int(item["id"])
            title = item["title"]
            status = TaskStatus(item["status"])
            notes = item.get("notes")
            task = Task(tid, title, status, notes)
            result.append(task)
        return result

    def create_task(self, title: str, status: TaskStatus):
        payload = self.jsonbin.fetch_payload()
        tasks_raw = payload["tasks"]
        if len(tasks_raw) == 0:
            new_id = 1
        else:
            new_id = max(int(t["id"]) for t in tasks_raw) + 1
        task = Task(new_id, title, status)
        tasks_raw.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
            }
        )
        self.jsonbin.push_payload(payload)
        return task

    def update_task(
        self,
        id: int,
        title: str | None = None,
        status: TaskStatus | None = None,
        notes: str | None = None,
    ):
        payload = self.jsonbin.fetch_payload()
        tasks_raw = payload["tasks"]
        task = None
        for t in tasks_raw:
            if int(t["id"]) == id:
                task = t
                break
        if task is None:
            raise ValueError("ID не найден!")
        obj = Task(
            id=int(task["id"]),
            title=task["title"],
            status=TaskStatus(task["status"]),
            notes=task.get("notes"),
        )
        if title is not None:
            obj.rename_title(title)
        if status is not None:
            obj.change_status(status)
        if notes is not None:
            obj.notes = notes
            task["notes"] = obj.notes
        task["title"] = obj.title
        task["status"] = obj.status.value
        self.jsonbin.push_payload(payload)
        return obj

    def delete_task(self, id: int):
        payload = self.jsonbin.fetch_payload()
        tasks_raw = payload["tasks"]
        for index, task in enumerate(tasks_raw):
            if int(task["id"]) == id:
                tasks_raw.pop(index)
                break
        else:
            raise ValueError("ID не найден!")
        self.jsonbin.push_payload(payload)
        return None


class TaskService:
    """Класс для работы с LLM."""

    def __init__(
        self,
        store: RemoteTaskStore,
        ai: CloudflareAIClient,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.store = store
        self.ai = ai

    def _build_prompt(self, title: str):
        return f"Ты — сеньор-наставник по продуктивности. Задача: '{title}'."

    def create_task_and_enrich(self, title: str, status: TaskStatus):
        task = self.store.create_task(title, status)
        try:
            plan = self.ai.generate_plan(self._build_prompt(title))
            if plan:
                self.store.update_task(id=task.id, notes=plan)
                task.notes = plan
        except Exception as e:
            print(f"Попытка подключения провалилась: {e}")
        return task


# f1 = FileTaskStore('data/tasks.json')
# tasks = f1.get_all()
# payload = f1.dump_all(tasks)
# f1.update_task(2, title='jobik', status=TaskStatus.DONE)
# f1.update_task(2, title='ABOBA')
# f1.update_task(2, status=TaskStatus.IN_PROGRESS)
# f1.delete_task(1)
# s1 = RemoteTaskStore()
# print(s1.endpoint_latest())
# print(s1.endpoint_bin())
# print(s1._headers_for_read())
# print(s1._headers_for_write())
# p = s1.fetch_payload()
# print(p.keys(), len(p.get('tasks', [])))
# p = s1.push_payload(p)
# s1.fetch_payload()
# s1.create_task(title='Leetcode', status=TaskStatus.IN_PROGRESS)
# s1.update_task(2, status=TaskStatus.DONE)
# s1.delete_task(2)
# s1.get_all()
# s2 = TaskService(RemoteTaskStore)
# print(s2._cf_generate_plan('Что это такое?*!'))
# print(s2._cf_headers())
