"""Runtime file-path resolution.

Centralises the rules for locating the default config, user overrides,
inventory and spirit-mark archives. The previous implementation computed
these paths inline in `main()`; pulling them into a small helper makes
them easy to test and override in different deployment contexts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolved filesystem paths used by the runtime.

    `config_path` is the always-present default configuration.
    `user_config_path` is where the in-app settings page writes overrides.
    `user_inventory_path` is where inventory entries are persisted.
    `user_spirit_mark_path` is where equipped / owned spirit marks live.
    """

    config_path: Path
    user_config_path: Path
    user_inventory_path: Path
    user_spirit_mark_path: Path

    @classmethod
    def from_config_path(cls, config_path: Path) -> "RuntimePaths":
        user_dir = config_path.parent / "user"
        return cls(
            config_path=config_path,
            user_config_path=user_dir / "user.json",
            user_inventory_path=user_dir / "inventory.json",
            user_spirit_mark_path=user_dir / "spirit_marks.json",
        )

    @classmethod
    def resolve_default(cls) -> "RuntimePaths":
        """Resolve the default paths shipped with the project.

        The default config lives at `<repo>/config/default.json`; user
        artefacts are stored under `<repo>/config/user/`.
        """

        config_path = Path(__file__).resolve().parents[2] / "config" / "default.json"
        return cls.from_config_path(config_path)
