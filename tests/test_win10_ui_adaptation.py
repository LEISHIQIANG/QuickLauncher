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
    import ui.styles.style as style_mod
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

    monkeypatch.setattr(style_mod, "QApplication", FakeApplication)

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


def test_popup_menu_native_blur_is_delayed(monkeypatch, qapp):
    import ui.styles.style as style_mod
    from ui.styles.style import PopupMenu

    calls = []
    scheduled = []
    monkeypatch.setattr(PopupMenu, "_apply_blur_effect", lambda self: calls.append(True))
    monkeypatch.setattr(style_mod.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))

    menu = PopupMenu(theme="dark")
    menu.add_action("one", lambda: None)
    menu.popup(QPoint(-10000, -10000))

    assert calls == []
    assert scheduled
    assert scheduled[0][0] == 40

    scheduled[0][1]()

    assert calls == [True]

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
    import ui.styles.style as style_mod
    from ui.styles.style import PopupMenu

    class OutsideCursor:
        @staticmethod
        def pos():
            return QPoint(-10000, -10000)

    monkeypatch.setattr(style_mod, "QCursor", OutsideCursor)
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
    import ui.styles.style as style_mod
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

    monkeypatch.setattr(style_mod, "QApplication", FakeApplication)
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
