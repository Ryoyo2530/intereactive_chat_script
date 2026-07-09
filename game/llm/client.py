import json
import logging
import re
import time
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from game.llm.config import LLMConfig

logger = logging.getLogger(__name__)


def _extra_body(config: LLMConfig) -> dict[str, Any]:
    if config.provider == "doubao":
        return {"thinking": {"type": "disabled"}}
    return {}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()
    return json.loads(text)


def _decode_json_string_partial(raw: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(raw):
        char = raw[i]
        if char == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
            result.append(escapes.get(nxt, nxt))
            i += 2
        else:
            result.append(char)
            i += 1
    return "".join(result)


def extract_reply_from_partial_json(text: str) -> str:
    match = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    if not match:
        return ""
    return _decode_json_string_partial(match.group(1))


def extract_emotion_tag_from_partial_json(text: str) -> str:
    match = re.search(r'"emotion_tag"\s*:\s*"([^"\\]*)"', text)
    if not match:
        return ""
    return match.group(1).strip()


def _client_for(config: LLMConfig) -> OpenAI:
    return OpenAI(api_key=config.api_key, base_url=config.api_base)


def chat_completion(
    messages: list[dict[str, str]],
    config: LLMConfig,
    temperature: float = 0.8,
) -> str:
    extra = _extra_body(config)
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
    }
    if extra:
        kwargs["extra_body"] = extra
    response = _client_for(config).chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def chat_stream(
    messages: list[dict[str, str]],
    config: LLMConfig,
    temperature: float = 0.7,
) -> Iterator[str]:
    extra = _extra_body(config)
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if extra:
        kwargs["extra_body"] = extra
    stream = _client_for(config).chat.completions.create(**kwargs)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def parse_json_response(text: str) -> dict[str, Any]:
    return _extract_json(text)


def _prompts_from_messages(messages: list[dict[str, str]]) -> dict[str, str]:
    return {
        "system": next((m["content"] for m in messages if m["role"] == "system"), ""),
        "user": next((m["content"] for m in messages if m["role"] == "user"), ""),
    }


def chat_json_stream_debug(
    messages: list[dict[str, str]],
    config: LLMConfig,
    fallback: dict[str, Any],
    temperature: float = 0.7,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Stream a JSON completion and capture TTFT, total time, and token usage."""
    start = time.perf_counter()
    ttft_ms: int | None = None
    accumulated = ""
    usage: dict[str, int | None] = {"input_tokens": None, "output_tokens": None}

    extra = _extra_body(config)
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if extra:
        kwargs["extra_body"] = extra

    stream = _client_for(config).chat.completions.create(**kwargs)
    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage["input_tokens"] = chunk.usage.prompt_tokens
            usage["output_tokens"] = chunk.usage.completion_tokens
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            if ttft_ms is None:
                ttft_ms = int((time.perf_counter() - start) * 1000)
            accumulated += delta

    total_ms = int((time.perf_counter() - start) * 1000)
    if ttft_ms is None:
        ttft_ms = total_ms

    try:
        parsed = _extract_json(accumulated)
    except Exception as exc:
        logger.warning("LLM JSON parse failed (stream debug): %s", exc)
        parsed = dict(fallback)

    meta = {
        "prompts": _prompts_from_messages(messages),
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "usage": usage,
        "raw_output": accumulated,
    }
    return parsed, meta


def chat_json(
    messages: list[dict[str, str]],
    config: LLMConfig,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    try:
        raw = chat_completion(messages, config, temperature=0.7)
        return _extract_json(raw)
    except Exception as exc:
        logger.warning("LLM JSON parse failed: %s", exc)
        return dict(fallback)


def test_connection(config: LLMConfig) -> dict[str, str]:
    reply = chat_completion(
        [{"role": "user", "content": "回复 OK 两个字母即可"}],
        config,
        temperature=0,
    )
    preview = (reply or "").strip()[:80]
    return {"ok": True, "preview": preview or "(empty response)"}
