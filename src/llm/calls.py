"""How a model is called and its answer read, the same for every agent and provider."""

import json
import logging
import re
import time

import openai
from langchain_openai import ChatOpenAI

from .factory import tokens_per_minute_limit
from src.log import get_logger

log = get_logger("llm")

MAX_LLM_RETRIES = 2  # Retries after a temporary error.
MAX_RETRY_WAIT_SECONDS = 65  # A per-minute limit clears within a minute; a longer wait means a daily limit: give up.
DEFAULT_RETRY_WAIT_SECONDS = 5  # Wait used when the provider suggests none.
# Errors worth retrying; permanent ones (bad key, bad request) would fail again.
_TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,
)
# The wait suggested in the provider's error message, e.g. "try again in 1m2.5s".
_RETRY_AFTER = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def _retry_wait_seconds(error: Exception) -> float:
    """Seconds to wait before retrying, from the provider's message."""
    match = _RETRY_AFTER.search(str(error))
    if not match:
        return DEFAULT_RETRY_WAIT_SECONDS
    minutes, seconds = match.groups()
    return int(minutes or 0) * 60 + float(seconds) + 1


def call_with_retry(fn, *args, **kwargs):
    """Runs a model call, retrying after temporary errors; blocking, so call it in a thread."""
    for attempt in range(MAX_LLM_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except _TRANSIENT_ERRORS as e:
            wait = _retry_wait_seconds(e)
            # Give up after the last attempt, or when the wait asked for is too long.
            if attempt == MAX_LLM_RETRIES or wait > MAX_RETRY_WAIT_SECONDS:
                raise
            log.warning("temporary error (%s), retry %s/%s in %.1fs", type(e).__name__, attempt + 1, MAX_LLM_RETRIES, wait)
            time.sleep(wait)


_TOKEN_BUDGET_MARGIN = 300  # The prompt size is only estimated.
_MIN_RESPONSE_TOKENS = 1000  # Below this a JSON answer risks being cut.
_CHARS_PER_TOKEN = 3.0  # Measured about 3.4 on real prompts; 3.0 to stay safe.


def max_tokens_for(prompt: str, llm: ChatOpenAI) -> int | None:
    """Answer size that keeps prompt + answer within the per-minute limit, or None if there is no limit."""
    limit = tokens_per_minute_limit(llm)
    if limit is None:
        return None
    estimated_prompt_tokens = int(len(prompt) / _CHARS_PER_TOKEN)
    budget = limit - estimated_prompt_tokens - _TOKEN_BUDGET_MARGIN
    # The provider rejects a request whose prompt plus reserved answer exceed the limit.
    return max(_MIN_RESPONSE_TOKENS, min(llm.max_tokens or 4096, budget))


def stream_text(prompt: str, llm: ChatOpenAI) -> str:
    """The model's full answer; in DEBUG it is shown in the terminal while it arrives."""
    max_tokens = max_tokens_for(prompt, llm)
    client = llm.bind(max_tokens=max_tokens) if max_tokens else llm

    def _stream():
        """One attempt."""
        # Rebuilt at every attempt: an error can arrive in the middle of the stream.
        full_response = ""
        show = log.isEnabledFor(logging.DEBUG)
        for chunk in client.stream(prompt):
            content = chunk.content
            if show:
                print(content, end="", flush=True)
            full_response += content
        if show:
            print("\n")
        return full_response

    return call_with_retry(_stream)


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)  # Reasoning block some models write before the answer.
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)  # The outermost JSON object in a text.


def extract_json(text: str) -> dict:
    """The JSON object in a model's answer; raises JSONDecodeError if there is none."""
    clean = _THINK_BLOCK.sub("", text or "")
    clean = clean.replace("```json", "").replace("```", "").strip()
    match = _JSON_OBJECT.search(clean)
    data = json.loads(match.group(0) if match else clean)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("la risposta non e' un oggetto JSON", clean, 0)
    return data
