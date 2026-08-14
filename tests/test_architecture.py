from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "danvas"
FORBIDDEN_EDGES = {
    ("sources", "assignments"),
    ("sources", "pages"),
    ("snapshot_collections", "pages"),
    ("authored_assets", "config"),
}
LEGACY_COMPLEXITY_EXCEPTIONS = {
    ("authored_content.py", "comparable_value"),
    ("page_sources.py", "check_css"),
    ("pages.py", "build_pages_sync_plan"),
    ("status.py", "compare_pages"),
}
RESOLVE_API_KEY_CALLS = {
    ("auth.py", "resolve_canvas_credential"),
}
RESOLVE_CANVAS_CREDENTIAL_CALLS = {
    ("auth.py", "canvas_from_args"),
    ("panopto.py", "command_panopto_captions"),
}
RESOLVE_NEUTRAL_CREDENTIAL_CALLS = {
    ("auth.py", "resolve_canvas_credential"),
}
CURRENT_PROVIDER_IMPORTS = Counter(
    {
        ("auth.py", "secretpath"): 1,
        ("cli.py", "dotenv"): 1,
    }
)
CURRENT_PROVIDER_CALLS = Counter(
    {
        ("auth.py", "resolve_api_key", "resolve_named_secret"): 1,
        ("auth.py", "build_auth_doctor_report", "doctor_report"): 1,
        ("auth.py", "build_auth_doctor_report", "resolve_named_secret"): 1,
        ("cli.py", "main", "load_dotenv"): 1,
    }
)
PROVIDER_PACKAGES = {
    "azure",
    "boto3",
    "dotenv",
    "google",
    "hvac",
    "keyring",
    "onepassword",
    "secretspec",
    "secretpath",
}
PROCESS_CALLS = {
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
    "multiprocessing": {"Process"},
    "os": {
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "fork",
        "popen",
        "posix_spawn",
        "posix_spawnp",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "system",
    },
    "pty": {"spawn"},
    "subprocess": {"Popen", "call", "check_call", "check_output", "run"},
}


def package_import_graph() -> dict[str, set[str]]:
    modules = {path.stem for path in PACKAGE_ROOT.glob("*.py") if path.name != "__init__.py"}
    graph = {module: set() for module in modules}
    for path in PACKAGE_ROOT.glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            graph[source].update(import_targets(node, modules))
    return graph


def import_targets(node: ast.AST, modules: set[str]) -> set[str]:
    targets: set[str] = set()
    if isinstance(node, ast.ImportFrom):
        if node.level == 1:
            if node.module:
                targets.add(node.module.split(".", 1)[0])
            else:
                targets.update(alias.name for alias in node.names)
        elif node.module == "danvas":
            targets.update(alias.name for alias in node.names)
        elif node.module and node.module.startswith("danvas."):
            targets.add(node.module.split(".", 1)[1].split(".", 1)[0])
    elif isinstance(node, ast.Import):
        targets.update(
            alias.name.split(".", 1)[1].split(".", 1)[0]
            for alias in node.names
            if alias.name.startswith("danvas.")
        )
    return targets & modules


def strongly_connected_components(graph: dict[str, set[str]]) -> list[set[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: set[str] = set()
        while True:
            target = stack.pop()
            on_stack.remove(target)
            component.add(target)
            if target == node:
                break
        components.append(component)

    for module in sorted(graph):
        if module not in indices:
            visit(module)
    return components


def test_danvas_package_import_graph_is_acyclic() -> None:
    cycles = [
        sorted(component)
        for component in strongly_connected_components(package_import_graph())
        if len(component) > 1
    ]
    assert cycles == []


def test_low_level_module_edges_remain_forbidden() -> None:
    graph = package_import_graph()
    present = sorted(edge for edge in FORBIDDEN_EDGES if edge[1] in graph[edge[0]])
    assert present == []
    assert graph["project_config"] == set()


def test_only_documented_legacy_functions_suppress_complexity() -> None:
    exceptions: set[tuple[str, str]] = set()
    for path in PACKAGE_ROOT.glob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        tree = ast.parse("\n".join(lines), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            declaration = lines[node.lineno - 1]
            if "noqa: C901" in declaration:
                exceptions.add((path.name, node.name))

    assert exceptions == LEGACY_COMPLEXITY_EXCEPTIONS


def test_legacy_resolve_api_key_call_site_is_bounded_and_passes_secret_name() -> None:
    found: set[tuple[str, str]] = set()
    missing_secret_name: set[tuple[str, str]] = set()
    for path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "resolve_api_key":
                    continue
                call_site = (path.name, function.name)
                found.add(call_site)
                if "secret_name" not in {keyword.arg for keyword in node.keywords}:
                    missing_secret_name.add(call_site)

    assert found == RESOLVE_API_KEY_CALLS
    assert missing_secret_name == set()


def test_canvas_and_panopto_share_one_credential_boundary() -> None:
    found: set[tuple[str, str]] = set()
    for path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "resolve_canvas_credential"
                for node in ast.walk(function)
            ):
                found.add((path.name, function.name))

    assert found == RESOLVE_CANVAS_CREDENTIAL_CALLS


def test_neutral_credential_reader_has_one_reviewed_entry_point() -> None:
    found: set[tuple[str, str]] = set()
    for path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "resolve_credential"
                for node in ast.walk(function)
            ):
                found.add((path.name, function.name))

    assert found == RESOLVE_NEUTRAL_CREDENTIAL_CALLS


def test_current_provider_imports_and_calls_match_reviewed_baseline() -> None:
    imports: Counter[tuple[str, str]] = Counter()
    calls: Counter[tuple[str, str, str]] = Counter()
    provider_call_names = {"doctor_report", "load_dotenv", "resolve_named_secret"}

    for path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    package = alias.name.split(".", 1)[0]
                    if package in PROVIDER_PACKAGES:
                        imports[(path.name, package)] += 1
            elif isinstance(node, ast.ImportFrom) and node.module:
                package = node.module.split(".", 1)[0]
                if package in PROVIDER_PACKAGES:
                    imports[(path.name, package)] += 1
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in provider_call_names
                ):
                    calls[(path.name, function.name, node.func.id)] += 1

    assert imports == CURRENT_PROVIDER_IMPORTS
    assert calls == CURRENT_PROVIDER_CALLS


def process_aliases(tree: ast.AST) -> tuple[dict[str, str], dict[str, str]]:
    module_aliases: dict[str, str] = {}
    callable_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".", 1)[0]
                if module in PROCESS_CALLS:
                    module_aliases[alias.asname or module] = module
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".", 1)[0] in PROCESS_CALLS
        ):
            module = node.module.split(".", 1)[0]
            for alias in node.names:
                if alias.name in PROCESS_CALLS[module]:
                    callable_aliases[alias.asname or alias.name] = (
                        f"{module}.{alias.name}"
                    )
    return module_aliases, callable_aliases


def process_call_name(
    node: ast.Call,
    *,
    module_aliases: dict[str, str],
    callable_aliases: dict[str, str],
) -> str | None:
    if isinstance(node.func, ast.Name):
        return callable_aliases.get(node.func.id)
    if not isinstance(node.func, ast.Attribute) or not isinstance(
        node.func.value, ast.Name
    ):
        return None
    module = module_aliases.get(node.func.value.id)
    if module and node.func.attr in PROCESS_CALLS[module]:
        return f"{module}.{node.func.attr}"
    return None


def test_production_process_spawn_call_sites_are_empty() -> None:
    calls: Counter[tuple[str, str, str]] = Counter()

    for path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_aliases, callable_aliases = process_aliases(tree)

        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                call_name = process_call_name(
                    node,
                    module_aliases=module_aliases,
                    callable_aliases=callable_aliases,
                )
                if call_name:
                    calls[(path.name, function.name, call_name)] += 1

    assert calls == Counter()
