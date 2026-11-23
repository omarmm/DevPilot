import ast
import shlex
import re
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
        helpers = [node for node in module.body if isinstance(node, ast.FunctionDef)
                   and node.name in {"mysql_sql_literal", "build_mysql_user_sql", "_validate_access_credentials", "_sql_string_literal", "build_postgresql_user_sql", "build_redis_acl_command", "redis_acl_user_exists"}]
        helper_namespace = {"re": re}
        exec(compile(ast.Module(body=helpers, type_ignores=[]), str(SOURCE), "exec"), helper_namespace)
        cls.build_mysql_user_sql = staticmethod(helper_namespace["build_mysql_user_sql"])
        cls.build_postgresql_user_sql = staticmethod(helper_namespace["build_postgresql_user_sql"])
        cls.build_redis_acl_command = staticmethod(helper_namespace["build_redis_acl_command"])
        cls.redis_acl_user_exists = staticmethod(helper_namespace["redis_acl_user_exists"])
        cls.parse_processes = staticmethod(namespace["parse_unmanaged_database_processes"])

    def test_mysql_user_sql_is_scoped_to_database_by_default_mode(self):
        sql = self.build_mysql_user_sql('omar_dev', 'a-strong-password-123', 'database', 'sandbox')
        self.assertIn("CREATE USER 'omar_dev'@'127.0.0.1'", sql)
        self.assertIn('GRANT ALL PRIVILEGES ON `sandbox`.*', sql)
        self.assertNotIn('ON *.*', sql)

    def test_mysql_admin_mode_is_explicit_and_can_manage_users(self):
        sql = self.build_mysql_user_sql('omar_admin', 'a-strong-password-123', 'admin')
        self.assertIn('GRANT ALL PRIVILEGES ON *.*', sql)
        self.assertIn('GRANT CREATE USER ON *.*', sql)

    def test_mysql_account_input_is_validated_and_password_is_escaped(self):
        with self.assertRaises(ValueError):
            self.build_mysql_user_sql("bad'user", 'a-strong-password-123', 'admin')
        with self.assertRaises(ValueError):
            self.build_mysql_user_sql('omar', 'short', 'admin')
        sql = self.build_mysql_user_sql('omar', "pass'word\\123456", 'admin')
        self.assertIn("pass\\'word\\\\123456", sql)

    def test_postgresql_user_sql_is_scoped_to_existing_database(self):
        sql = self.build_postgresql_user_sql("app_user", "strong-password-123", "app_db")
        self.assertIn('CREATE ROLE "app_user" WITH LOGIN', sql)
        self.assertIn('GRANT CONNECT ON DATABASE "app_db"', sql)
        self.assertIn("GRANT USAGE, CREATE ON SCHEMA public", sql)
        self.assertIn("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public", sql)
        self.assertNotIn("SUPERUSER", sql.upper())
        self.assertNotIn("CREATEDB", sql.upper())

    def test_postgresql_user_sql_rejects_invalid_identifiers(self):
        with self.assertRaises(ValueError):
            self.build_postgresql_user_sql("bad;role", "strong-password-123", "app_db")
        with self.assertRaises(ValueError):
            self.build_postgresql_user_sql("app_user", "short", "bad-db")

    def test_redis_acl_is_limited_to_key_pattern_and_app_commands(self):
        payload = self.build_redis_acl_command("app_user", "strong-password-123", "app:*")
        self.assertIn("ACL", payload)
        self.assertIn("~app:*", payload)
        self.assertIn("+@read", payload)
        self.assertIn("+@write", payload)
        self.assertNotIn("+@admin", payload)
        self.assertNotIn("allcommands", payload.lower())

    def test_redis_acl_rejects_invalid_patterns(self):
        with self.assertRaises(ValueError):
            self.build_redis_acl_command("app_user", "strong-password-123", "*")
        with self.assertRaises(ValueError):
            self.build_redis_acl_command("app_user", "strong-password-123", "app:*;ACL")

    def test_redis_existing_user_detection_matches_exact_username(self):
        acl_list = "user default on nopass ~* &* +@all\nuser app_user on ~app:* +@read"
        self.assertTrue(self.redis_acl_user_exists(acl_list, "app_user"))
        self.assertFalse(self.redis_acl_user_exists(acl_list, "app"))
        self.assertFalse(self.redis_acl_user_exists(acl_list, "other"))

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
