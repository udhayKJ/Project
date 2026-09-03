import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("api_security")


def _str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "t", "on")


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:qwerty%401234@localhost:5432/api_security"
    )
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-this-to-a-long-random-secret")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Master switch for vulnerability testing mode
    TEST_MODE: bool = _str_to_bool(os.getenv("TEST_MODE"), default=False)

    # Controlled vulnerability test flags
    ENABLE_BOLA_TEST: bool = _str_to_bool(os.getenv("ENABLE_BOLA_TEST"), default=False)
    ENABLE_BFLA_TEST: bool = _str_to_bool(os.getenv("ENABLE_BFLA_TEST"), default=False)
    ENABLE_WORKFLOW_TEST: bool = _str_to_bool(os.getenv("ENABLE_WORKFLOW_TEST"), default=False)
    ENABLE_CONTEXTUAL_TEST: bool = _str_to_bool(os.getenv("ENABLE_CONTEXTUAL_TEST"), default=False)

    @classmethod
    def reload_from_env(cls):
        """Reload configuration from environment (useful for testing runtime flag changes)."""
        load_dotenv(override=True)
        cls.DATABASE_URL = os.getenv("DATABASE_URL", cls.DATABASE_URL)
        cls.JWT_SECRET = os.getenv("JWT_SECRET", cls.JWT_SECRET)
        cls.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", cls.JWT_ALGORITHM)
        cls.TEST_MODE = _str_to_bool(os.getenv("TEST_MODE"), default=False)
        cls.ENABLE_BOLA_TEST = _str_to_bool(os.getenv("ENABLE_BOLA_TEST"), default=False)
        cls.ENABLE_BFLA_TEST = _str_to_bool(os.getenv("ENABLE_BFLA_TEST"), default=False)
        cls.ENABLE_WORKFLOW_TEST = _str_to_bool(os.getenv("ENABLE_WORKFLOW_TEST"), default=False)
        cls.ENABLE_CONTEXTUAL_TEST = _str_to_bool(os.getenv("ENABLE_CONTEXTUAL_TEST"), default=False)


settings = Settings()


def is_test_mode_active() -> bool:
    return settings.TEST_MODE


def is_bola_test_active() -> bool:
    active = settings.TEST_MODE and settings.ENABLE_BOLA_TEST
    if active:
        logger.warning("[TEST MODE] BOLA test active: Cross-tenant authorization checks bypassed")
    return active


def is_bfla_test_active() -> bool:
    active = settings.TEST_MODE and settings.ENABLE_BFLA_TEST
    if active:
        logger.warning("[TEST MODE] BFLA test active: Role authorization checks bypassed")
    return active


def is_workflow_test_active() -> bool:
    active = settings.TEST_MODE and settings.ENABLE_WORKFLOW_TEST
    if active:
        logger.warning("[TEST MODE] Workflow test active: State transition validation bypassed")
    return active


def is_contextual_test_active() -> bool:
    active = settings.TEST_MODE and settings.ENABLE_CONTEXTUAL_TEST
    if active:
        logger.warning("[TEST MODE] Contextual test active: Resource ownership checks bypassed")
    return active
