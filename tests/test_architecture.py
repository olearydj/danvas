from __future__ import annotations

import ast
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
    ("auth.py", "canvas_from_args"),
    ("panopto.py", "command_panopto_captions"),
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


def test_resolve_api_key_call_sites_are_bounded_and_pass_secret_name() -> None:
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
