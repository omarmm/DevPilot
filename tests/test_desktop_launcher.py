import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesktopLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((ROOT / "linux_work_setup.py").read_text(encoding="utf-8"))
        cls.installer = ast.unparse(next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "install_desktop_shortcuts"
        ))
        app = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "App"
        )
        cls.init = ast.unparse(next(
            node for node in app.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        ))

    def test_application_icon_is_in_repository(self):
        icon = ROOT / "assets" / "devpilot.svg"
        self.assertTrue(icon.is_file())
        self.assertIn("<svg", icon.read_text(encoding="utf-8"))

    def test_installs_menu_and_desktop_launchers(self):
        self.assertIn("applications", self.installer)
        self.assertIn("devpilot.desktop", self.installer)
        self.assertIn("Desktop", self.installer)
        self.assertIn("Exec=/usr/bin/python3", self.installer)
        self.assertIn("Terminal=false", self.installer)

    def test_launcher_creation_does_not_block_app_startup(self):
        self.assertIn("install_desktop_shortcuts", self.init)
        self.assertIn("except Exception", self.init)


if __name__ == "__main__":
    unittest.main()
