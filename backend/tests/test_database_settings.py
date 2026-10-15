import unittest

from app.database import database_settings


class DatabaseSettingsTests(unittest.TestCase):
    def test_uses_local_sqlite_by_default(self) -> None:
        url, connect_args = database_settings({})

        self.assertEqual(url, "sqlite:///./videos.db")
        self.assertEqual(connect_args, {"check_same_thread": False})

    def test_uses_turso_when_remote_credentials_are_configured(self) -> None:
        url, connect_args = database_settings(
            {
                "TURSO_DATABASE_URL": "libsql://videohub-example.turso.io",
                "TURSO_AUTH_TOKEN": "secret",
            }
        )

        self.assertEqual(
            url,
            "sqlite+libsql://videohub-example.turso.io?secure=true",
        )
        self.assertEqual(connect_args, {"auth_token": "secret"})

    def test_requires_both_turso_credentials(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "devem ser configurados juntos"):
            database_settings({"TURSO_DATABASE_URL": "libsql://example"})

    def test_rejects_local_sqlite_fallback_on_vercel(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "não é persistente"):
            database_settings({"VERCEL": "1"})


if __name__ == "__main__":
    unittest.main()
