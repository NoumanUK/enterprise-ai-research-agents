from app.services.llm_service import LLMService

llm = LLMService()


def resolve_intent(task: str) -> str:
    if "mcp" not in task.lower():
        return task

    prompt = f"""
You are a query disambiguation system.

Task:
{task}

The acronym "MCP" is ambiguous.

Possible meanings include:
- Model Context Protocol in AI/LLM systems
- Multi-cloud platform
- Microsoft Configuration Manager
- Other domain-specific meanings

Use the task context to resolve the meaning.
If the task is about AI, LLMs, agents, Claude, Anthropic, tools, or integrations,
rewrite MCP as "Model Context Protocol".
If the context clearly indicates another meaning, use that meaning.
If unclear, preserve the ambiguity and rewrite the query to search for clarification.

Return ONLY the rewritten task.
"""

    return llm.generate(prompt).strip()