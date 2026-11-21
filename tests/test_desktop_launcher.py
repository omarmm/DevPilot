import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesktopLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((ROOT / "linux_work_setup.py").read_text(encoding="utf-8"))
        cls.functions = {
            node.name: ast.unparse(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        app = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "App"
        )
        cls.methods = {
            node.name: ast.unparse(node)
            for node in app.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_application_icon_is_in_repository(self):
        icon = ROOT / "assets" / "devpilot.svg"
        self.assertTrue(icon.is_file())
        self.assertIn("<svg", icon.read_text(encoding="utf-8"))

    def test_installs_menu_and_desktop_launchers(self):
        installer = self.functions["install_desktop_shortcuts"]
        self.assertIn("applications", installer)
        self.assertIn("devpilot.desktop", installer)
        self.assertIn("DevPilot.desktop", installer)
        self.assertIn("mkdir", installer)
        self.assertIn("Desktop", installer)
        self.assertIn("Exec=/usr/bin/python3", installer)
        self.assertIn("Terminal=false", installer)
        self.assertIn("chmod", installer)

    def test_desktop_shortcut_can_be_created_manually_from_ui(self):
        self.assertIn("Create Desktop Shortcut", self.methods["_ui"])
        self.assertIn("install_desktop_shortcuts", self.methods["create_desktop_shortcut"])

    def test_launcher_creation_does_not_block_app_startup(self):
        self.assertIn("install_desktop_shortcuts", self.methods["__init__"])
        self.assertIn("except Exception", self.methods["__init__"])


if __name__ == "__main__":
    unittest.main()
