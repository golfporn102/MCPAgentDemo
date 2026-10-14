
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from config import PROJECT_DIR
import sys
mcp = FastMCP("Java Code Tools")

# แก้เป็นโฟลเดอร์โปรเจกต์ Java ของคุณ
PROJECT_ROOT = Path(PROJECT_DIR).resolve()

print("MCP Server starting", file=sys.stderr)
def safe_java_path(relative_path: str) -> Path:
    path = (PROJECT_ROOT / relative_path).resolve()

    # ป้องกันการอ่านไฟล์นอกโปรเจกต์
    if not path.is_relative_to(PROJECT_ROOT):
        raise ValueError("Path is outside project directory")

    if path.suffix.lower() != ".java":
        raise ValueError("Only .java files are allowed")

    if not path.is_file():
        raise FileNotFoundError(relative_path)

    return path


@mcp.tool()
def list_java_files() -> list[str]:
    """List Java source files in the project."""
    return [
        str(path.relative_to(PROJECT_ROOT))
        for path in PROJECT_ROOT.rglob("*.java")
        if "target" not in path.parts
        and ".git" not in path.parts
    ]


@mcp.tool()
def read_java_file(relative_path: str) -> str:
    """Read a Java source file by its relative path."""
    path = safe_java_path(relative_path)
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run()
