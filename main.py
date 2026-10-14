
import asyncio
import json
import sys
from pathlib import Path

from google import genai
from google.genai import types

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import GEMINI_API_KEY, GEMINI_MODEL


# -----------------------------
# Configuration
# -----------------------------

BASE_DIR = Path(__file__).resolve().parent
SERVER_PATH = BASE_DIR / "mcp_server.py"

client = genai.Client(api_key=GEMINI_API_KEY)

server_params = StdioServerParameters(
    command=sys.executable,
    args=["-u", str(SERVER_PATH)],
    cwd=str(BASE_DIR),
)


# -----------------------------
# Convert MCP result to JSON
# -----------------------------

def convert_mcp_result(result):
    content = []

    for item in result.content:
        if hasattr(item, "text"):
            content.append(item.text)
        else:
            content.append(str(item))

    return {
        "content": content,
        "isError": result.isError,
    }


# -----------------------------
# Main Agent
# -----------------------------

async def main():

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            # 1. Initialize MCP connection
            await session.initialize()
            print("MCP connected")

            # 2. Discover available MCP tools
            mcp_result = await session.list_tools()

            if not mcp_result.tools:
                print("ไม่พบ MCP tools")
                return

            print("Available MCP tools:")

            for tool in mcp_result.tools:
                print(f"- {tool.name}: {tool.description}")

            # 3. Convert MCP tools to Gemini function declarations
            function_declarations = [
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description or "",
                    parameters_json_schema=tool.inputSchema,
                )
                for tool in mcp_result.tools
            ]

            gemini_tools = [
                types.Tool(
                    function_declarations=function_declarations
                )
            ]

            # 4. Initial user request
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=(
                            "Search for Java files in this project. "
                            "Identify the Service class related to user registration. "
                            "Read the relevant file and explain its business logic. "
                            "If no relevant file is found, state that clearly."
                        )
                        )
                    ],
                )
            ]

            # 5. Agent loop: Gemini -> MCP -> Gemini
            max_turns = 10

            for turn in range(max_turns):

                response = await client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        tools=gemini_tools,
                    ),
                )

                if not response.candidates:
                    print("Gemini ไม่ส่งคำตอบกลับมา")
                    return

                model_content = response.candidates[0].content

                if model_content is None:
                    print(response.text or "Gemini ส่งคำตอบว่าง")
                    return

                # Preserve Gemini's response in conversation history
                contents.append(model_content)

                # Find function calls requested by Gemini
                function_calls = [
                    part.function_call
                    for part in (model_content.parts or [])
                    if part.function_call is not None
                ]

                # No tool call means Gemini has finished
                if not function_calls:
                    print(response.text or "")
                    return

                # Execute each requested MCP tool
                function_response_parts = []

                for fc in function_calls:
                    tool_name = fc.name
                    arguments = dict(fc.args or {})

                    print(f"\nCalling MCP tool: {tool_name}")
                    print(f"Arguments: {arguments}")

                    try:
                        tool_result = await session.call_tool(
                            tool_name,
                            arguments=arguments,
                        )

                        result_data = convert_mcp_result(tool_result)

                    except Exception as exc:
                        result_data = {
                            "error": str(exc),
                            "tool": tool_name,
                        }

                    print(
                        "MCP result:",
                        json.dumps(
                            result_data,
                            ensure_ascii=False,
                            default=str,
                        ),
                    )

                    # Return MCP result to Gemini
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response=result_data,
                        )
                    )

                contents.append(
                    types.Content(
                        role="user",
                        parts=function_response_parts,
                    )
                )

            print(
                f"Agent หยุดหลังทำงานครบ {max_turns} รอบ "
                "เพื่อป้องกันการเรียก Tool วนไม่สิ้นสุด"
            )


if __name__ == "__main__":
    asyncio.run(main())
