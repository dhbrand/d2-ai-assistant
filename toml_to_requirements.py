import tomllib  # Python 3.11+; use 'import tomli as tomllib' for 3.7-3.10
from pathlib import Path

TOML_PATH = Path("pyproject.toml")
REQS_PATH = Path("requirements.txt")

def parse_pep621_deps(data):
    """Parse [project] dependencies (PEP 621)"""
    deps = data.get("project", {}).get("dependencies", [])
    # Optionally include optional-dependencies
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        deps.extend(group)
    return deps

def parse_poetry_deps(data):
    """Parse [tool.poetry.dependencies] and [tool.poetry.group.dev.dependencies]"""
    deps = []
    poetry = data.get("tool", {}).get("poetry", {})
    main_deps = poetry.get("dependencies", {})
    for name, spec in main_deps.items():
        if name.lower() == "python":
            continue
        if isinstance(spec, str):
            deps.append(f"{name}{spec if spec != '*' else ''}")
        elif isinstance(spec, dict):
            # Handles extras, version, etc.
            version = spec.get("version", "")
            extras = spec.get("extras", [])
            marker = f"[{','.join(extras)}]" if extras else ""
            deps.append(f"{name}{marker}{version}")
    # Optionally add dev dependencies
    dev_deps = poetry.get("group", {}).get("dev", {}).get("dependencies", {})
    for name, spec in dev_deps.items():
        if isinstance(spec, str):
            deps.append(f"{name}{spec if spec != '*' else ''}")
        elif isinstance(spec, dict):
            version = spec.get("version", "")
            extras = spec.get("extras", [])
            marker = f"[{','.join(extras)}]" if extras else ""
            deps.append(f"{name}{marker}{version}")
    return deps

def main():
    with TOML_PATH.open("rb") as f:
        data = tomllib.load(f)
    deps = []
    # Try PEP 621 first
    deps = parse_pep621_deps(data)
    # If not found, try Poetry
    if not deps:
        deps = parse_poetry_deps(data)
    if not deps:
        print("No dependencies found in pyproject.toml")
        return
    # Write to requirements.txt
    with REQS_PATH.open("w") as f:
        for dep in deps:
            f.write(dep + "\n")
    print(f"Wrote {len(deps)} dependencies to {REQS_PATH}")

if __name__ == "__main__":
    main()