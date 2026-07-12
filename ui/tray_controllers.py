"""Explicit controller composition for tray behavior."""

from __future__ import annotations

from typing import Any

from ui.tray_mixins import HooksMixin, PopupMixin, SleepMixin, StartupMixin, UpdateMixin, WindowsMixin
from ui.tray_mixins.menu_mixin import TrayAppMenuMixin
from ui.tray_mixins.shutdown_mixin import TrayAppShutdownMixin


class TrayController:
    """Controller base that delegates state to its owning TrayApp."""

    def __init__(self, owner: Any) -> None:
        object.__setattr__(self, "_owner", owner)

    @property
    def owner(self) -> Any:
        return object.__getattribute__(self, "_owner")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.owner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_owner":
            object.__setattr__(self, name, value)
        else:
            setattr(self.owner, name, value)

    def start(self) -> None:
        """Start resources owned directly by this controller."""

    def stop(self) -> None:
        """Idempotently stop resources owned directly by this controller."""


class MenuController(TrayAppMenuMixin, TrayController):
    pass


class UpdateController(UpdateMixin, TrayController):
    pass


class HooksController(HooksMixin, TrayController):
    pass


class SleepController(SleepMixin, TrayController):
    pass


class PopupController(PopupMixin, TrayController):
    pass


class StartupController(StartupMixin, TrayController):
    pass


class WindowsController(WindowsMixin, TrayController):
    pass


class ShutdownController(TrayAppShutdownMixin, TrayController):
    def stop(self) -> None:
        self._shutdown_runtime_components()


class TrayControllerSet:
    """Own and resolve all TrayApp controllers in deterministic order."""

    def __init__(self, owner: Any) -> None:
        self._controllers: tuple[TrayController, ...] = (
            MenuController(owner),
            UpdateController(owner),
            HooksController(owner),
            SleepController(owner),
            PopupController(owner),
            StartupController(owner),
            WindowsController(owner),
            ShutdownController(owner),
        )
        self._started = False
        self._stopped = False

    def resolve(self, name: str) -> Any:
        for controller in self._controllers:
            descriptor = getattr(type(controller), name, None)
            if descriptor is not None:
                getter = getattr(descriptor, "__get__", None)
                return getter(controller, type(controller)) if getter is not None else descriptor
        raise AttributeError(name)

    def start(self) -> None:
        if self._started or self._stopped:
            return
        self._started = True
        for controller in self._controllers:
            controller.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        for controller in reversed(self._controllers):
            controller.stop()


__all__ = ["TrayController", "TrayControllerSet"]
