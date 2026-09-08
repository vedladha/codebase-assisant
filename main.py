import asyncio
import os
import sys

from anthropic import Anthropic
from dotenv import load_dotenv

from mcp_client import MCPClient

load_dotenv()

MODEL = "claude-sonnet-5"


def to_claude_tools(mcp_tools):
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema,
        }
        for tool in mcp_tools
    ]


def result_to_text(result) -> str:
    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts) if parts else "(no output)"


async def run_conversation(anthropic, client, messages, tools):
    while True:
        response = anthropic.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=messages,
            tools=tools,
        )

        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text":
                print(f"\n{block.text}")

        if response.stop_reason != "tool_use":
            return

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            print(f"  [calling {block.name} {block.input}]")
            try:
                result = await client.call_tool(block.name, block.input)
                content = result_to_text(result)
                is_error = bool(getattr(result, "isError", False))
            except Exception as exc:
                content = f"Tool failed: {exc}"
                is_error = True

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})


async def main():
    anthropic = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    async with MCPClient(command=sys.executable, args=["mcp_server.py"]) as client:
        tools = to_claude_tools(await client.list_tools())
        print(f"Connected. Tools: {[t['name'] for t in tools]}")
        print("Ask a question, '/prompts' to list prompts, or 'quit' to exit.\n")

        messages = []

        while True:
            question = input("> ").strip()
            if question.lower() in {"quit", "exit"}:
                break
            if not question:
                continue

            if question.startswith("/"):
                parts = question[1:].split(maxsplit=1)
                name = parts[0]
                arg = parts[1] if len(parts) > 1 else ""

                if name == "prompts":
                    for prompt in await client.list_prompts():
                        print(f"  /{prompt.name} — {prompt.description}")
                    continue

                try:
                    prompt_messages = await client.get_prompt(name, {"focus": arg})
                except Exception as exc:
                    print(f"Unknown prompt: {exc}")
                    continue

                for message in prompt_messages:
                    text = getattr(message.content, "text", str(message.content))
                    messages.append({"role": message.role, "content": text})

                await run_conversation(anthropic, client, messages, tools)
                print()
                continue

            if "@readme" in question:
                readme = await client.read_resource("repo://readme")
                question = question.replace("@readme", "")
                question = (
                    f"Repository README:\n\n{readme}\n\n---\n\n{question.strip()}"
                )

            messages.append({"role": "user", "content": question})
            await run_conversation(anthropic, client, messages, tools)
            print()

if __name__ == "__main__":
    asyncio.run(main())