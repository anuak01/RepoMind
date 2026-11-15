"""OpenRouter wrapper using the OpenAI-compatible chat completions API."""
import json
import inspect
from typing import Callable, get_args, get_origin

from .config import settings


class LLMUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(settings.openrouter_api_key)


def _client():
    if not available():
        raise LLMUnavailable("OPENROUTER_API_KEY is not set in backend/.env")
    from openai import OpenAI

    return OpenAI(api_key=settings.openrouter_api_key, base_url="https://openrouter.ai/api/v1")


def _json_type(annotation) -> dict:
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if get_origin(annotation) is list:
        args = get_args(annotation)
        return {"type": "array", "items": _json_type(args[0]) if args else {}}
    return {}


def _tool_specs(tools: list[Callable]) -> list[dict]:
    specs = []
    for tool in tools:
        signature = inspect.signature(tool)
        properties = {
            name: _json_type(param.annotation)
            for name, param in signature.parameters.items()
            if name != "self"
        }
        required = [
            name for name, param in signature.parameters.items()
            if name != "self" and param.default is param.empty
        ]
        specs.append({
            "type": "function",
            "function": {
                "name": tool.__name__,
                "description": tool.__doc__ or "",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return specs


def run_tool_agent(system: str, prompt: str, tools: list[Callable], max_calls: int = 8) -> str:
    """Run an OpenRouter function-calling loop and return the final text."""
    by_name = {tool.__name__: tool for tool in tools}
    tool_specs = _tool_specs(tools)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    call_count = 0

    with _client() as client:
        for _ in range(max_calls + 1):
            can_call_tools = call_count < max_calls
            request = {
                "model": settings.openrouter_model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": settings.openrouter_max_tokens,
            }
            if can_call_tools:
                request.update({"tools": tool_specs, "tool_choice": "auto"})
            response = client.chat.completions.create(**request)
            message = response.choices[0].message
            requested_calls = message.tool_calls or []
            if not requested_calls:
                return message.content or ""
            if not can_call_tools:
                raise RuntimeError("OpenRouter returned tool calls after tool use was disabled")

            accepted_calls = requested_calls[:max_calls - call_count]
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [tool_call.model_dump(exclude_none=True) for tool_call in accepted_calls],
            })
            for tool_call in accepted_calls:
                tool = by_name.get(tool_call.function.name)
                if tool is None:
                    raise ValueError(f"OpenRouter requested an unknown tool: {tool_call.function.name}")
                arguments = json.loads(tool_call.function.arguments)
                result = tool(**arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })
            call_count += len(accepted_calls)

    raise RuntimeError("OpenRouter did not return a final response")


def generate_structured(system: str, prompt: str, schema):
    """Return an instance (or list) of the pydantic schema, validated."""
    schema_json = json.dumps(schema.model_json_schema())
    messages = [
        {"role": "system", "content": f"{system}\nReturn valid JSON matching this schema:\n{schema_json}"},
        {"role": "user", "content": prompt},
    ]
    with _client() as client:
        response = client.chat.completions.create(
            model=settings.openrouter_model,
            messages=messages,
            max_tokens=settings.openrouter_max_tokens,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("OpenRouter returned no structured output")
    return schema.model_validate_json(content)
