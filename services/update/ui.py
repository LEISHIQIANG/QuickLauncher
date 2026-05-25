"""Update notification UI helpers."""

from core.i18n import tr
from services.update.config import UpdateInfo
from ui.styles.themed_messagebox import ThemedMessageBox


class UpdateNotification:
    @staticmethod
    def show_update_available(update_info: UpdateInfo, on_download=None, on_skip=None, parent=None):
        changelog = update_info.changelog_zh or update_info.changelog_en or tr("暂无更新说明。")
        size_mb = update_info.file_size / 1024 / 1024
        mandatory_text = tr("\n\n这是强制更新，不能跳过。") if update_info.mandatory else ""
        msg = tr(
            "新版本 {version} 可用\n\n{changelog}\n\n文件大小: {size_mb:.1f} MB{mandatory_text}",
            version=update_info.version,
            changelog=changelog,
            size_mb=size_mb,
            mandatory_text=mandatory_text,
        )
        result = ThemedMessageBox.question(
            parent,
            tr("发现更新"),
            tr("{message}\n\n是否立即下载更新？", message=msg),
            buttons=ThemedMessageBox.Yes | ThemedMessageBox.No,
        )
        if result == ThemedMessageBox.Yes and on_download:
            on_download()
        elif not update_info.mandatory and on_skip:
            on_skip()

    @staticmethod
    def show_download_progress_text(current: int, total: int) -> str:
        pct = current / total * 100 if total > 0 else 0
        mb_done = current / 1024 / 1024
        mb_total = total / 1024 / 1024
        return tr("正在下载更新... {done:.1f}/{total:.1f} MB ({pct:.0f}%)", done=mb_done, total=mb_total, pct=pct)

    @staticmethod
    def show_download_failed(error: str, parent=None):
        ThemedMessageBox.critical(parent, tr("更新失败"), tr("更新失败:\n{error}", error=error))

    @staticmethod
    def show_download_finished(on_install=None, parent=None):
        result = ThemedMessageBox.question(
            parent,
            tr("下载完成"),
            tr("新版本已下载完成，是否立即安装并重启？"),
            buttons=ThemedMessageBox.Yes | ThemedMessageBox.No,
        )
        if result == ThemedMessageBox.Yes and on_install:
            on_install()

    @staticmethod
    def show_up_to_date(parent=None):
        ThemedMessageBox.information(parent, tr("检查更新"), tr("当前已经是最新版本。"))

    @staticmethod
    def show_check_failed(error: str, parent=None):
        ThemedMessageBox.warning(parent, tr("检查更新失败"), tr("无法检查更新:\n{error}", error=error))
