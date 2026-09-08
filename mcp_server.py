import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("CodebaseMCP", log_level="ERROR")

load_dotenv()
repo_path = os.environ.get("REPO_PATH")

if not repo_path:
    raise ValueError("Set REPO_PATH to the repository you want examined")

repo_root = Path(repo_path).expanduser().resolve()
if not repo_root.is_dir():
    raise ValueError(f"Directory does not exist: {repo_root}")


# Shared path guard
def resolve_in_repo(file_path: str) -> Path:
    relative_path = Path(file_path)

    if relative_path.is_absolute():
        raise ValueError("Provide a path relative to the repository root.")

    full_path = (repo_root / relative_path).resolve()

    if not full_path.is_relative_to(repo_root):
        raise ValueError("File path must stay inside the repository.")

    return full_path


# File reader tool
@mcp.tool(
    name="read_file",
    description="Read a UTF-8 text file from the configured repository."
)
def read_file(
    file_path: str = Field(
        description="Path relative to the repository root, e.g. src/main.py"
    )
) -> str:
    relative_path = Path(file_path)

    if relative_path.is_absolute():
        raise ValueError("Provide a path relative to the repository root.")

    full_path = (repo_root / relative_path).resolve()

    if not full_path.is_relative_to(repo_root):
        raise ValueError("File path must stay inside the repository.")

    if not full_path.is_file():
        raise ValueError(f"File not found: {file_path}")

    return full_path.read_text(encoding="utf-8")


# File search tool
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}


@mcp.tool(
    name="search_code",
    description=(
        "Search the repository for a text pattern. Returns matching lines as "
        "'path:line: text'. Use read_file on a returned path to see full context."
    )
)
def search_code(
    pattern: str = Field(
        description="Text to search for, e.g. a function name like 'get_user'"
    ),
    file_glob: str = Field(
        default="**/*.py",
        description="Glob relative to the repository root, e.g. '**/*.py' or 'src/**/*.ts'"
    ),
    max_results: int = Field(
        default=50,
        description="Stop after this many matching lines"
    )
) -> list[str]:
    needle = pattern.lower()
    results = []

    for path in sorted(repo_root.glob(file_glob)):
        if len(results) >= max_results:
            break

        if not path.is_file():
            continue

        relative = path.relative_to(repo_root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue

        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if needle in line.lower():
                    results.append(f"{relative.as_posix()}:{line_number}: {line.strip()[:200]}")
                    if len(results) >= max_results:
                        break

    return results


# Git diff tool
@mcp.tool(
    name="get_git_diff",
    description=(
        "Show uncommitted changes in the repository. Defaults to everything "
        "changed since the last commit."
    )
)
def get_git_diff(
    base: str = Field(
        default="HEAD",
        description="Git ref to compare against, e.g. 'HEAD', 'HEAD~3', 'main'"
    ),
    path_filter: str = Field(
        default="",
        description="Optional path to limit the diff to, e.g. 'src/' or 'app/models.py'"
    )
) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-~^")

    if not base or not set(base).issubset(allowed):
        raise ValueError(f"Invalid git ref: {base}")

    command = f"git -C '{repo_root}' diff {base}"

    if path_filter:
        resolve_in_repo(path_filter)
        if not set(path_filter).issubset(allowed):
            raise ValueError(f"Invalid path filter: {path_filter}")
        command += f" -- '{path_filter}'"

    with os.popen(command + " 2>&1") as stream:
        output = stream.read()

    if not output.strip():
        return "No changes found."

    if len(output) > 20000:
        return output[:20000] + "\n\n[diff truncated - narrow it with path_filter]"

    return output


if __name__ == "__main__":
    mcp.run(transport="stdio")