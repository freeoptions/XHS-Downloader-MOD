from importlib.metadata import PackageNotFoundError
from pathlib import Path
from runpy import run_path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class BuildOptionsTest(TestCase):
    def build_options(self, metadata):
        freeze = ModuleType("cx_Freeze")
        freeze.Executable = Mock()
        freeze.setup = Mock()
        with (
            patch.dict("sys.modules", {"cx_Freeze": freeze}),
            patch("importlib.metadata.distribution", **metadata),
        ):
            run_path(str(Path(__file__).resolve().parents[1] / "setup.py"))
        return freeze.setup.call_args.kwargs["options"]["build_exe"]

    def test_optional_mcp_dependency_can_be_absent(self):
        options = self.build_options({"side_effect": PackageNotFoundError("opentelemetry-api")})
        self.assertNotIn("opentelemetry", options["packages"])
        self.assertEqual(options["include_files"], [("static", "static"), ("locale", "locale")])

    def test_installed_telemetry_keeps_package_and_metadata(self):
        path = Path("opentelemetry_api-1.0.dist-info")
        options = self.build_options({"return_value": SimpleNamespace(_path=path)})
        self.assertIn("opentelemetry", options["packages"])
        self.assertIn((str(path), f"lib/{path.name}"), options["include_files"])
