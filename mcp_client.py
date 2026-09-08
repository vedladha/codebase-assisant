import sys
from contextlib import AsyncExitStack

from pydantic import AnyUrl

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self, command: str, args: list[str], env: dict | None = None):
        self._command = command
        self._args = args
        self._env = env
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()

    async def connect(self):
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env,
        )

        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        read, write = stdio_transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        await self._session.initialize()

    def session(self) -> ClientSession:
        if self._session is None:
            raise ConnectionError(
                "Client session not initialized. Call connect() first."
            )
        return self._session

    async def list_tools(self):
        result = await self.session().list_tools()
        return result.tools

    async def call_tool(self, tool_name: str, tool_input: dict):
        return await self.session().call_tool(tool_name, tool_input)

    async def read_resource(self, uri: str):
        result = await self.session().read_resource(AnyUrl(uri))
        parts = []
        for item in result.contents:
            if hasattr(item, "text"):
                parts.append(item.text)
        return "\n".join(parts)

    async def list_prompts(self):
        result = await self.session().list_prompts()
        return result.prompts

    async def get_prompt(self, prompt_name: str, args: dict | None = None):
        result = await self.session().get_prompt(prompt_name, args or {})
        return result.messages

    async def cleanup(self):
        await self._exit_stack.aclose()
        self._session = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


if __name__ == "__main__":
    import asyncio

    async def main():
        async with MCPClient(
            command=sys.executable,
            args=["mcp_server.py"],
        ) as client:
            tools = await client.list_tools()
            print("Tools:", [tool.name for tool in tools])

            prompts = await client.list_prompts()
            print("Prompts:", [prompt.name for prompt in prompts])

            result = await client.call_tool("read_file", {"file_path": "README.md"})
            print(result.content[0].text[:500])

    asyncio.run(main())