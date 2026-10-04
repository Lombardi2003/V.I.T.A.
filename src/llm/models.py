"""Catalogue of the available models, grouped by provider. The active ones are chosen in factory.py."""


class Models:
    """Model names; the class a name belongs to tells its provider."""
    class Groq:
        """Groq (cloud). Free tier: 8,000 tokens per minute per model."""
        TEXT_8B = "llama-3.1-8b-instant"  # No longer available on the account; kept as history.
        TEXT_70B = "llama-3.3-70b-versatile"  # No longer available on the account; kept as history.
        TEXT_120B = "openai/gpt-oss-120b"  # Reasoning model.
        TEXT_20B = "openai/gpt-oss-20b"  # Same family as TEXT_120B, smaller.
        TEXT_QWEN_27B = "qwen/qwen3.8-27b"  # Writes a <think> block before the JSON (handled by extract_json).
        # Tried and discarded: it relies on TEXT_120B and shares its token limit.
        TEXT_COMPOUND_MINI = "groq/compound-mini"
        VISION_QWEN = "qwen/qwen3.8-27b"  # The only vision model available on the account.

    class Ollama:
        """Ollama (local): no rate limit; start it with a context of at least 8,192 tokens."""
        TEXT_LLAMA3 = "llama3:latest"
        VISION_MOONDREAM = "moondream"

    class Gemini:
        """Google AI Studio (cloud). Free tier: about 20 requests per day."""
        TEXT_FLASH = "gemini-3.8-flash"  # Reasoning model, also multimodal.
