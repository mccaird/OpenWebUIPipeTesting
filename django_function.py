from typing import Optional, Callable, Awaitable
from pydantic import BaseModel, Field
import os
import time
import requests


class Pipe:
    class Valves(BaseModel):
        django_api_url: str  # Replace n8n_url
        django_auth_token: str  # Replace n8n_bearer_token
        input_field: str = "input"
        response_field: str = "response"
        emit_interval: float = 0.1

    def __init__(self):
        self.type = "pipe"
        self.id = "django_pipe"
        self.name = "Django Pipe"
        self.valves = self.Valves()
        self.last_emit_time = 0
    
    async def emit_status(
        self,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        level: str,
        message: str,
        done: bool,
    ):
        current_time = time.time()
        if (
            __event_emitter__
            and self.valves.enable_status_indicator
            and (
                current_time - self.last_emit_time >= self.valves.emit_interval or done
            )
        ):
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "status": "complete" if done else "in_progress",
                        "level": level,
                        "description": message,
                        "done": done,
                    },
                }
            )
            self.last_emit_time = current_time


    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Awaitable[None]] = None,
        __event_call__: Callable[[dict], Awaitable[dict]] = None,
    ) -> Optional[dict]:
        await self.emit_status(
            __event_emitter__, "info", "Calling Django API...", False
        )

        messages = body.get("messages", [])

        if messages:
            question = messages[-1]["content"]
            if "Prompt: " in question:
                question = question.split("Prompt: ")[-1]
            try:
                # Invoke Django API
                headers = {
                    "Authorization": f"Token {self.valves.django_auth_token}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "user_id": __user__['id'],
                    "session_context": messages[0]['content'][:100],
                    self.valves.input_field: question
                }
                
                response = requests.post(
                    self.valves.django_api_url, 
                    json=payload, 
                    headers=headers
                )
                
                if response.status_code == 200:
                    django_response = response.json()[self.valves.response_field]
                else:
                    raise Exception(f"Django API Error: {response.status_code} - {response.text}")

                body["messages"].append({"role": "assistant", "content": django_response})
                return django_response
            except Exception as e:
                await self.emit_status(
                    __event_emitter__,
                    "error",
                    f"Error during Django API call: {str(e)}",
                    True,
                )
                return {"error": str(e)}
        # If no message is available alert user
        else:
            await self.emit_status(
                __event_emitter__,
                "error",
                "No messages found in the request body",
                True,
            )
            body["messages"].append(
                {
                    "role": "assistant",
                    "content": "No messages found in the request body",
                }
            )

        await self.emit_status(__event_emitter__, "info", "Complete", True)
        return django_response