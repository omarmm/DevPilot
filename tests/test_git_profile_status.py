import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitProfileStatusAndInstallProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((ROOT / "linux_work_setup.py").read_text(encoding="utf-8"))
        cls.functions = {
            node.name: ast.unparse(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        app = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "App")
        cls.methods = {
            node.name: ast.unparse(node)
            for node in app.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_https_profile_status_checks_exact_github_account(self):
        method = self.functions["github_cli_auth_status"]
        self.assertIn("gh", method)
        self.assertIn("auth", method)
        self.assertIn("status", method)
        self.assertIn("username", method)
        self.assertIn("Authenticated", method)
        self.assertIn("Not authenticated", method)

    def test_profile_table_displays_auth_status(self):
        ui = self.methods["_git_ui"]
        refresh = self.methods["refresh_profiles"]
        self.assertIn("status", ui)
        self.assertIn("GitHub status", ui)
        self.assertIn("github_cli_auth_status", refresh)

    def test_github_cli_install_runs_in_background_with_progress_indicator(self):
        method = self.methods["_install_gh_async"]
        self.assertIn("threading.Thread", method)
        self.assertIn("Progressbar", method)
        self.assertIn("indeterminate", method)
        self.assertIn("pkexec", method)

    def test_launcher_does_not_set_a_nonexistent_working_directory(self):
        launcher = self.functions["install_desktop_shortcuts"]
        self.assertNotIn("Path=", launcher)
        self.assertIn("install_dir", launcher)


if __name__ == "__main__":
    unittest.main()
