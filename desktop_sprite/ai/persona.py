"""Persona 加载器——把 AIPersonaConfig 包成 Persona 不可变记录。"""
from __future__ import annotations

from dataclasses import dataclass

from desktop_sprite.utils.config import AppConfig


@dataclass(frozen=True, slots=True)
class Persona:
    """LLM 的人设/系统提示词封装。

    `name` 给 prompt 模板用（`{persona_name}`）；`system_prompt` 进
    LLM 的 system 消息；`default_fallback` 在 provider 失败且 use_case
    无 fallback_text 时显示。
    """

    name: str
    system_prompt: str
    default_fallback: str

    @classmethod
    def from_config(cls, config: AppConfig, character_id: str = "pet") -> "Persona":
        persona_cfg = config.ai_persona
        return cls(
            name=character_id,
            system_prompt=persona_cfg.system_prompt,
            default_fallback=persona_cfg.default_fallback,
        )
