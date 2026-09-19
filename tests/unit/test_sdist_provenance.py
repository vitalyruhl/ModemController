"""Ensure setuptools captures source provenance before creating its release tree."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def versioned_source_class(build_info, base_class):
    tree = ast.parse((ROOT / "setup.py").read_text(encoding="utf-8"))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "VersionedSource"
    )
    namespace = {
        "Path": Path,
        "build_info": build_info,
        "json": json,
        "sdist": base_class,
    }
    module = ast.Module([class_node], [])
    exec(compile(ast.fix_missing_locations(module), "setup.py", "exec"), namespace)
    return namespace["VersionedSource"]


def test_sdist_uses_pre_release_tree_provenance(tmp_path):
    source_became_dirty = False

    def source_info():
        return {"dirty": source_became_dirty, "source_revision": "clean-source"}

    class GeneratedReleaseTree:
        def run(self):
            nonlocal source_became_dirty
            source_became_dirty = True
            self.make_release_tree(str(tmp_path), [])

        def make_release_tree(self, base_dir, files):
            pass

    command = versioned_source_class(source_info, GeneratedReleaseTree)()
    command.run()

    assert (
        (tmp_path / "source-build.json")
        .read_text(encoding="utf-8")
        .startswith('{\n  "dirty": false')
    )
