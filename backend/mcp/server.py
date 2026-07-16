"""
Jessie — backend/mcp/server.py
FastMCP server. Claude Code and Claude Desktop connect here.
Calls the same FastAPI backend as the VS Code extension.
Add to claude_desktop_config.json or .vscode/mcp.json to use.
"""

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Jessie")
BACKEND = "http://localhost:8000"


@mcp.tool()
async def ask_jessie(
    prompt: str,
    user_id: str,
    workspace_id: str = "",
    language: str = "",
    open_file_content: str = "",
    selected_code: str = "",
    error_message: str = "",
) -> str:
    """
    Send a coding task to Jessie.
    Jessie coaches your prompt, injects codebase context,
    calls GitHub Copilot intelligently, checks the output quality,
    and returns clean code.

    Args:
        prompt: Your coding task — can be vague, Jessie will improve it
        user_id: Your name or team identifier
        workspace_id: Leave empty — auto-detected
        language: python | typescript | java | go | rust (or leave empty)
        open_file_content: Paste the content of the file you are working in
        selected_code: Paste any code you have highlighted
        error_message: Paste any terminal error
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Phase 1: prepare
        prep = await client.post(f"{BACKEND}/prepare", json={
            "prompt": prompt, "user_id": user_id,
            "workspace_id": workspace_id, "language": language,
            "open_file_content": open_file_content,
            "selected_code": selected_code, "error_message": error_message,
        })
        if prep.status_code != 200:
            return f"Jessie error (prepare): {prep.text}"

        prep_data = prep.json()

        # If component reuse — return immediately
        if prep_data["component_exists"]:
            return prep_data["generated_code"]

        # Show what Jessie improved
        result = (
            f"[Jessie improved your prompt]\n"
            f"Complexity: {prep_data['complexity_score']}/10\n\n"
            f"Note: In the VS Code extension, you would approve this prompt "
            f"before it goes to Copilot.\n\n"
            f"Improved prompt sent to Copilot:\n{prep_data['improved_prompt']}\n\n"
            f"[In MCP mode, Copilot is called via the VS Code extension. "
            f"For full Jessie experience, use the VS Code extension.]"
        )
        return result


@mcp.tool()
async def check_my_requests(user_id: str) -> str:
    """Check how many Jessie requests you have made today."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BACKEND}/requests/{user_id}")
    d = r.json()
    return f"User: {d['user_id']} — Requests today: {d['requests_today']}"


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
