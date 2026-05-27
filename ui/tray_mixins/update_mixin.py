"""Update system methods for the tray application."""

import logging
import os

logger = logging.getLogger(__name__)


class UpdateMixin:
    """Update system methods for the tray application."""

    def _init_update_system(self, start_auto_check: bool = True):
        try:
            from services.update.checker import UpdateChecker
            from services.update.downloader import UpdateDownloader
            from services.update.installer import UpdateInstaller
            from services.update.session import mark_latest_session_first_start_confirmed

            self._update_checker = UpdateChecker()
            self._update_downloader = UpdateDownloader()
            self._update_installer = UpdateInstaller()

            self._update_checker.add_listener(lambda event, data=None: self._update_event_signal.emit(event, data))
            self._update_downloader.add_listener(lambda event, data=None: self._download_event_signal.emit(event, data))
            self._update_installer.add_listener(lambda event, data=None: self._install_event_signal.emit(event, data))

            if start_auto_check:
                self._update_checker.start_auto_check()
            try:
                update_root = os.path.join(
                    str(self.data_manager.app_dir),
                    "downloads",
                    self._update_checker._config.download_dir_name,
                )
                mark_latest_session_first_start_confirmed(update_root)
            except Exception:
                pass
            logger.info("Update system initialized")
        except Exception as e:
            logger.debug("Update system initialization failed: %s", e)

    def _check_update_now(self, parent=None):
        from services.update.ui import UpdateNotification

        self._update_dialog_parent = parent
        if self._update_checker is None:
            self._init_update_system(start_auto_check=False)
        if self._update_checker is None:
            UpdateNotification.show_check_failed("Update system is not initialized", parent=parent)
            return
        info = self._update_checker.check_now()
        if info and not info.has_update:
            UpdateNotification.show_up_to_date(parent=parent)

    def _on_update_event(self, event: str, data=None):
        from services.update.ui import UpdateNotification

        parent = getattr(self, "_update_dialog_parent", None)

        if event == "update_available":
            self._pending_update_info = data
            UpdateNotification.show_update_available(
                data,
                on_download=lambda: self._download_update(data),
                on_skip=lambda: self._skip_version(data.version),
                parent=parent,
            )
        elif event == "auto_download_requested":
            self._pending_update_info = data
            logger.info("Found update %s, starting automatic download", getattr(data, "version", ""))
            self._download_update(data)
        elif event == "update_skipped":
            logger.info("Skipped update %s", getattr(data, "version", ""))
        elif event == "check_failed":
            logger.debug("Update check failed: %s", data)
        elif event == "up_to_date":
            pass

    def _download_update(self, update_info):
        if not self._update_downloader:
            return
        target_dir = None
        try:
            target_dir = os.path.join(
                str(self.data_manager.app_dir),
                "downloads",
                self._update_checker._config.download_dir_name,
            )
        except Exception:
            pass
        self._update_downloader.download(
            update_info.download_url,
            target_dir=target_dir,
            expected_hash=update_info.file_hash,
            expected_size=getattr(update_info, "file_size", 0),
            max_bytes=getattr(self._update_checker._config, "max_download_bytes", 0) if self._update_checker else 0,
            allowed_hosts=getattr(self._update_checker._config, "allowed_download_hosts", None)
            if self._update_checker
            else None,
            version=getattr(update_info, "version", ""),
        )

    def _on_download_event(self, event: str, data=None):
        from services.update.ui import UpdateNotification

        parent = getattr(self, "_update_dialog_parent", None)

        if event == "progress":
            downloaded, total = data
            logger.info(UpdateNotification.show_download_progress_text(downloaded, total))
        elif event == "finished":
            self._pending_update_installer = data
            auto_install = (
                bool(getattr(self._update_checker._config, "auto_install", False)) if self._update_checker else False
            )
            if auto_install:
                self._install_update(data)
            else:
                UpdateNotification.show_download_finished(on_install=lambda: self._install_update(data), parent=parent)
        elif event == "failed":
            UpdateNotification.show_download_failed(data, parent=parent)
        elif event == "cancelled":
            logger.info("Update download was cancelled")

    def _install_update(self, installer_path: str):
        if self._update_installer:
            update_info = getattr(self, "_pending_update_info", None)
            trusted_dir = ""
            try:
                trusted_dir = os.path.join(
                    str(self.data_manager.app_dir),
                    "downloads",
                    self._update_checker._config.download_dir_name,
                )
            except Exception:
                pass
            self._update_installer.install(
                installer_path,
                expected_hash=getattr(update_info, "file_hash", "") if update_info else "",
                trusted_dir=trusted_dir,
                data_manager=getattr(self, "data_manager", None),
            )

    def _on_install_event(self, event: str, data=None):
        if event == "failed":
            from services.update.ui import UpdateNotification

            UpdateNotification.show_download_failed(data, parent=getattr(self, "_update_dialog_parent", None))

    def _skip_version(self, version: str):
        try:
            if self._update_checker:
                self._update_checker.skip_version(version)
        except Exception:
            pass
