from types import SimpleNamespace

from pydantic import BaseModel

from app import llm


def test_client_uses_openrouter_endpoint(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = llm._client()
    try:
        assert str(client.base_url) == "https://openrouter.ai/api/v1/"
    finally:
        client.close()


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = False
        self.chat = SimpleNamespace(completions=self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        return False

    def create(self, **request):
        assert not self.closed
        self.requests.append(request)
        return next(self.responses)


def test_run_tool_agent_calls_tools_and_returns_final_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "8192")

    class ToolCall:
        id = "call-1"
        function = SimpleNamespace(name="increment", arguments='{"value": 4}')

        def model_dump(self, exclude_none=True):
            return {"id": self.id, "type": "function", "function": {
                "name": self.function.name, "arguments": self.function.arguments,
            }}

    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[ToolCall()]))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Done", tool_calls=None))]),
    ]
    client = FakeClient(responses)
    monkeypatch.setattr(llm, "_client", lambda: client)
    results = []

    def increment(value: int) -> dict:
        results.append(value)
        return {"value": value + 1}

    assert llm.run_tool_agent("system", "prompt", [increment]) == "Done"
    assert results == [4]
    assert client.requests[0]["max_tokens"] == 8192
    assert client.requests[0]["tools"][0]["function"]["parameters"]["required"] == ["value"]
    assert client.requests[1]["messages"][-1] == {
        "role": "tool", "tool_call_id": "call-1", "content": '{"value": 5}',
    }
    assert client.closed


def test_generate_structured_validates_openrouter_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "8192")

    class Answer(BaseModel):
        message: str

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"message":"ok"}'))]
    )
    client = FakeClient([response])
    monkeypatch.setattr(llm, "_client", lambda: client)

    assert llm.generate_structured("system", "prompt", Answer) == Answer(message="ok")
    assert client.requests[0]["response_format"] == {"type": "json_object"}
    assert client.requests[0]["max_tokens"] == 8192
    assert "message" in client.requests[0]["messages"][0]["content"]
    assert client.closed
