"""Garde le sens des dépendances entre couches : une couche n'importe que celles du dessous."""

import ast
from pathlib import Path

import pytest

import jobgrep

PACKAGE = "jobgrep"
SOURCE_DIR = Path(jobgrep.__file__).parent

# Couche -> couches et modules du paquet qu'elle a le droit d'importer
ALLOWED = {
    "config": set(),
    "errors": set(),
    "schemas": set(),
    "site_texts": {"config"},
    "data": {"config", "errors"},
    "agent": {"data", "config", "errors"},
    "assistant": {"config"},
    "services": {"assistant", "site_texts", "data", "schemas", "config", "errors"},
    "container": {"services", "agent", "assistant", "data", "config"},
    "api": {"container", "services", "site_texts", "schemas", "config", "errors"},
    "cli": {"container", "schemas", "config", "errors"},
}
# Bibliothèques réservées à une couche : les services ne doivent dépendre d'aucune interface
RESERVED_LIBRARIES = {"fastapi": {"api"}, "sqlalchemy": {"data"}, "alembic": {"data"}}


def layer_of(path: Path) -> str:
    return path.relative_to(SOURCE_DIR).parts[0].removesuffix(".py")


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            # « from paquet import module » importe aussi le module
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


SOURCE_FILES = sorted(path for path in SOURCE_DIR.rglob("*.py") if path.name != "__init__.py")


def test_every_layer_has_its_rule():
    assert {layer_of(path) for path in SOURCE_FILES} == set(ALLOWED)


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: path.relative_to(SOURCE_DIR).as_posix())
def test_module_only_imports_the_layers_below(path):
    layer = layer_of(path)
    for module in imported_modules(path):
        root, _, rest = module.partition(".")
        if root == PACKAGE and rest:
            imported_layer = rest.split(".")[0]
            assert imported_layer == layer or imported_layer in ALLOWED[layer], f"{layer} importe {module}"
        elif root in RESERVED_LIBRARIES:
            assert layer in RESERVED_LIBRARIES[root], f"{layer} importe {root}"
