import models.openai_adapter as openai_adapter


class FakeTextResponse:
    output_text = "Generated adapter answer"


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def create(self, **kwargs):
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, api_key=None, timeout=None):
        self.responses = FakeResponses(FakeTextResponse())


def test_generate_response_normalizes_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_adapter, "OpenAI", FakeClient)

    result = openai_adapter.generate_response("Hello")

    assert result["provider"] == "openai"
    assert result["success"] is True
    assert result["llm_success"] is True
    assert result["response"] == "Generated adapter answer"
    assert result["content"] == "Generated adapter answer"
    assert result["llm_error"] is None


def test_generate_response_normalizes_failure(monkeypatch):
    class FailingClient:
        def __init__(self, api_key=None, timeout=None):
            self.responses = FakeResponses(error=RuntimeError("boom"))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_adapter, "OpenAI", FailingClient)

    result = openai_adapter.generate_response("Hello")

    assert result["provider"] == "openai"
    assert result["success"] is False
    assert result["llm_success"] is False
    assert result["response"] == ""
    assert result["content"] == ""
    assert result["llm_error"] == "RuntimeError"
