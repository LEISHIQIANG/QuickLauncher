from types import SimpleNamespace

from qt_compat import QPoint, QtCompat, QWidget


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
    assert shadow._sync_timer.interval() == 200

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


def test_win10_shadow_uses_configurable_size_and_distance(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    target = QWidget()
    target.setGeometry(-10000, -10000, 180, 120)
    assert window_effect.install_win10_window_shadow(target, 8, shadow_size=24, shadow_distance=7)
    target.show()
    qapp.processEvents()

    shadow = getattr(target, "_quicklauncher_win10_shadow", None)
    assert shadow is not None
    shadow.sync()

    size_px, distance_px, margin, bottom_extra = shadow._shadow_metrics(target)
    assert shadow._shadow_size == 24
    assert shadow._shadow_distance == 7
    assert size_px >= 24
    assert distance_px >= 7
    assert margin > size_px
    assert bottom_extra == distance_px

    assert window_effect.install_win10_window_shadow(target, 14, shadow_size=32, shadow_distance=11)
    assert shadow._radius == 14
    assert shadow._shadow_size == 32
    assert shadow._shadow_distance == 11

    assert window_effect.install_win10_window_shadow(target, 14, shadow_size=0, shadow_distance=0)
    assert getattr(target, "_quicklauncher_win10_shadow", None) is shadow
    assert shadow._shadow_size is None
    assert shadow._shadow_distance is None

    target.close()
    target.deleteLater()
    qapp.processEvents()


def test_win10_shadow_global_defaults_apply_to_shared_shadow(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")
    monkeypatch.setattr(window_effect, "_win10_shadow_config_size", None)
    monkeypatch.setattr(window_effect, "_win10_shadow_config_distance", None)

    assert window_effect.configure_win10_window_shadow(shadow_size=28, shadow_distance=9)

    target = QWidget()
    target.setGeometry(-10000, -10000, 180, 120)
    assert window_effect.install_win10_window_shadow(target, 8)
    target.show()
    qapp.processEvents()

    shadow = getattr(target, "_quicklauncher_win10_shadow", None)
    assert shadow is not None
    shadow.sync()

    size_px, distance_px, _margin, bottom_extra = shadow._shadow_metrics(target)
    assert shadow._shadow_size is None
    assert shadow._shadow_distance is None
    assert size_px >= 28
    assert distance_px >= 9
    assert bottom_extra == distance_px

    assert window_effect.configure_win10_window_shadow(shadow_size=0, shadow_distance=0)
    size_px, distance_px, _margin, bottom_extra = shadow._shadow_metrics(target)
    assert 0 < size_px < 28
    assert 0 < distance_px < 9
    assert bottom_extra == distance_px

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
    assert shadow._shadow_size == PopupMenu._WIN10_SHADOW_SIZE
    assert shadow._shadow_distance == PopupMenu._WIN10_SHADOW_DISTANCE
    assert menu.windowFlags() & QtCompat.NoDropShadowWindowHint

    shadow.detach()
    menu.close()
    menu.deleteLater()
    qapp.processEvents()


def test_popup_menu_win10_shadow_is_ready_when_popup_returns(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect
    from ui.styles.style import PopupMenu

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    menu = PopupMenu(theme="dark", radius=12)
    menu.add_action("Open", lambda: None)
    menu.popup(QPoint(-10000, -10000))

    shadow = getattr(menu, "_quicklauncher_win10_shadow", None)
    assert menu._blur_applied is True
    assert shadow is not None
    assert shadow.widget is not None
    assert shadow.widget.isVisible()
    assert shadow._synchronous is True

    shadow.detach()
    menu.close()
    menu.deleteLater()
    qapp.processEvents()


def test_popup_menu_win10_shadow_follows_geometry_and_opacity_synchronously(monkeypatch, qapp):
    import ui.utils.window_effect as window_effect
    from ui.styles.style import PopupMenu

    monkeypatch.setattr(window_effect, "_windows_version_cache", "win10")

    menu = PopupMenu(theme="dark", radius=12)
    menu.add_action("Open", lambda: None)
    menu.popup(QPoint(-10000, -10000))

    shadow = getattr(menu, "_quicklauncher_win10_shadow", None)
    assert shadow is not None
    assert shadow.widget is not None

    margin, bottom_extra = shadow._shadow_margins(menu)
    menu.move(-9800, -9700)
    frame = menu.frameGeometry()
    shadow_geo = shadow.widget.geometry()
    assert shadow_geo.x() == frame.x() - margin
    assert shadow_geo.y() == frame.y() - margin
    assert shadow_geo.width() == frame.width() + margin * 2
    assert shadow_geo.height() == frame.height() + margin * 2 + bottom_extra

    menu.setWindowOpacity(0.4)
    assert abs(shadow.widget.windowOpacity() - 0.4) < 0.01

    shadow.detach()
    menu.close()
    menu.deleteLater()
    qapp.processEvents()


def test_launcher_popup_win10_internal_shadow_skips_companion_when_effect_state_is_cached(monkeypatch, qapp):
    import ui.launcher_popup.popup_window_effect as popup_effect

    class DummyWindowEffect:
        def set_dwm_blur_behind(self, *args, **kwargs):
            return True

        def set_acrylic(self, *args, **kwargs):
            return True

        def set_round_corners(self, *args, **kwargs):
            return True

        def clear_window_region(self, *args, **kwargs):
            return True

    class PopupHarness(popup_effect.PopupWindowEffectMixin, QWidget):
        def __init__(self):
            super().__init__()
            self.settings = SimpleNamespace(
                bg_mode="theme",
                bg_blur_radius=0,
                corner_radius=11,
                shadow_size=23,
                shadow_distance=6,
                theme="dark",
            )
            self.window_effect = DummyWindowEffect()

    monkeypatch.setattr(popup_effect, "is_win10", lambda: True)
    monkeypatch.setattr(popup_effect, "is_win11", lambda: False)

    install_calls = []
    remove_calls = []

    def fake_install(widget, radius, shadow_size=None, shadow_distance=None):
        install_calls.append((widget, radius, shadow_size, shadow_distance))
        return True

    monkeypatch.setattr(popup_effect, "install_win10_window_shadow", fake_install)
    monkeypatch.setattr(popup_effect, "remove_win10_window_shadow", lambda widget: remove_calls.append(widget))

    popup = PopupHarness()
    popup.resize(180, 120)
    popup.winId()
    popup._last_effect_state = popup._snapshot_effect_state()

    popup._update_window_effect()

    assert install_calls == []
    assert remove_calls == [popup]

    popup.close()
    popup.deleteLater()
    qapp.processEvents()
