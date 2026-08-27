"""Typed runtime configuration loaded from the process environment."""

from ipaddress import IPv4Address

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    """Local runtime settings validated at the application boundary."""

    model_config = SettingsConfigDict(
        env_prefix="JOB_HUNTER_",
        extra="forbid",
        frozen=True,
    )

    api_host: IPv4Address = IPv4Address("127.0.0.1")
    api_port: int = Field(default=8000, ge=1, le=65535)
    frontend_origin: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:5173")
