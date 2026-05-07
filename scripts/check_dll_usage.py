"""
检测 msvcp140.dll 被哪些进程占用
用于安装前提示用户关闭相关程序
"""

import ctypes
from ctypes import wintypes
import sys

# Windows API 常量
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = -1
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

# 结构体定义
class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260)
    ]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260)
    ]

def find_processes_using_dll(dll_name, target_path=None):
    """查找使用指定 DLL 的进程"""
    kernel32 = ctypes.windll.kernel32
    processes_using_dll = []

    # 创建进程快照
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return processes_using_dll

    try:
        pe32 = PROCESSENTRY32()
        pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)

        # 遍历进程
        if kernel32.Process32First(snapshot, ctypes.byref(pe32)):
            while True:
                pid = pe32.th32ProcessID
                process_name = pe32.szExeFile.decode('utf-8', errors='ignore')

                # 检查该进程是否加载了目标 DLL
                if check_process_has_dll(pid, dll_name, target_path):
                    processes_using_dll.append({
                        'pid': pid,
                        'name': process_name
                    })

                if not kernel32.Process32Next(snapshot, ctypes.byref(pe32)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)

    return processes_using_dll

def check_process_has_dll(pid, dll_name, target_path=None):
    """检查指定进程是否加载了目标 DLL"""
    kernel32 = ctypes.windll.kernel32

    # 创建模块快照
    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid
    )
    if snapshot == INVALID_HANDLE_VALUE:
        return False

    try:
        me32 = MODULEENTRY32()
        me32.dwSize = ctypes.sizeof(MODULEENTRY32)

        if kernel32.Module32First(snapshot, ctypes.byref(me32)):
            while True:
                module_name = me32.szModule.decode('utf-8', errors='ignore').lower()

                if dll_name.lower() in module_name:
                    if target_path:
                        module_path = me32.szExePath.decode('utf-8', errors='ignore').lower()
                        if target_path.lower() in module_path:
                            return True
                    else:
                        return True

                if not kernel32.Module32Next(snapshot, ctypes.byref(me32)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)

    return False

def main():
    """主函数"""
    import os
    import sys
    import io

    # 设置输出编码为 UTF-8
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # 检测目标 DLL
    dll_name = "msvcp140.dll"

    # 如果提供了路径参数，只检查特定路径的 DLL
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        # 默认检查 QuickLauncher 安装目录
        target_path = os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'QuickLauncher')

    print(f"检查路径: {target_path}")
    print(f"检查 DLL: {dll_name}")

    print(f"正在检测使用 {dll_name} 的进程...")
    print("-" * 60)

    processes = find_processes_using_dll(dll_name, target_path)

    if not processes:
        print(f"[OK] 没有进程占用 {dll_name}")
        return 0

    print(f"[警告] 发现 {len(processes)} 个进程占用 {dll_name}:")
    print()
    for proc in processes:
        print(f"  PID: {proc['pid']:6d}  进程名: {proc['name']}")

    print()
    print("请关闭以上程序后再进行安装。")
    return 1

if __name__ == "__main__":
    sys.exit(main())

