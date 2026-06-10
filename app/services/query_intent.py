from app.services.llm_service import LLMService

llm = LLMService()


def resolve_intent(task: str) -> str:
    """
    Forces MCP to be interpreted correctly before search.
    """

    prompt = f"""
You are a query disambiguation system.

Task:
{task}

IMPORTANT:
"MCP" most likely refers to "Model Context Protocol (Anthropic)" in AI context.

Rewrite the task so that search engines will return ONLY AI/LLM-related results.

Rules:
- If MCP appears, expand it to Model Context Protocol
- Avoid Microsoft Cloud Platform unless explicitly requested
- Keep meaning focused on AI systems and enterprise AI

Return ONLY the rewritten task.
"""

    return llm.generate(prompt).strip()