"""Guards for the layering rules: domain and engineering code stays free of frameworks."""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "alembic", "reportlab", "openpyxl", "ezdxf")


def _imports(path: pathlib.Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _pure_files() -> list[pathlib.Path]:
    files = list((APP / "engineering").rglob("*.py"))
    for domain in (APP / "modules").glob("*/domain"):
        files += list(domain.rglob("*.py"))
    return files


def test_engineering_and_domain_code_imports_no_framework():
    assert len(_pure_files()) >= 6
    for f in _pure_files():
        for name in _imports(f):
            assert not name.startswith(FORBIDDEN), f"{f.relative_to(APP)} imports {name}"


def test_engineering_kernel_does_not_depend_on_modules():
    for f in (APP / "engineering").rglob("*.py"):
        for name in _imports(f):
            assert not name.startswith("app.modules") and not name.startswith("app.core"), f"{f.name} imports {name}"


def test_domain_code_reaches_only_the_kernel_and_its_own_module():
    for domain in (APP / "modules").glob("*/domain"):
        module = domain.parent.name
        for f in domain.rglob("*.py"):
            for name in _imports(f):
                if name.startswith("app."):
                    assert name.startswith(("app.engineering", f"app.modules.{module}.domain")), f"{f.name} imports {name}"
