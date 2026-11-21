import ast
import unittest
from pathlib import Path


class GitIdentityFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "linux_work_setup.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        app = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "App"
        )
        cls.app_methods = {
            node.name: ast.unparse(node)
            for node in app.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        backup = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Backup"
        )
        cls.backup_create = ast.unparse(next(
            node for node in backup.body
            if isinstance(node, ast.FunctionDef) and node.name == "create"
        ))

    def test_apply_action_detects_current_repository(self):
        method = self.app_methods["apply_git"]
        self.assertIn("_git_repository_root", method)
        self.assertIn("_apply_profile_to_repository", method)
        self.assertIn("apply_git_to_folder", method)

    def test_user_can_choose_repository_from_the_gui(self):
        self.assertIn("Apply to project folder", self.app_methods["_git_ui"])
        self.assertIn("Apply assigned profiles", self.app_methods["_ws_ui"])
        self.assertIn("_apply_workspace_git_configuration", self.app_methods["apply_workspace_profiles"])
        picker = self.app_methods["apply_git_to_folder"]
        self.assertIn("askdirectory", picker)
        self.assertIn("_apply_profile_to_repository", picker)

    def test_repository_identity_is_written_and_verified_locally(self):
        method = self.app_methods["_apply_profile_to_repository"]
        self.assertIn("--local", method)
        self.assertIn("--get", method)
        self.assertIn("user.name", method)
        self.assertIn("user.email", method)

    def test_repository_git_config_is_backed_up_before_change(self):
        method = self.app_methods["_apply_profile_to_repository"]
        self.assertIn("--git-path", method)
        self.assertIn("config", method)
        self.assertIn("extra_files=[config_path]", method)
        self.assertIn("rollback_copy", method)
        self.assertIn("shutil.copy2", method)
        self.assertIn("extra_files=()", self.backup_create)


if __name__ == "__main__":
    unittest.main()
