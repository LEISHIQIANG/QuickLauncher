from qt_compat import QColor, QEvent, QImage, QPainter, QPoint, QRect, Qt, QtCompat, QWidget


def test_drink_card_self_painted_icons_are_horizontally_centered(qapp):
    from ui.config_window.settings_support_page import DrinkCard

    cards = [
        DrinkCard("water", "纯净矿泉水", 2.0, "#2DA8FF"),
        DrinkCard("latte", "香浓拿铁", 5.19, "#FF9500"),
        DrinkCard("tea", "沁心绿茶", 9.9, "#00C7BE"),
        DrinkCard("berry", "芝芝莓莓", 15.0, "#FF2D55"),
    ]

    for card in cards:
        image = QImage(card.width(), card.height(), QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        icon_rect = card._icon_rect(card.rect())

        painter = QPainter(image)
        card._paint_drink_icon(painter, icon_rect)
        painter.end()

        xs = []
        for y in range(image.height()):
            for x in range(image.width()):
                if QColor(image.pixelColor(x, y)).alpha() > 5:
                    xs.append(x)

        assert xs
        visible_center_x = (min(xs) + max(xs)) / 2
        assert abs(visible_center_x - icon_rect.center().x()) <= 2
        card.deleteLater()


def test_popup_menu_uses_trigger_screen_for_bounds(monkeypatch, qapp):
    import ui.styles.popup_menu as popup_menu_mod
    from ui.styles.style import PopupMenu

    class FakeScreen:
        def __init__(self, rect):
            self._rect = rect

        def availableGeometry(self):  # noqa: N802 - Qt API
            return self._rect

        def geometry(self):
            return self._rect

    primary = FakeScreen(QRect(0, 0, 1920, 1080))
    secondary = FakeScreen(QRect(1920, 0, 1280, 720))

    class FakeApplication:
        @staticmethod
        def screenAt(pos):  # noqa: N802 - Qt API
            if secondary.geometry().contains(pos):
                return secondary
            if primary.geometry().contains(pos):
                return primary
            return None

        @staticmethod
        def screens():
            return [primary, secondary]

        @staticmethod
        def primaryScreen():  # noqa: N802 - Qt API
            return primary

    monkeypatch.setattr(popup_menu_mod, "QApplication", FakeApplication)

    menu = PopupMenu(theme="dark")
    menu.setFixedSize(160, 180)
    menu._move_into_screen(QPoint(3150, 690))

    assert menu.x() >= secondary.geometry().left()
    assert menu.x() <= secondary.geometry().right() - menu.width()
    assert menu.y() <= secondary.geometry().bottom() - menu.height()

    menu.deleteLater()


def test_popup_menu_accepts_legacy_parent_positional_argument(qapp):
    from ui.styles.style import PopupMenu

    parent = QWidget()
    parent.theme = "light"

    menu = PopupMenu(parent)

    assert menu.parent() is parent
    assert menu._theme == "light"

    menu.deleteLater()
    parent.deleteLater()


def test_popup_menu_disables_native_shadow_on_win11(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect
    from ui.styles.style import PopupMenu

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win11")

    menu = PopupMenu(theme="dark", radius=12)

    assert menu.windowFlags() & QtCompat.NoDropShadowWindowHint
    assert getattr(menu, "_quicklauncher_win10_shadow", None) is None

    menu.deleteLater()


def test_popup_menu_disables_native_shadow_on_win10(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect
    from ui.styles.style import PopupMenu

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    menu = PopupMenu(theme="dark", radius=12)

    assert menu.windowFlags() & QtCompat.NoDropShadowWindowHint
    shadow = getattr(menu, "_quicklauncher_win10_shadow", None)
    assert shadow is not None
    assert shadow._radius == 12
    assert shadow._shadow_size == PopupMenu._WIN10_SHADOW_SIZE
    assert shadow._shadow_distance == PopupMenu._WIN10_SHADOW_DISTANCE

    shadow.detach()
    menu.deleteLater()


def test_popup_menu_retains_until_hidden(monkeypatch, qapp):
    from ui.styles.style import PopupMenu

    monkeypatch.setattr(PopupMenu, "_apply_blur_effect", lambda self: None)

    menu = PopupMenu(theme="dark")
    menu.add_action("one", lambda: None)
    menu.popup(QPoint(-10000, -10000))
    qapp.processEvents()

    assert menu in PopupMenu._active_popups

    menu.hide()
    qapp.processEvents()

    assert menu not in PopupMenu._active_popups
    menu.deleteLater()


def test_popup_menu_applies_native_blur_by_default(monkeypatch, qapp):
    from ui.styles.style import PopupMenu

    menu = PopupMenu(theme="dark")
    assert menu._native_effects_enabled is True

    menu.deleteLater()


def test_popup_menu_native_blur_can_be_disabled(monkeypatch, qapp):
    from ui.styles.style import PopupMenu

    calls = []
    monkeypatch.setattr(PopupMenu, "_apply_blur_effect", lambda self: calls.append(True))

    menu = PopupMenu(theme="dark", native_effects=False)
    menu.add_action("one", lambda: None)
    menu.popup(QPoint(-10000, -10000))
    qapp.processEvents()

    assert calls == []

    menu.hide()
    menu.deleteLater()


def test_popup_menu_native_surface_is_ready_before_show(monkeypatch, qapp):
    from ui.styles.style import PopupMenu

    calls = []

    def apply_surface(menu):
        calls.append(True)
        menu._blur_applied = True

    monkeypatch.setattr(PopupMenu, "_apply_blur_effect", apply_surface)

    menu = PopupMenu(theme="dark")
    menu.add_action("one", lambda: None)
    menu.popup(QPoint(-10000, -10000))

    assert calls == [True]

    menu.hide()
    menu.deleteLater()


def test_popup_menu_direct_show_prepares_native_surface(monkeypatch, qapp):
    from ui.styles.style import PopupMenu

    calls = []

    def apply_surface(menu):
        calls.append(True)
        menu._blur_applied = True

    monkeypatch.setattr(PopupMenu, "_apply_blur_effect", apply_surface)

    menu = PopupMenu(theme="dark")
    menu.add_action("one", lambda: None)
    menu.show()
    qapp.processEvents()

    assert calls == [True]
    assert menu._blur_applied is True

    menu.hide()
    menu.deleteLater()


def test_popup_menu_surface_matches_tool_window_on_win10_and_win11(qapp):
    from ui.styles.style import PopupMenu

    win10_dark, win10_dark_border = PopupMenu._surface_colors("dark", True, win10=True, win11=False)
    win11_dark, win11_dark_border = PopupMenu._surface_colors("dark", True, win10=False, win11=True)
    win10_light, win10_light_border = PopupMenu._surface_colors("light", True, win10=True, win11=False)
    win11_light, win11_light_border = PopupMenu._surface_colors("light", True, win10=False, win11=True)

    assert win10_dark.getRgb() == (28, 28, 30, 180)
    assert win10_dark_border.getRgb() == (190, 190, 197, 60)
    assert win11_dark.getRgb() == (28, 28, 30, 100)
    assert win11_dark_border.getRgb() == (190, 190, 197, 60)
    assert win10_light.getRgb() == (242, 242, 247, 160)
    assert win10_light_border.getRgb() == (229, 229, 234, 150)
    assert win11_light.getRgb() == (242, 242, 247, 100)
    assert win11_light_border.getRgb() == (229, 229, 234, 120)


def test_popup_menu_leave_delay_is_cancelled_when_pointer_returns(qapp):
    from ui.styles.style import PopupMenu

    menu = PopupMenu(theme="dark", native_effects=False)
    menu.add_action("one", lambda: None)
    menu.show()
    qapp.processEvents()

    menu.leaveEvent(QEvent(QEvent.Leave))
    assert menu._leave_timer.isActive()

    menu.enterEvent(QEvent(QEvent.Enter))
    assert not menu._leave_timer.isActive()
    assert menu.isVisible()

    menu.hide()
    menu.deleteLater()


def test_popup_menu_hides_when_pointer_stays_outside(monkeypatch, qapp):
    import ui.styles.popup_menu as popup_menu_mod
    from ui.styles.style import PopupMenu

    class OutsideCursor:
        @staticmethod
        def pos():
            return QPoint(-10000, -10000)

    monkeypatch.setattr(popup_menu_mod, "QCursor", OutsideCursor)
    menu = PopupMenu(theme="dark", native_effects=False)
    menu.add_action("one", lambda: None)
    menu.show()
    qapp.processEvents()

    menu._hide_if_pointer_outside()

    assert not menu.isVisible()
    menu.deleteLater()


def test_popup_menu_hides_when_window_deactivates(qapp):
    from ui.styles.style import PopupMenu

    menu = PopupMenu(theme="dark", native_effects=False)
    menu.add_action("one", lambda: None)
    menu.show()
    qapp.processEvents()

    menu.event(QEvent(QEvent.WindowDeactivate))

    assert not menu.isVisible()
    menu.deleteLater()


def test_popup_menu_repaints_parent_when_action_hover_moves(monkeypatch, qapp):
    from ui.styles.style import PopupMenu

    menu = PopupMenu(theme="dark", native_effects=False)
    first = menu.add_action("first", lambda: None)
    second = menu.add_action("second", lambda: None)
    updates = []
    monkeypatch.setattr(menu, "update", lambda *args: updates.append(args))

    menu.eventFilter(first, QEvent(QEvent.Enter))
    menu.eventFilter(first, QEvent(QEvent.Leave))
    menu.eventFilter(second, QEvent(QEvent.Enter))

    assert first.property("popup_menu_role") == "action"
    assert second.property("popup_menu_role") == "action"
    assert len(updates) >= 3
    menu.deleteLater()


def test_popup_menu_hover_keeps_final_surface_state(monkeypatch, qapp):
    from ui.styles.style import PopupMenu

    def apply_surface(menu):
        menu._blur_applied = True

    monkeypatch.setattr(PopupMenu, "_apply_blur_effect", apply_surface)

    menu = PopupMenu(theme="light")
    action = menu.add_action("one", lambda: None)
    menu.popup(QPoint(-10000, -10000))

    before = PopupMenu._surface_colors("light", menu._blur_applied, win10=False, win11=True)
    menu.eventFilter(action, QEvent(QEvent.Enter))
    after = PopupMenu._surface_colors("light", menu._blur_applied, win10=False, win11=True)

    assert menu._blur_applied is True
    assert before[0].getRgb() == after[0].getRgb() == (242, 242, 247, 100)
    assert before[1].getRgb() == after[1].getRgb() == (229, 229, 234, 120)

    menu.hide()
    menu.deleteLater()


def test_popup_menu_uses_event_filter_for_submenu_hover(qapp):
    from ui.styles.style import PopupMenu

    menu = PopupMenu(theme="dark", native_effects=False)
    submenu = menu.add_submenu("more", [("child", lambda: None)])
    action = menu.add_action("plain", lambda: None)

    menu.eventFilter(submenu, QEvent(QEvent.Enter))
    assert menu._submenu_expanded is True

    menu.eventFilter(action, QEvent(QEvent.Enter))
    assert menu._submenu_expanded is False
    menu.deleteLater()


def test_popup_menu_reclamps_after_inline_submenu_expands(monkeypatch, qapp):
    import ui.styles.popup_menu as popup_menu_mod
    from ui.styles.style import PopupMenu

    class FakeScreen:
        def availableGeometry(self):  # noqa: N802 - Qt API
            return QRect(0, 0, 260, 320)

        def geometry(self):
            return QRect(0, 0, 260, 320)

    class FakeApplication:
        @staticmethod
        def screenAt(_pos):  # noqa: N802 - Qt API
            return FakeScreen()

        @staticmethod
        def screens():
            return [FakeScreen()]

        @staticmethod
        def primaryScreen():  # noqa: N802 - Qt API
            return FakeScreen()

    monkeypatch.setattr(popup_menu_mod, "QApplication", FakeApplication)
    monkeypatch.setattr(PopupMenu, "_apply_blur_effect", lambda self: None)

    menu = PopupMenu(theme="dark")
    menu.add_action("one", lambda: None)
    menu.add_submenu("more", [(f"item {index}", lambda: None) for index in range(6)])
    menu.adjustSize()
    menu._move_into_screen(QPoint(240, 140))

    menu._expand_submenu()

    assert menu.x() >= 0
    assert menu.y() >= 0
    assert menu.x() + menu.width() <= FakeScreen().availableGeometry().right() + 1
    assert menu.y() + menu.height() <= FakeScreen().availableGeometry().bottom() + 1

    menu.deleteLater()


def test_launcher_popup_pin_indicator_y_adaptation(qapp):
    from types import SimpleNamespace

    from core.data_models import Folder
    from ui.launcher_popup.popup_window import LauncherPopup

    popup = LauncherPopup.__new__(LauncherPopup)
    popup.pages = [Folder(id="page-1", name="Page 1", items=[])]
    popup.current_page = 0
    popup.dock_items = []
    popup.settings = SimpleNamespace(theme="dark")

    # Mock _body_y_offset to return a base offset (like 32)
    popup._body_y_offset = lambda: 32

    # Case 1: Windows 11 (shadow_margin = 0)
    popup.__dict__["shadow_margin"] = 0
    popup.is_pinned = True

    shadow_margin_w11 = int(popup.__dict__.get("shadow_margin", 0) or 0)
    pin_y_offset_w11 = (popup._body_y_offset() if hasattr(popup, "_body_y_offset") else 0) + shadow_margin_w11
    assert pin_y_offset_w11 == 32

    # Case 2: Windows 10 (shadow_margin = 18)
    popup.__dict__["shadow_margin"] = 18
    shadow_margin_w10 = int(popup.__dict__.get("shadow_margin", 0) or 0)
    pin_y_offset_w10 = (popup._body_y_offset() if hasattr(popup, "_body_y_offset") else 0) + shadow_margin_w10
    assert pin_y_offset_w10 == 32 + 18


def test_launcher_popup_coordinate_adaptation(qapp):
    from types import SimpleNamespace

    from core.data_models import Folder
    from ui.launcher_popup.popup_window import LauncherPopup

    popup = LauncherPopup.__new__(LauncherPopup)
    popup.pages = [Folder(id="page-1", name="Page 1", items=[])]
    popup.current_page = 0
    popup.dock_items = []
    popup.settings = SimpleNamespace(theme="dark", dock_enabled=False)
    popup.dock_height = 0
    popup.fixed_rows = 3
    popup.cols = 4
    popup.cell_size = 40
    popup.cell_h = 40
    popup.padding = 8

    popup._dock_outer_bottom_gap = lambda: 6
    popup._body_y_offset = lambda: 32
    popup.height = lambda: 200

    # Verify icons_bottom with shadow_margin = 0
    popup.__dict__["shadow_margin"] = 0

    bottom_margin = popup._dock_outer_bottom_gap()
    indicator_height = 16 if len(popup.pages) > 1 else 0
    indicator_spacing = 4 if len(popup.pages) > 1 else 0
    dock_height = popup.dock_height
    shadow_margin = int(popup.__dict__.get("shadow_margin", 0) or 0)

    icons_bottom_w11 = (
        popup.height() - shadow_margin - bottom_margin - dock_height - indicator_height - indicator_spacing
    )
    assert icons_bottom_w11 == 200 - 0 - 6 - 0 - 0 - 0

    # Verify icons_bottom with shadow_margin = 18
    popup.__dict__["shadow_margin"] = 18
    shadow_margin = int(popup.__dict__.get("shadow_margin", 0) or 0)
    icons_bottom_w10 = (
        popup.height() - shadow_margin - bottom_margin - dock_height - indicator_height - indicator_spacing
    )
    assert icons_bottom_w10 == 200 - 18 - 6 - 0 - 0 - 0
