"""更新通知 UI。"""

from ui.styles.themed_messagebox import ThemedMessageBox
from commercial.update.config import UpdateInfo


class UpdateNotification:

    @staticmethod
    def show_update_available(update_info: UpdateInfo,
                              on_download=None, on_skip=None):
        changelog = update_info.changelog_zh or update_info.changelog_en or ""
        size_mb = update_info.file_size / 1024 / 1024
        msg = (
            f"新版本 {update_info.version} 可用\n\n"
            f"{changelog}\n\n"
            f"文件大小: {size_mb:.1f} MB"
        )
        result = ThemedMessageBox.question(
            None, "发现更新", msg,
            buttons=["立即更新", "稍后提醒", "忽略此版本"],
            default_button=0,
        )
        if result == 0 and on_download:
            on_download()
        elif result == 2 and on_skip:
            on_skip()

    @staticmethod
    def show_download_progress_text(current: int, total: int) -> str:
        pct = current / total * 100 if total > 0 else 0
        mb_done = current / 1024 / 1024
        mb_total = total / 1024 / 1024
        return f"正在下载更新... {mb_done:.1f}/{mb_total:.1f} MB ({pct:.0f}%)"

    @staticmethod
    def show_download_failed(error: str):
        ThemedMessageBox.critical(None, "下载失败", f"更新下载失败:\n{error}")

    @staticmethod
    def show_download_finished(on_install=None):
        result = ThemedMessageBox.question(
            None, "下载完成", "新版本已下载完成，是否立即安装并重启？",
            buttons=["立即安装", "稍后安装"],
            default_button=0,
        )
        if result == 0 and on_install:
            on_install()

    @staticmethod
    def show_up_to_date():
        ThemedMessageBox.info(None, "检查更新", "当前已是最新版本")
