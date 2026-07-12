"""Locust load test for the NexusAI critical path.

Exercises register -> login -> create workspace -> create conversation ->
chat, then repeatedly posts messages (the hot path) under load. Run against a
live stack, e.g.::

    locust -f load/locustfile.py --host http://localhost:8000 \
        --users 50 --spawn-rate 5

SLO targets (validate in the Locust UI / CSV output):
  * p95 chat latency  < 1500 ms
  * error rate        < 1%
"""

import uuid

from locust import HttpUser, between, task

_API = "/api/v1"
_PASSWORD = "s3cret-password"  # noqa: S105 - synthetic load-test credential


class NexusUser(HttpUser):
    """A simulated tenant user driving the auth + chat critical path."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Register, authenticate and provision a workspace + conversation."""
        email = f"load-{uuid.uuid4().hex}@example.com"
        self.client.post(
            f"{_API}/auth/register",
            json={"email": email, "password": _PASSWORD},
            name="POST /auth/register",
        )
        login = self.client.post(
            f"{_API}/auth/login",
            json={"email": email, "password": _PASSWORD},
            name="POST /auth/login",
        )
        token = login.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}

        workspace = self.client.post(
            f"{_API}/workspaces",
            json={"name": "load-test"},
            headers=self.headers,
            name="POST /workspaces",
        )
        self.workspace_id = workspace.json()["id"]

        conversation = self.client.post(
            f"{_API}/workspaces/{self.workspace_id}/conversations",
            json={"title": "load-test"},
            headers=self.headers,
            name="POST /conversations",
        )
        self.conversation_id = conversation.json()["id"]

    @task(5)
    def chat(self) -> None:
        """The hot path: submit a grounded chat turn."""
        self.client.post(
            f"{_API}/workspaces/{self.workspace_id}/conversations/{self.conversation_id}/messages",
            json={"message": "What does the knowledge base say about this?"},
            headers=self.headers,
            name="POST /messages (chat)",
        )

    @task(1)
    def list_messages(self) -> None:
        """A lighter read to mix in with writes."""
        self.client.get(
            f"{_API}/workspaces/{self.workspace_id}/conversations/{self.conversation_id}/messages",
            headers=self.headers,
            name="GET /messages",
        )
