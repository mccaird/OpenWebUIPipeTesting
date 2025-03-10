from typing import Optional, Callable, Awaitable
from pydantic import BaseModel, Field
import os
import time
import requests


class Pipe:
    class Valves(BaseModel):
        django_api_url: str = Field(default="") 
        django_auth_token: str = Field(default="") 
        #what the user prompt comes in as to the webhook (custom to account for additional attributes outputting, like files)
        input_field: str = Field(default="chatInput") 
        #Name of property that containes the response from the LLM (json response)
        response_field: str = Field(default="output") 
        emit_interval: float = Field(
            default=2.0, description="Interval in seconds between status emissions"
        )
        enable_status_indicator: bool = Field(
            default=True, description="Enable or disable status indicator emissions"
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "django_pipe"
        self.name = "Django Pipe"
        self.valves = self.Valves()
        self.last_emit_time = 0
    
    async def emit_status(
        # Emmits status messages to the output in Open WebUI to see updates as it generates a response
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
        # primary function
        
        self,
        # body is the list of messages in the conversation, which gets added to with a response
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
            #extracting last user message and making a HTTP post request
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
                    "user_id": __user__['id'], #makeshift chat ID, since no way to extract it
                    "session_context": messages[0]['content'][:100],
                    self.valves.input_field: question #self.valves.input_field is user input for last message
                }
                
                response = requests.post(
                    # Get response from the LLM
                    self.valves.django_api_url, 
                    json=payload, 
                    headers=headers
                )
                
                if response.status_code == 200:
                    #extract the output from the LLM based on response field valve
                    django_response = response.json()[self.valves.response_field]
                else:
                    raise Exception(f"Django API Error: {response.status_code} - {response.text}")
                
                #appending extracted output to conversation
                body["messages"].append({"role": "assistant", "content": django_response})
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