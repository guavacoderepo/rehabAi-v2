"""Application configuration."""

import os

from db import DB_PATH


class Config:
    """Default configuration. Override with environment variables."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    DATABASE = os.environ.get("REHABAI_DATABASE", DB_PATH)

    # Number of days used for "recent" activity on the dashboard.
    DASHBOARD_RECENT_DAYS = 30
