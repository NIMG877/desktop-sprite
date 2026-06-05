import pytest
from desktop_sprite.ai.channel import AIText
from desktop_sprite.ui.ai_panel import AIPanelWidget


class _StubOrchestrator:
    def __init__(self):
        self.test_triggered = 0
    def trigger_test(self):
        self.test_triggered += 1


@pytest.fixture
def panel(qtbot):
    orch = _StubOrchestrator()
    p = AIPanelWidget(orchestrator=orch, history_max_lines=50)
    qtbot.addWidget(p)
    return p, orch


def test_panel_has_history_and_trigger_button(panel):
    p, _ = panel
    assert p.history_text() == ""
    assert p.trigger_button_text() == "发送测试事件"


def test_trigger_button_calls_orchestrator(panel, qtbot):
    p, orch = panel
    p.click_trigger()
    assert orch.test_triggered == 1


def test_append_history_shows_text(panel):
    p, _ = panel
    p.append_history(AIText(text="hello", source="ai", use_case_id="x", timestamp=0.0))
    p.append_history(AIText(text="world", source="fallback", use_case_id="y", timestamp=0.1))
    txt = p.history_text()
    assert "hello" in txt
    assert "world" in txt
    assert "ai" in txt
    assert "fallback" in txt


def test_clear_history(panel):
    p, _ = panel
    p.append_history(AIText(text="x", source="ai", use_case_id="x", timestamp=0.0))
    p.clear_history()
    assert p.history_text() == ""


def test_status_indicator_reflects_state(panel):
    p, _ = panel
    p.set_status("idle")
    assert "空闲" in p.status_text() or "idle" in p.status_text().lower()
    p.set_status("thinking")
    assert "思考" in p.status_text() or "thinking" in p.status_text().lower()
    p.set_status("error: 鉴权失败")
    assert "鉴权" in p.status_text() or "error" in p.status_text().lower()
