import os
import re

KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ZAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "MOONSHOT_API_KEY",
)


def redact(text: str) -> str:
    for name in KEY_NAMES:
        secret = os.getenv(name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", text)
