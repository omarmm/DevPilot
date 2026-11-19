import ast
import unittest
from pathlib import Path


class AgentCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "linux_work_setup.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
        assignment = next(
            node for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "AI_AGENTS" for target in node.targets)
        )
        cls.agents = ast.literal_eval(assignment.value)

    def test_supported_agent_ids_and_commands_are_unique(self):
        self.assertEqual(
            {agent["id"] for agent in self.agents},
            {"opencode", "claude", "codex", "copilot"},
        )
        commands = [agent["command"] for agent in self.agents]
        self.assertEqual(len(commands), len(set(commands)))

    def test_every_agent_has_an_official_installer_and_documentation(self):
        for agent in self.agents:
            with self.subTest(agent=agent["id"]):
                self.assertTrue(agent["install_command"].startswith("curl -fsSL https://"))
                self.assertTrue(agent["docs"].startswith("https://"))
                self.assertNotIn("sudo", agent["install_command"])

    def test_codex_and_copilot_are_not_mixed_up(self):
        by_id = {agent["id"]: agent for agent in self.agents}
        self.assertEqual(by_id["codex"]["command"], "codex")
        self.assertEqual(by_id["copilot"]["command"], "copilot")
        self.assertIn("chatgpt.com", by_id["codex"]["install_command"])
        self.assertIn("gh.io", by_id["copilot"]["install_command"])


if __name__ == "__main__":
    unittest.main()
