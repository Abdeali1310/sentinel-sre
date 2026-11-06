"""The redaction list is built from the .env itself, not from a keyword guess."""

from sentinel.config import Settings, load_settings

SECRET = "ghp_9f3c2b1a4d5e6f708192a3b4c5d6e7f80912"


def test_secret_values_are_collected_from_the_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        f"GITHUB_TOKEN={SECRET}\nCHAOS_TOKEN=chaos-12345678\nAPI_URL=http://api.test\n",
        encoding="utf-8",
    )

    settings = load_settings(env)

    assert SECRET in settings.secrets
    assert "chaos-12345678" in settings.secrets
    assert "http://api.test" not in settings.secrets


def test_short_values_are_not_treated_as_secrets(tmp_path):
    env = tmp_path / ".env"
    env.write_text("API_KEY=x\n", encoding="utf-8")

    assert load_settings(env).secrets == []


def test_github_repo_accepts_an_owner_slash_repo_value():
    settings = Settings(github_owner="", github_repo="acme/thing", _env_file=None)

    assert (settings.github_owner, settings.github_repo) == ("acme", "thing")
