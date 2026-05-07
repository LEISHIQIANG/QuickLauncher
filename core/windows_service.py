"""
Windows 服务实现

使用 pywin32 创建 Windows 服务，实现开机即启动（最快方式）
服务只负责启动主程序，不处理 GUI
"""

import sys
import os
import win32serviceutil
import win32service
import win32event
import servicemanager
import subprocess
import time
import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "QuickLauncherService"
SERVICE_DISPLAY_NAME = "QuickLauncher 快速启动服务"
SERVICE_DESCRIPTION = "QuickLauncher 开机自启服务，负责在用户登录时快速启动主程序"


def _get_app_exe_path() -> str:
    """获取 QuickLauncher.exe 的路径（兼容 Nuitka）"""
    # 优先用 sys.argv[0]
    if sys.argv and sys.argv[0].lower().endswith('.exe'):
        candidate = os.path.abspath(sys.argv[0])
        if os.path.isfile(candidate):
            return candidate

    # 从 sys.executable 所在目录查找 QuickLauncher.exe
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(exe_dir, 'QuickLauncher.exe')
    if os.path.isfile(candidate):
        return candidate

    return os.path.abspath(sys.executable)


class QuickLauncherService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True
        self.main_process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.is_running = False

        # 停止主程序
        if self.main_process:
            try:
                self.main_process.terminate()
            except:
                pass

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def main(self):
        """服务主循环"""
        import winreg

        # 优先从服务参数获取 exe 路径
        exe_path = None
        try:
            # 从服务注册表读取启动参数
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"SYSTEM\\CurrentControlSet\\Services\\{SERVICE_NAME}", 0, winreg.KEY_READ)
            image_path, _ = winreg.QueryValueEx(key, "ImagePath")
            winreg.CloseKey(key)

            # 解析出 QuickLauncher.exe 路径（从 ImagePath 中提取）
            if "QuickLauncher.exe" in image_path:
                import re
                match = re.search(r'([A-Za-z]:[^"]+QuickLauncher\.exe)', image_path)
                if match:
                    exe_path = match.group(1)
        except:
            pass

        # 降级方案1：从安装注册表获取
        if not exe_path:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1", 0, winreg.KEY_READ)
                install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                winreg.CloseKey(key)
                exe_path = os.path.join(install_path, "QuickLauncher.exe")
            except:
                pass

        # 降级方案2：使用 exe 同目录
        if not exe_path:
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            exe_path = os.path.join(exe_dir, "QuickLauncher.exe")

        if not os.path.exists(exe_path):
            servicemanager.LogErrorMsg(f"找不到主程序: {exe_path}")
            return

        # 等待用户登录
        for _ in range(60):
            if not self.is_running:
                return
            try:
                result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq explorer.exe"],
                                      capture_output=True, text=True, timeout=1)
                if "explorer.exe" in result.stdout:
                    time.sleep(2)  # 等待桌面加载
                    break
            except:
                pass
            time.sleep(1)

        # 启动主程序（以当前登录用户身份）
        try:
            subprocess.Popen([exe_path], creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS)
            servicemanager.LogInfoMsg(f"主程序已启动: {exe_path}")
        except Exception as e:
            servicemanager.LogErrorMsg(f"启动失败: {e}")

        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


def install_service():
    """安装服务（兼容 Nuitka 打包，不依赖 pythonservice.exe）"""
    try:
        import win32service

        exe_path = _get_app_exe_path()
        if not os.path.isfile(exe_path):
            return False, f"找不到主程序: {exe_path}"

        bin_path = f'"{exe_path}" --service-mode'

        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
        try:
            hs = win32service.CreateService(
                scm,
                SERVICE_NAME,
                SERVICE_DISPLAY_NAME,
                win32service.SERVICE_ALL_ACCESS,
                win32service.SERVICE_WIN32_OWN_PROCESS,
                win32service.SERVICE_AUTO_START,
                win32service.SERVICE_ERROR_NORMAL,
                bin_path,
                None, 0, None, None, None
            )
            try:
                win32service.ChangeServiceConfig2(
                    hs, win32service.SERVICE_CONFIG_DESCRIPTION,
                    SERVICE_DESCRIPTION
                )
            except Exception:
                pass
            win32service.CloseServiceHandle(hs)
        finally:
            win32service.CloseServiceHandle(scm)

        return True, "服务安装成功"
    except Exception as e:
        return False, f"服务安装失败: {e}"


def uninstall_service():
    """卸载服务"""
    try:
        win32serviceutil.RemoveService(SERVICE_NAME)
        return True, "服务卸载成功"
    except Exception as e:
        return False, f"服务卸载失败: {e}"


def start_service():
    """启动服务"""
    try:
        # 检查服务是否已在运行
        if is_service_running():
            return True, "服务已在运行"

        win32serviceutil.StartService(SERVICE_NAME)

        # 等待服务启动（最多5秒）
        import time
        for _ in range(10):
            time.sleep(0.5)
            if is_service_running():
                return True, "服务启动成功"

        return False, "服务启动超时"
    except Exception as e:
        return False, f"服务启动失败: {e}"


def stop_service():
    """停止服务"""
    try:
        # 检查服务是否在运行
        if not is_service_running():
            return True, "服务未运行"

        win32serviceutil.StopService(SERVICE_NAME)

        # 等待服务停止（最多5秒）
        import time
        for _ in range(10):
            time.sleep(0.5)
            if not is_service_running():
                return True, "服务停止成功"

        return False, "服务停止超时"
    except Exception as e:
        return False, f"服务停止失败: {e}"


def is_service_installed():
    """检查服务是否已安装"""
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return True
    except:
        return False


def is_service_running():
    """检查服务是否正在运行"""
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
        return status == win32service.SERVICE_RUNNING
    except:
        return False


if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(QuickLauncherService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(QuickLauncherService)
