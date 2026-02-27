"""
Async wrapper around OpenRouter (OpenAI-compatible) for LLM calls.
"""

import openai
import asyncio
import logging

from backend.config import OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)


async def call_llm(
    prompt: str,
    model: str | None = None,
    temperature: float = 0,
    max_retries: int = 5,
) -> str:
    """Send a single-turn prompt and return the assistant's text."""
    model = model or LLM_MODEL
    api_key = OPENAI_API_KEY
    base_url = OPENAI_BASE_URL

    for attempt in range(max_retries):
        try:
            async with openai.AsyncOpenAI(api_key=api_key, base_url=base_url) as client:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("LLM call attempt %d failed: %s", attempt + 1, e)
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
            else:
                raise
    return ""  # unreachable, but keeps type checkers happy
