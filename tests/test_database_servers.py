import ast
import shlex
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "linux_work_setup.py"


class DatabaseServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module = ast.parse(SOURCE.read_text(encoding="utf-8"))
        catalog = next(
            node for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "DATABASE_SERVERS" for target in node.targets)
        )
        cls.servers = ast.literal_eval(catalog.value)
        parser = next(
            node for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "parse_unmanaged_database_processes"
        )
        namespace = {"Path": Path, "shlex": shlex}
        exec(compile(ast.Module(body=[parser], type_ignores=[]), str(SOURCE), "exec"), namespace)
        cls.parse_processes = staticmethod(namespace["parse_unmanaged_database_processes"])

    def test_supported_servers_and_packages_are_unique(self):
        self.assertEqual(
            {server["id"] for server in self.servers},
            {"mysql", "mariadb", "postgresql", "redis"},
        )
        packages = [server["package"] for server in self.servers]
        self.assertEqual(len(packages), len(set(packages)))

    def test_mysql_and_mariadb_are_declared_as_conflicts(self):
        by_id = {server["id"]: server for server in self.servers}
        self.assertIn("mariadb", by_id["mysql"]["conflicts"])
        self.assertIn("mysql", by_id["mariadb"]["conflicts"])
        self.assertEqual(by_id["mysql"]["port"], by_id["mariadb"]["port"])

    def test_detects_loader_started_mysql_and_its_data_paths(self):
        process = (
            "130042 /media/drive/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 "
            "--library-path /media/drive/lib:/media/drive/usr/lib "
            "/media/drive/usr/sbin/mysqld --daemonize "
            "--datadir=/tmp/opencode/mysql-data --socket=/tmp/opencode/mysql.sock "
            "--port=3300 --user=omar --pid-file=/tmp/opencode/mysql.pid"
        )
        found = self.parse_processes(process)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["pid"], "130042")
        self.assertEqual(found[0]["name"], "MySQL-compatible server")
        self.assertEqual(found[0]["port"], 3300)
        self.assertEqual(found[0]["datadir"], "/tmp/opencode/mysql-data")
        self.assertEqual(found[0]["socket"], "/tmp/opencode/mysql.sock")

    def test_ignores_shell_wrapper_that_only_mentions_mysqld(self):
        process = (
            "130031 /bin/bash -c 'mkdir -p /tmp/opencode/mysql-files; "
            "/media/drive/usr/sbin/mysqld --datadir=/tmp/opencode/mysql-data'"
        )
        self.assertEqual(self.parse_processes(process), [])

    def test_detects_regular_postgres_and_redis_processes(self):
        output = (
            "200 postgres -D /var/lib/postgresql/data\n"
            "201 redis-server 127.0.0.1:6379"
        )
        found = self.parse_processes(output)
        self.assertEqual([item["name"] for item in found], ["PostgreSQL server", "Redis server"])
        self.assertEqual([item["port"] for item in found], [5432, 6379])


if __name__ == "__main__":
    unittest.main()
