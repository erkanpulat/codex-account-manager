import string

from codex_account_manager.domain.states import GoalState, HandoffReason
from codex_account_manager.gui.i18n import (
    EN,
    TR,
    diagnostic_detail,
    diagnostic_name,
    language,
    set_language,
    state_label,
    tr,
)


def test_translation_placeholders_match_source():
    formatter = string.Formatter()

    def fields(text):
        return {field for _, field, _, _ in formatter.parse(text) if field is not None}

    for source, translation in TR.items():
        assert fields(source) == fields(translation), source


def test_language_switch_and_dynamic_messages():
    try:
        set_language("tr")
        assert tr("Accounts") == "Hesaplarım"
        assert tr("Switching to {alias}…", alias="İş") == "İş hesabına geçiliyor…"
        assert diagnostic_name("codex_version") == "Codex sürümü"
        assert tr("Desktop readiness timed out.") == "Codex Desktop belirtilen sürede hazır olmadı."
        for state in (*GoalState, *HandoffReason):
            assert state_label(state.value) != state.value
        assert "codex --version" in diagnostic_detail("codex_version", False, "Timeout")
        set_language("en")
        assert tr("Accounts") == "My accounts"
        set_language("unsupported")
        assert language() == "en"
    finally:
        set_language("en")


def test_improved_english_copy_has_turkish_equivalents():
    assert EN.keys() <= TR.keys()
