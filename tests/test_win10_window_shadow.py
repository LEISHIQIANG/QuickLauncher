from qt_compat import QWidget


def test_win10_shadow_installs_without_hidden_window_delete_crash(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    target = QWidget()
    assert window_effect.install_win10_window_shadow(target, 8)

    shadow = getattr(target, "_quicklauncher_win10_shadow", None)
    assert shadow is not None
    assert shadow.widget is None

    target.deleteLater()
    qapp.processEvents()


def test_win10_shadow_is_removed_when_platform_is_not_win10(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    target = QWidget()
    assert window_effect.install_win10_window_shadow(target, 8)
    assert getattr(target, "_quicklauncher_win10_shadow", None) is not None

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win11")

    assert not window_effect.install_win10_window_shadow(target, 8)
    assert getattr(target, "_quicklauncher_win10_shadow", None) is None

    target.deleteLater()
    qapp.processEvents()


def test_win10_shadow_creates_companion_for_visible_rounded_window(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    target = QWidget()
    target.setGeometry(-10000, -10000, 180, 120)
    assert window_effect.install_win10_window_shadow(target, 8)

    target.show()
    qapp.processEvents()

    shadow = getattr(target, "_quicklauncher_win10_shadow", None)
    assert shadow is not None
    shadow.sync()

    assert shadow.widget is not None
    assert shadow._radius == 8
    assert shadow._sync_timer.interval() == 50

    margin, bottom_extra = shadow._shadow_margins(target)
    assert bottom_extra <= max(1, int(round(margin * 0.15)))

    update_calls = []
    z_calls = []
    original_update = shadow.widget.update
    original_sync_z = shadow._sync_z_order
    shadow.widget.update = lambda *args: update_calls.append(args)
    shadow._sync_z_order = lambda *args: z_calls.append(args)
    shadow.sync()
    shadow.sync()
    assert update_calls == []
    assert len(z_calls) == 2

    target.move(-9900, -9900)
    qapp.processEvents()
    margin, bottom_extra = shadow._shadow_margins(target)
    frame = target.frameGeometry()
    shadow_geo = shadow.widget.geometry()
    assert shadow_geo.x() <= frame.x()
    assert shadow_geo.y() <= frame.y()
    assert shadow_geo.width() == frame.width() + margin * 2
    assert shadow_geo.height() == frame.height() + margin * 2 + bottom_extra
    assert update_calls == []
    shadow.widget.update = original_update
    shadow._sync_z_order = original_sync_z

    assert window_effect.install_win10_window_shadow(target, 14)
    assert shadow._radius == 14

    shadow.detach()
    target.close()
    target.deleteLater()
    qapp.processEvents()


def test_win10_shadow_resyncs_z_order_after_raise_and_activate(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    target = QWidget()
    target.setGeometry(-10000, -10000, 180, 120)
    assert window_effect.install_win10_window_shadow(target, 8)
    target.show()
    qapp.processEvents()

    shadow = getattr(target, "_quicklauncher_win10_shadow", None)
    assert shadow is not None
    shadow.sync()

    z_calls = []
    original_sync_z = shadow._sync_z_order
    shadow._sync_z_order = lambda *args: z_calls.append(args)

    target.raise_()
    target.activateWindow()
    qapp.processEvents()

    assert len(z_calls) >= 2

    shadow._sync_z_order = original_sync_z
    shadow.detach()
    target.close()
    target.deleteLater()
    qapp.processEvents()


def test_popup_menu_uses_win10_shadow_with_menu_radius(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect
    from ui.styles.style import PopupMenu

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    menu = PopupMenu(theme="dark", radius=12)
    shadow = getattr(menu, "_quicklauncher_win10_shadow", None)
    assert shadow is not None

    menu.setGeometry(-10000, -10000, 160, 80)
    menu.show()
    qapp.processEvents()
    menu._apply_blur_effect()

    assert shadow._radius == 12

    shadow.detach()
    menu.close()
    menu.deleteLater()
    qapp.processEvents()
