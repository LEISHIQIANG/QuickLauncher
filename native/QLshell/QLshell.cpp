#define QLSHELL_EXPORTS
#include "QLshell.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <string>

static thread_local wchar_t g_lastError[512] = L"";

static void setError(const wchar_t* msg) {
    wcsncpy_s(g_lastError, msg ? msg : L"", _TRUNCATE);
}

QLSHELL_API int QLshell_version(void) { return 1; }

QLSHELL_API const wchar_t* QLshell_lastError(void) { return g_lastError; }

QLSHELL_API int QLshell_OpenPath(const wchar_t* path) {
    if (!path || !*path) { setError(L"empty path"); return -1; }
    DWORD attrs = GetFileAttributesW(path);
    if (attrs == INVALID_FILE_ATTRIBUTES) { setError(L"path not found"); return -1; }
    SHELLEXECUTEINFOW sei = { sizeof(sei) };
    sei.fMask = SEE_MASK_DEFAULT;
    sei.lpVerb = L"open";
    sei.lpFile = path;
    sei.nShow = SW_SHOWNORMAL;
    if (!ShellExecuteExW(&sei)) { setError(L"ShellExecuteEx failed"); return -2; }
    return 0;
}

QLSHELL_API int QLshell_Relaunch(const wchar_t* exePath,
                                  const wchar_t* const* argv) {
    if (!exePath || !*exePath) { setError(L"empty exePath"); return -1; }
    std::wstring cmdLine = L"\"" + std::wstring(exePath) + L"\"";
    if (argv) {
        for (int i = 0; argv[i]; i++)
            cmdLine += L" " + std::wstring(argv[i]);
    }
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {0};
    DWORD flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | 0x01000000;
    if (!CreateProcessW(exePath, cmdLine.data(), NULL, NULL, FALSE,
                        flags, NULL, NULL, &si, &pi)) {
        setError(L"CreateProcess failed");
        return -1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

QLSHELL_API int QLshell_RunDetached(const wchar_t* exePath,
                                     const wchar_t* const* argv,
                                     const wchar_t* workingDir) {
    if (!exePath || !*exePath) { setError(L"empty exePath"); return -1; }
    std::wstring cmdLine = L"\"" + std::wstring(exePath) + L"\"";
    if (argv) {
        for (int i = 0; argv[i]; i++)
            cmdLine += L" " + std::wstring(argv[i]);
    }
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessW(NULL, cmdLine.data(), NULL, NULL, FALSE,
                        CREATE_NO_WINDOW, NULL,
                        workingDir && workingDir[0] ? workingDir : NULL,
                        &si, &pi)) {
        setError(L"CreateProcess failed");
        return -1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

QLSHELL_API int QLshell_LaunchWithFile(const wchar_t* exePath,
                                        const wchar_t* filePath,
                                        const wchar_t* workingDir,
                                        int useCmdStart) {
    if (!exePath || !*exePath || !filePath || !*filePath) {
        setError(L"empty arguments"); return -1;
    }
    std::wstring cmdLine;
    if (useCmdStart) {
        cmdLine = L"cmd /c start \"\" \"" + std::wstring(exePath) +
                  L"\" \"" + std::wstring(filePath) + L"\"";
    } else {
        cmdLine = L"\"" + std::wstring(exePath) + L"\" \"" +
                  std::wstring(filePath) + L"\"";
    }
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {0};
    DWORD flags = CREATE_NEW_PROCESS_GROUP;
    if (useCmdStart) {
        flags |= CREATE_NO_WINDOW | 0x01000000;
    } else {
        flags |= DETACHED_PROCESS | 0x01000000;
    }
    if (!CreateProcessW(NULL, cmdLine.data(), NULL, NULL, FALSE,
                        flags, NULL,
                        workingDir && workingDir[0] ? workingDir : NULL,
                        &si, &pi)) {
        setError(L"CreateProcess failed");
        return -2;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
