"""
LLM provider wrapper.

Supports Groq, Google Gemini, OpenAI, and Anthropic via environment variables.
Gracefully degrades to rule-based fallbacks if no API key is set.

Environment variables:
    LLM_PROVIDER         — "groq" | "gemini" | "openai" | "anthropic"  (default: auto-detect)
    GROQ_API_KEY         — Groq key (free tier: ~14,400 req/day — best free option)
    GEMINI_API_KEY       — Google Gemini key (free tier: only ~20 req/day)
    OPENAI_API_KEY       — OpenAI key
    ANTHROPIC_API_KEY    — Anthropic key
    MODEL_NAME           — override model name

Groq is the recommended free provider — far more generous than Gemini's free tier:
  1. Get a key at https://console.groq.com/keys (no credit card)
  2. Set GROQ_API_KEY on Render (Environment → Add variable)
  3. Auto-detected and preferred when set. Uses Llama 3.3 70B via the
     OpenAI-compatible endpoint (no extra dependency needed).
"""

import logging
import os

logger = logging.getLogger(__name__)

_MODEL_OVERRIDE = os.getenv("MODEL_NAME", "")
_GROQ_KEY       = os.getenv("GROQ_API_KEY", "")
_OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")
_ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
_GEMINI_KEY     = os.getenv("GEMINI_API_KEY", "")

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_DEFAULT_MODELS = {
    "groq":      "llama-3.3-70b-versatile",
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini":    "gemini-2.5-flash",
}

# Groq model candidates, tried in order until one responds.
_GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

# Gemini model candidates. gemini-2.5-flash is the only one currently on the free
# tier (2.0-flash = limit 0, 1.5-flash = 404). Its "thinking" mode is disabled in
# _gemini_attempt_new to avoid the empty-output problem. Override with MODEL_NAME.
_GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

_PLACEHOLDERS = {"sk-placeholder", "sk-ant-placeholder", "placeholder", ""}


def _provider() -> str:
    """Auto-detect provider from available keys, or read LLM_PROVIDER env var."""
    explicit = os.getenv("LLM_PROVIDER", "").lower()
    if explicit:
        return explicit
    # Auto-detect — prefer the most generous free tier first
    if _GROQ_KEY and _GROQ_KEY not in _PLACEHOLDERS:
        return "groq"
    if _GEMINI_KEY and _GEMINI_KEY not in _PLACEHOLDERS:
        return "gemini"
    if _OPENAI_KEY and _OPENAI_KEY not in _PLACEHOLDERS:
        return "openai"
    if _ANTHROPIC_KEY and _ANTHROPIC_KEY not in _PLACEHOLDERS:
        return "anthropic"
    return "none"


def _model_name(provider: str) -> str:
    return _MODEL_OVERRIDE or _DEFAULT_MODELS.get(provider, "gpt-4o-mini")


def _is_available() -> bool:
    p = _provider()
    if p == "groq":
        return _GROQ_KEY not in _PLACEHOLDERS
    if p == "openai":
        return _OPENAI_KEY not in _PLACEHOLDERS
    if p == "anthropic":
        return _ANTHROPIC_KEY not in _PLACEHOLDERS
    if p == "gemini":
        return _GEMINI_KEY not in _PLACEHOLDERS
    return False


def _groq_models() -> list[str]:
    """Candidate Groq models to try in order (override pins a single one)."""
    return [_MODEL_OVERRIDE] if _MODEL_OVERRIDE else _GROQ_MODELS


def status() -> dict:
    """Diagnostic snapshot for the /llm/status endpoint — never raises."""
    p = _provider()
    return {
        "provider": p,
        "configured": _is_available(),
        "model": _model_name(p) if p != "none" else None,
    }


def _gemini_models() -> list[str]:
    """Candidate Gemini models to try in order (override pins a single one)."""
    return [_MODEL_OVERRIDE] if _MODEL_OVERRIDE else _GEMINI_MODELS


def complete(system: str, user: str, max_tokens: int = 1024) -> str:
    """
    Send a chat completion and return the response text.
    Returns "" if no API key is configured — callers fall back to rule-based logic.
    """
    p = _provider()
    if p == "none" or not _is_available():
        logger.debug(
            "No LLM API key set — using rule-based fallback. "
            "Add GROQ_API_KEY (free, recommended), GEMINI_API_KEY, OPENAI_API_KEY, "
            "or ANTHROPIC_API_KEY to Render env vars."
        )
        return ""

    logger.debug("LLM call via provider=%s model=%s", p, _model_name(p))

    if p == "groq":
        return _call_groq(system, user, max_tokens)
    if p == "openai":
        return _call_openai(system, user, max_tokens)
    if p == "anthropic":
        return _call_anthropic(system, user, max_tokens)
    if p == "gemini":
        return _call_gemini(system, user, max_tokens)

    logger.error("Unknown LLM_PROVIDER: %s", p)
    return ""


def _groq_attempt(model: str, system: str, user: str, max_tokens: int) -> tuple[str, str | None]:
    """Try one Groq model via the OpenAI-compatible endpoint. Returns (text, error_or_None)."""
    try:
        from openai import OpenAI
    except ImportError:
        return "", "openai package not installed (needed for Groq)"
    try:
        client = OpenAI(api_key=_GROQ_KEY, base_url=_GROQ_BASE_URL)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        return text, (None if text else "empty response")
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def _call_groq(system: str, user: str, max_tokens: int) -> str:
    """
    Groq — free tier ~14,400 req/day, 30 req/min. Uses Llama models via the
    OpenAI-compatible API. Get a key at https://console.groq.com/keys
    """
    for model in _groq_models():
        text, err = _groq_attempt(model, system, user, max_tokens)
        if text:
            return text
        if err:
            logger.warning("Groq %s: %s", model, err)
    return ""


def _call_openai(system: str, user: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=_OPENAI_KEY)
        resp = client.chat.completions.create(
            model=_model_name("openai"),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except ImportError:
        logger.error("openai package not installed — run: pip install openai")
        return ""
    except Exception as exc:
        logger.error("OpenAI call failed: %s", exc)
        return ""


def _call_anthropic(system: str, user: str, max_tokens: int) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
        msg = client.messages.create(
            model=_model_name("anthropic"),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text if msg.content else ""
    except ImportError:
        logger.error("anthropic package not installed — run: pip install anthropic")
        return ""
    except Exception as exc:
        logger.error("Anthropic call failed: %s", exc)
        return ""


def _gemini_attempt_new(model: str, system: str, user: str, max_tokens: int) -> tuple[str, str | None]:
    """Try one model via the new google-genai SDK. Returns (text, error_or_None)."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "", "google-genai SDK not installed"
    try:
        client = genai.Client(api_key=_GEMINI_KEY)
        cfg_kwargs = dict(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=0.2,
        )
        # Gemini 2.5 models "think" by default, which can consume the entire
        # output-token budget and leave no visible text. Disable it.
        if "2.5" in model:
            try:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass
        cfg = types.GenerateContentConfig(**cfg_kwargs)
        resp = client.models.generate_content(model=model, contents=user, config=cfg)
        text = (resp.text or "") if resp else ""
        return text, (None if text else "empty response")
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def _gemini_attempt_legacy(model: str, system: str, user: str, max_tokens: int) -> tuple[str, str | None]:
    """Try one model via the legacy google-generativeai SDK. Returns (text, error_or_None)."""
    try:
        import google.generativeai as genai
    except ImportError:
        return "", "google-generativeai SDK not installed"
    try:
        genai.configure(api_key=_GEMINI_KEY)
        gm = genai.GenerativeModel(model_name=model, system_instruction=system)
        resp = gm.generate_content(
            user,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.2},
        )
        text = (getattr(resp, "text", "") or "") if resp else ""
        return text, (None if text else "empty response")
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def _call_gemini(system: str, user: str, max_tokens: int) -> str:
    """
    Google Gemini — free tier (gemini-2.x-flash): 15 RPM, 1M tokens/day.
    Tries the new google-genai SDK first across candidate models, then the
    legacy SDK. Returns "" if everything fails (caller falls back to rule-based).
    """
    for model in _gemini_models():
        text, err = _gemini_attempt_new(model, system, user, max_tokens)
        if text:
            return text
        if err:
            logger.warning("Gemini %s (new SDK): %s", model, err)
    for model in _gemini_models():
        text, err = _gemini_attempt_legacy(model, system, user, max_tokens)
        if text:
            return text
        if err:
            logger.warning("Gemini %s (legacy SDK): %s", model, err)
    return ""


def test_call() -> dict:
    """
    Detailed live diagnostic for /llm/status?test=true.
    Tries every model on every SDK and surfaces the exact error for each —
    never raises. Returns the first success plus the full attempt log.
    """
    p = _provider()
    info: dict = {"provider": p, "configured": _is_available()}
    if not _is_available():
        info["error"] = "no API key configured"
        return info

    system, user = "You are a test assistant.", "Reply with exactly the word: OK"
    attempts: list[dict] = []

    if p == "groq":
        for model in _groq_models():
            text, err = _groq_attempt(model, system, user, 50)
            attempts.append({"model": model, "ok": bool(text), "error": err, "text": text[:80]})
            if text:
                info.update(working=True, test_response=text[:120],
                            used={"model": model}, attempts=attempts)
                return info
        info.update(working=False, attempts=attempts)
        return info

    if p == "gemini":
        for sdk_name, fn in (("google-genai", _gemini_attempt_new), ("legacy", _gemini_attempt_legacy)):
            for model in _gemini_models():
                text, err = fn(model, system, user, 100)
                attempts.append({
                    "sdk": sdk_name, "model": model,
                    "ok": bool(text), "error": err, "text": text[:80],
                })
                if text:
                    info.update(working=True, test_response=text[:120],
                                used={"sdk": sdk_name, "model": model}, attempts=attempts)
                    return info
        info.update(working=False, attempts=attempts)
        return info

    # openai / anthropic: simple round-trip
    text = complete(system, user, max_tokens=50)
    info["working"] = bool(text.strip())
    info["test_response"] = text[:120]
    return info
