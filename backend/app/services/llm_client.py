import json
from dataclasses import dataclass
from functools import lru_cache

from groq import Groq

from app.core.config import settings


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class LLMClient:
    """The only file that knows about Groq. To switch providers, change this file."""

    def __init__(self, api_key: str):
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set in backend/.env")
        self._client = Groq(api_key=api_key)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        # Reasoning tokens count toward this limit, so keep it generous
        max_tokens: int = 2500,
        reasoning_effort: str | None = "low",
    ) -> LLMResult:
        model = model or settings.groq_model_main

        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        # gpt-oss models accept low | medium | high. Other models may reject the parameter.
        if reasoning_effort and model.startswith("openai/gpt-oss"):
            kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}

        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Groq request failed: {exc}") from exc

        choice = resp.choices[0]
        text = choice.message.content or ""
        if not text.strip():
            raise LLMError(
                f"Model returned an empty reply (finish_reason={choice.finish_reason}). "
                "It may have used the whole token budget on reasoning; try a higher max_tokens."
            )

        usage = resp.usage
        return LLMResult(
            text=text,
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    def chat_json(self, messages: list[dict[str, str]], **kwargs) -> tuple[dict, LLMResult]:
        # Groq's JSON mode requires the word "JSON" to appear in the prompt
        result = self.chat(messages, json_mode=True, **kwargs)
        try:
            return json.loads(result.text), result
        except json.JSONDecodeError as exc:
            raise LLMError("Model did not return valid JSON") from exc


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient(settings.groq_api_key)