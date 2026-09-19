"""Generate installed metadata from the authoritative root version.json."""

import json
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from modem_controller.versioning import build_info, read_version  # noqa: E402


class VersionedBuild(build_py):
    def run(self):
        super().run()
        target = Path(self.build_lib) / "modem_controller"
        (target / "_version.json").write_bytes((ROOT / "version.json").read_bytes())
        (target / "_build.json").write_text(
            json.dumps(build_info(), indent=2), encoding="utf-8"
        )


class VersionedSource(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        (Path(base_dir) / "source-build.json").write_text(
            json.dumps(build_info(), indent=2), encoding="utf-8"
        )


setup(
    version=read_version(ROOT / "version.json"),
    cmdclass={"build_py": VersionedBuild, "sdist": VersionedSource},
)
