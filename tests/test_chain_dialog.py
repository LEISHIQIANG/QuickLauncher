import pytest

from core.data_models import Folder, ShortcutItem, ShortcutType
from qt_compat import QWidget
from ui.config_window.base_dialog import BaseDialog
from ui.config_window.chain_dialog import ChainDialog
from ui.config_window.theme_helper import get_small_checkbox_stylesheet

pytestmark = pytest.mark.ui


class _Settings:
    theme = "dark"


class _DataManager:
    def __init__(self, items, folders=None):
        self.data = type("Data", (), {"folders": folders or [Folder(id="f", name="F", items=items)]})()

    def get_settings(self):
        return _Settings()


class _Parent(QWidget):
    def __init__(self, items, folders=None):
        super().__init__()
        self.data_manager = _DataManager(items, folders=folders)


def test_chain_dialog_is_base_dialog(qapp):
    """ChainDialog 应继承 BaseDialog，保持一致的对话框风格。"""
    first = ShortcutItem(id="one", name="One", type=ShortcutType.FILE)
    parent = _Parent([first])
    dialog = ChainDialog(parent)
    assert isinstance(dialog, BaseDialog)
    dialog.close()


def test_chain_dialog_includes_icon_repo_items(qapp):
    normal = ShortcutItem(id="normal", name="Normal", type=ShortcutType.FILE)
    repo_item = ShortcutItem(id="repo", name="Repo", type=ShortcutType.URL)
    parent = _Parent(
        [],
        folders=[
            Folder(id="f", name="F", items=[normal]),
            Folder(id="icon_repo", name="图标仓库", is_system=True, is_icon_repo=True, items=[repo_item]),
        ],
    )
    dialog = ChainDialog(parent)

    assert {item.id for item in dialog._available} == {"normal", "repo"}
    dialog.close()


def test_chain_dialog_add_remove_reorder_and_save(qapp):
    first = ShortcutItem(id="one", name="One", type=ShortcutType.FILE)
    second = ShortcutItem(id="two", name="Two", type=ShortcutType.URL)
    parent = _Parent([first, second])
    dialog = ChainDialog(parent)

    # 通过内部方法添加步骤
    dialog._add_step(first)
    dialog._add_step(second)
    assert len(dialog._steps) == 2

    # 上移第二步
    dialog._selected_index = 1
    dialog._move_step(-1)
    shortcut = dialog.get_shortcut()
    assert shortcut.type == ShortcutType.CHAIN
    assert [step["shortcut_id"] for step in shortcut.chain_steps] == ["two", "one"]

    # 修改第一步的设置
    dialog._selected_index = 0
    dialog._steps[0]["enabled"] = False
    dialog._steps[0]["stop_on_error"] = False
    dialog._steps[0]["delay_ms"] = 25
    shortcut = dialog.get_shortcut()
    assert shortcut.chain_steps[0]["enabled"] is False
    assert shortcut.chain_steps[0]["stop_on_error"] is False
    assert shortcut.chain_steps[0]["delay_ms"] == 25

    # 删除第一步
    dialog._selected_index = 0
    dialog._remove_step()
    assert len(dialog._steps) == 1


def test_chain_dialog_edits_existing_chain(qapp):
    target = ShortcutItem(id="target", name="Target", type=ShortcutType.FILE)
    chain = ShortcutItem(
        id="chain",
        name="Existing",
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "target", "enabled": True, "stop_on_error": True, "delay_ms": 10}],
    )
    parent = _Parent([target, chain])
    dialog = ChainDialog(parent, chain)

    updated = dialog.get_shortcut()

    assert updated.id == "chain"
    assert updated.name == "Existing"
    assert updated.chain_steps[0]["shortcut_id"] == "target"
    assert updated.chain_steps[0]["delay_ms"] == 10


def test_chain_dialog_risk_analysis(qapp):
    """风险分析应检测到管理员权限和不存在的引用。"""
    admin_item = ShortcutItem(id="admin", name="Admin", type=ShortcutType.COMMAND, run_as_admin=True)
    parent = _Parent([admin_item])
    dialog = ChainDialog(parent)
    dialog._add_step(admin_item)
    # 直接添加一个引用不存在快捷方式的步骤
    dialog._steps.append(
        {"id": "x", "shortcut_id": "nonexistent", "enabled": True, "stop_on_error": True, "delay_ms": 0}
    )
    risks = dialog._analyze_risks()
    assert any("管理员" in r for r in risks)
    assert any("不存在" in r for r in risks)


def test_chain_dialog_get_shortcut_normalizes(qapp):
    """get_shortcut 应对步骤进行规范化处理。"""
    item = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    parent = _Parent([item])
    dialog = ChainDialog(parent)
    dialog._steps = [
        {"shortcut_id": "a", "enabled": True, "stop_on_error": True, "delay_ms": 5},
        {"shortcut_id": "", "enabled": True, "stop_on_error": True, "delay_ms": 0},  # 空 id 应被过滤
    ]
    result = dialog.get_shortcut()
    assert result.type == ShortcutType.CHAIN
    assert len(result.chain_steps) == 1
    assert result.chain_steps[0]["shortcut_id"] == "a"


def test_chain_step_card_checkboxes_keep_card_local_style(qapp):
    item = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    parent = _Parent([item])
    dialog = ChainDialog(parent)
    dialog._add_step(item)

    card = dialog._find_card(0)

    assert card is not None
    expected_style = get_small_checkbox_stylesheet(dialog.theme)
    for style in (card.styleSheet(), card._stop_cb.styleSheet(), card._enabled_cb.styleSheet()):
        assert expected_style in style

    card.set_selected(True)
    assert expected_style in card.styleSheet()


def test_existing_chain_step_card_checkboxes_match_result_check_style_on_open(qapp):
    item = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    chain = ShortcutItem(
        id="chain",
        name="Chain",
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "a", "enabled": True, "stop_on_error": False, "delay_ms": 0}],
    )
    parent = _Parent([item, chain])
    dialog = ChainDialog(parent, chain)

    card = dialog._find_card(0)
    result_style = dialog._result_checks["medium"].styleSheet()

    assert card is not None
    assert card._stop_cb.styleSheet() == result_style
    assert card._enabled_cb.styleSheet() == result_style
    assert result_style in card.styleSheet()
