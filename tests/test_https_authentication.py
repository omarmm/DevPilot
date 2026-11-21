import ast
import unittest
from pathlib import Path


class HttpsAuthenticationFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "linux_work_setup.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        app = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "App"
        )
        cls.methods = {
            node.name: ast.unparse(node)
            for node in app.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_https_authentication_is_available_in_git_profiles_tab(self):
        self.assertIn("Set up HTTPS authentication", self.methods["_git_ui"])

    def test_only_selected_https_profile_can_start_authentication(self):
        method = self.methods["setup_https_authentication"]
        self.assertIn('profile.get("auth")!="https"', method)
        self.assertIn('profile.get("username"', method)
        self.assertIn("askyesno", method)

    def test_uses_github_cli_browser_login_and_credential_helper(self):
        method = self.methods["setup_https_authentication"]
        self.assertIn("gh auth login", method)
        self.assertIn("--git-protocol https", method)
        self.assertIn("--web", method)
        self.assertIn("gh auth setup-git", method)

    def test_checks_authenticated_account_matches_profile(self):
        method = self.methods["setup_https_authentication"]
        self.assertIn("gh api user", method)
        self.assertIn("expected_login", method)
        self.assertIn("does not match", method)

    def test_does_not_request_or_store_password_or_token(self):
        method = self.methods["setup_https_authentication"]
        self.assertNotIn('input(', method)
        self.assertNotIn("token =", method.lower())


if __name__ == "__main__":
    unittest.main()
