#define QLAUTOSTART_EXPORTS
#include "QLautostart.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <taskschd.h>
#include <comdef.h>
#include <string>
#include <cstring>
#include <cstdio>

#pragma comment(lib, "taskschd.lib")
#pragma comment(lib, "ole32.lib")

#define QL_TASK_NAME L"QuickLauncherAutoStart"
#define QL_TASK_FOLDER L"\\"
#define POLL_TIMEOUT_MS 20000
#define POLL_INTERVAL_MS 250

static thread_local wchar_t g_lastError[512] = L"";
static thread_local wchar_t g_statusReason[512] = L"";

static void setError(const wchar_t* msg) {
    wcsncpy_s(g_lastError, msg ? msg : L"", _TRUNCATE);
}

static void setStatusReason(const wchar_t* msg) {
    wcsncpy_s(g_statusReason, msg ? msg : L"", _TRUNCATE);
}

QLAUTOSTART_API int QLautostart_version(void) { return 1; }
QLAUTOSTART_API const wchar_t* QLautostart_lastError(void) { return g_lastError; }

// ---- helper: normalized args ----

static bool isEmpty(const wchar_t* s) {
    return !s || !*s;
}

// ---- Task Scheduler COM ----

static HRESULT initTaskService(ITaskService** ppService) {
    HRESULT hr = CoCreateInstance(
        CLSID_TaskScheduler, NULL, CLSCTX_INPROC_SERVER,
        IID_ITaskService, (void**)ppService);
    if (FAILED(hr)) return hr;
    hr = (*ppService)->Connect(_variant_t(), _variant_t(), _variant_t(), _variant_t());
    return hr;
}

static HRESULT getTask(ITaskService* pService, ITaskFolder** ppFolder,
                       IRegisteredTask** ppTask) {
    HRESULT hr = pService->GetFolder(_bstr_t(L"\\"), ppFolder);
    if (FAILED(hr)) return hr;
    hr = (*ppFolder)->GetTask(_bstr_t(QL_TASK_NAME), ppTask);
    return hr;
}

static int taskExists() {
    HRESULT hrCom = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    bool needsUninit = (hrCom == S_OK || hrCom == S_FALSE);

    ITaskService* pService = NULL;
    HRESULT hr = initTaskService(&pService);
    if (FAILED(hr) || !pService) {
        if (needsUninit) CoUninitialize();
        return 0;
    }

    ITaskFolder* pFolder = NULL;
    IRegisteredTask* pTask = NULL;
    hr = getTask(pService, &pFolder, &pTask);
    bool exists = SUCCEEDED(hr) && pTask;

    if (pTask) pTask->Release();
    if (pFolder) pFolder->Release();
    pService->Release();
    if (needsUninit) CoUninitialize();
    return exists ? 1 : 0;
}

static int enableTaskDirect(const wchar_t* exePath,
                             const wchar_t* arguments,
                             const wchar_t* workingDir) {
    HRESULT hrCom = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    bool needsUninit = (hrCom == S_OK || hrCom == S_FALSE);

    ITaskService* pService = NULL;
    HRESULT hr = initTaskService(&pService);
    if (FAILED(hr) || !pService) {
        if (needsUninit) CoUninitialize();
        setError(L"ITaskService init failed");
        return 2;
    }

    ITaskDefinition* pTaskDef = NULL;
    hr = pService->NewTask(0, &pTaskDef);
    if (FAILED(hr)) {
        pService->Release();
        if (needsUninit) CoUninitialize();
        setError(L"NewTask failed");
        return 2;
    }

    // Trigger: logon
    ITriggerCollection* pTriggers = NULL;
    pTaskDef->get_Triggers(&pTriggers);
    ITrigger* pTrigger = NULL;
    pTriggers->Create(TASK_TRIGGER_LOGON, &pTrigger);
    ILogonTrigger* pLogonTrigger = NULL;
    pTrigger->QueryInterface(IID_ILogonTrigger, (void**)&pLogonTrigger);
    if (pLogonTrigger) {
        pLogonTrigger->put_Delay(_bstr_t(L"PT2S"));
        pLogonTrigger->Release();
    }
    pTrigger->Release();
    pTriggers->Release();

    // Action: execute
    IActionCollection* pActions = NULL;
    pTaskDef->get_Actions(&pActions);
    IAction* pAction = NULL;
    pActions->Create(TASK_ACTION_EXEC, &pAction);
    IExecAction* pExecAction = NULL;
    pAction->QueryInterface(IID_IExecAction, (void**)&pExecAction);
    if (pExecAction) {
        pExecAction->put_Path(_bstr_t(exePath));
        if (!isEmpty(arguments)) pExecAction->put_Arguments(_bstr_t(arguments));
        if (!isEmpty(workingDir)) pExecAction->put_WorkingDirectory(_bstr_t(workingDir));
        pExecAction->Release();
    }
    pAction->Release();
    pActions->Release();

    // Settings
    ITaskSettings* pSettings = NULL;
    pTaskDef->get_Settings(&pSettings);
    if (pSettings) {
        pSettings->put_StartWhenAvailable(VARIANT_TRUE);
        pSettings->put_DisallowStartIfOnBatteries(VARIANT_FALSE);
        pSettings->put_StopIfGoingOnBatteries(VARIANT_FALSE);
        pSettings->put_ExecutionTimeLimit(_bstr_t(L"PT0S"));
        pSettings->put_Priority(4);
        pSettings->Release();
    }

    // Principal
    IPrincipal* pPrincipal = NULL;
    pTaskDef->get_Principal(&pPrincipal);
    if (pPrincipal) {
        pPrincipal->put_LogonType(TASK_LOGON_INTERACTIVE_TOKEN);
        pPrincipal->put_RunLevel(TASK_RUNLEVEL_LUA);
        pPrincipal->Release();
    }

    // Register with retry
    ITaskFolder* pRootFolder = NULL;
    pService->GetFolder(_bstr_t(L"\\"), &pRootFolder);
    IRegisteredTask* pRegTask = NULL;
    hr = E_FAIL;
    for (int attempt = 0; attempt < 2; attempt++) {
        hr = pRootFolder->RegisterTaskDefinition(
            _bstr_t(QL_TASK_NAME), pTaskDef,
            TASK_CREATE_OR_UPDATE,
            _variant_t(), _variant_t(),
            TASK_LOGON_INTERACTIVE_TOKEN,
            _variant_t(),
            &pRegTask);
        if (SUCCEEDED(hr)) break;
        if (attempt == 0) { if (pRegTask) { pRegTask->Release(); pRegTask = NULL; } Sleep(500); }
    }

    if (pRegTask) pRegTask->Release();
    pRootFolder->Release();
    pTaskDef->Release();
    pService->Release();
    if (needsUninit) CoUninitialize();

    if (FAILED(hr)) {
        setError(L"RegisterTaskDefinition failed");
        return 2;
    }
    return 0;
}

static int disableTaskDirect() {
    HRESULT hrCom = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    bool needsUninit = (hrCom == S_OK || hrCom == S_FALSE);

    ITaskService* pService = NULL;
    HRESULT hr = initTaskService(&pService);
    if (FAILED(hr)) {
        if (needsUninit) CoUninitialize();
        setError(L"ITaskService init failed");
        return 2;
    }

    ITaskFolder* pFolder = NULL;
    hr = pService->GetFolder(_bstr_t(L"\\"), &pFolder);
    if (FAILED(hr)) { pService->Release(); if (needsUninit) CoUninitialize(); return 2; }

    HRESULT delHr = S_OK;
    IRegisteredTask* pTask = NULL;
    hr = pFolder->GetTask(_bstr_t(QL_TASK_NAME), &pTask);
    if (SUCCEEDED(hr) && pTask) {
        delHr = pFolder->DeleteTask(_bstr_t(QL_TASK_NAME), 0);
        pTask->Release();
    }

    pFolder->Release();
    pService->Release();
    if (needsUninit) CoUninitialize();

    return SUCCEEDED(delHr) ? 0 : 2;
}

// ---- explorer token + launch ----

static bool getExplorerToken(HANDLE* phToken) {
    HWND hShell = GetShellWindow();
    if (!hShell) return false;

    DWORD pid = 0;
    GetWindowThreadProcessId(hShell, &pid);
    if (!pid) return false;

    HANDLE hProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!hProcess) return false;

    // Check elevation
    HANDLE hQueryToken = NULL;
    OpenProcessToken(hProcess, TOKEN_QUERY, &hQueryToken);
    if (hQueryToken) {
        TOKEN_ELEVATION elevation;
        DWORD size = sizeof(elevation);
        if (GetTokenInformation(hQueryToken, TokenElevation, &elevation, size, &size)) {
            if (elevation.TokenIsElevated) {
                CloseHandle(hQueryToken);
                CloseHandle(hProcess);
                return false;  // Explorer is elevated, refuse
            }
        }
        CloseHandle(hQueryToken);
    }

    HANDLE hToken = NULL;
    DWORD access = TOKEN_QUERY | TOKEN_DUPLICATE | TOKEN_ASSIGN_PRIMARY;
    if (!OpenProcessToken(hProcess, access, &hToken)) {
        access = TOKEN_QUERY | TOKEN_DUPLICATE;
        if (!OpenProcessToken(hProcess, access, &hToken)) {
            CloseHandle(hProcess);
            return false;
        }
    }

    HANDLE hDupToken = NULL;
    if (!DuplicateTokenEx(hToken, MAXIMUM_ALLOWED, NULL,
                          SecurityImpersonation, TokenPrimary, &hDupToken)) {
        CloseHandle(hToken);
        CloseHandle(hProcess);
        return false;
    }

    CloseHandle(hToken);
    CloseHandle(hProcess);
    *phToken = hDupToken;
    return true;
}

static int launchWithToken(HANDLE hToken, const wchar_t* exePath,
                           const wchar_t* args, const wchar_t* cwd) {
    std::wstring cmdLine = L"\"" + std::wstring(exePath) + L"\"";
    if (!isEmpty(args)) cmdLine += L" " + std::wstring(args);

    STARTUPINFOW si = { sizeof(si) };
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_SHOWDEFAULT;
    PROCESS_INFORMATION pi = {};

    BOOL ok = CreateProcessWithTokenW(
        hToken, 0, NULL, (LPWSTR)cmdLine.c_str(),
        CREATE_UNICODE_ENVIRONMENT,
        NULL, isEmpty(cwd) ? NULL : cwd, &si, &pi);

    if (ok) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
    return ok ? 0 : 1;
}

QLAUTOSTART_API int QLautostart_RunLauncher(const wchar_t* exePath,
                                              const wchar_t* arguments,
                                              const wchar_t* workingDir) {
    if (isEmpty(exePath)) {
        setError(L"exePath is required");
        return 3;
    }

    auto start = GetTickCount64();
    while (GetTickCount64() - start < POLL_TIMEOUT_MS) {
        HANDLE hToken = NULL;
        if (getExplorerToken(&hToken)) {
            int rc = launchWithToken(hToken, exePath, arguments, workingDir);
            CloseHandle(hToken);
            if (rc == 0) return 0;
        }
        Sleep(POLL_INTERVAL_MS);
    }

    setError(L"explorer token timeout");
    return 1;
}

// ---- public API ----

QLAUTOSTART_API int QLautostart_Enable(const wchar_t* exePath,
                                        const wchar_t* arguments,
                                        const wchar_t* workingDir,
                                        int isAdmin) {
    if (isEmpty(exePath)) {
        setError(L"exePath is required");
        return 3;
    }
    if (GetFileAttributesW(exePath) == INVALID_FILE_ATTRIBUTES) {
        setError(L"target exe not found");
        return 4;
    }

    if (isAdmin) {
        // Admin path: launch helper elevated to create de-elevated task
        std::wstring cmdLine = L"/c start \"\" /b \"" +
            std::wstring(exePath) + L"\" --autostart-helper enable --target-exe \"" +
            std::wstring(exePath) + L"\"";
        if (!isEmpty(arguments))
            cmdLine += L" --target-args \"" + std::wstring(arguments) + L"\"";
        if (!isEmpty(workingDir))
            cmdLine += L" --target-cwd \"" + std::wstring(workingDir) + L"\"";

        SHELLEXECUTEINFOW sei = { sizeof(sei) };
        sei.lpVerb = L"runas";
        sei.lpFile = L"cmd.exe";
        sei.lpParameters = cmdLine.c_str();
        sei.nShow = SW_HIDE;
        sei.fMask = SEE_MASK_NOCLOSEPROCESS;

        if (!ShellExecuteExW(&sei)) {
            DWORD err = GetLastError();
            if (err == ERROR_CANCELLED) {
                setError(L"UAC cancelled by user");
                return 1;
            }
            setError(L"ShellExecuteEx runas failed");
            return 2;
        }
        if (sei.hProcess) {
            WaitForSingleObject(sei.hProcess, 30000);
            CloseHandle(sei.hProcess);
        }
        return 0;
    } else {
        return enableTaskDirect(exePath, arguments, workingDir);
    }
}

QLAUTOSTART_API int QLautostart_Disable(int isAdmin) {
    if (isAdmin) {
        // Admin path: launch helper elevated to delete task
        wchar_t sysDir[MAX_PATH];
        GetSystemDirectoryW(sysDir, MAX_PATH);
        std::wstring cmdPath = std::wstring(sysDir) + L"\\cmd.exe";

        std::wstring cmdLine = L"/c schtasks /Delete /TN \"" +
            std::wstring(QL_TASK_NAME) + L"\" /F";

        SHELLEXECUTEINFOW sei = { sizeof(sei) };
        sei.lpVerb = L"runas";
        sei.lpFile = cmdPath.c_str();
        sei.lpParameters = cmdLine.c_str();
        sei.nShow = SW_HIDE;
        sei.fMask = SEE_MASK_NOCLOSEPROCESS;

        if (ShellExecuteExW(&sei)) {
            if (sei.hProcess) {
                WaitForSingleObject(sei.hProcess, 15000);
                CloseHandle(sei.hProcess);
            }
        }
        return 0;
    }
    return disableTaskDirect();
}

QLAUTOSTART_API int QLautostart_IsEnabled(void) {
    return taskExists();
}

QLAUTOSTART_API int QLautostart_GetMethod(void) {
    if (taskExists()) return 0;  // QL_AUTOSTART_TASK_SCHEDULER
    return 1;  // QL_AUTOSTART_NONE
}

QLAUTOSTART_API int QLautostart_GetStatus(QLAutostartStatus* outStatus) {
    if (!outStatus) return 2;

    outStatus->enabled = taskExists() ? 1 : 0;
    outStatus->method = outStatus->enabled ? 0 : 1;

    if (outStatus->enabled) {
        setStatusReason(L"Task Scheduler task exists");
    } else {
        setStatusReason(L"No auto-start configured");
    }
    outStatus->reason = g_statusReason;
    return 0;
}

QLAUTOSTART_API int QLautostart_RunHelper(const wchar_t* action,
                                           const wchar_t* exePath,
                                           const wchar_t* arguments,
                                           const wchar_t* workingDir) {
    if (isEmpty(action) || isEmpty(exePath)) {
        setError(L"action and exePath required");
        return 3;
    }

    std::wstring actStr(action);
    if (actStr == L"enable") {
        int rc = enableTaskDirect(exePath, arguments, workingDir);
        return rc;
    } else if (actStr == L"disable") {
        int rc = disableTaskDirect();
        return rc;
    }

    setError(L"unknown action");
    return 3;
}

QLAUTOSTART_API int QLautostart_IsAllowedTarget(const wchar_t* exePath,
                                                 const wchar_t* arguments,
                                                 const wchar_t* workingDir) {
    if (isEmpty(exePath)) return 0;
    if (GetFileAttributesW(exePath) == INVALID_FILE_ATTRIBUTES) return 0;
    return 1;
}

QLAUTOSTART_API int QLautostart_CleanupLegacyTasks(void) {
    static const wchar_t* legacyNames[] = {
        L"QuickLauncher_AutoStart",
        L"QuickLauncherAutoStart_Admin",
        NULL
    };

    HRESULT hrCom = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    bool needsUninit = (hrCom == S_OK || hrCom == S_FALSE);

    ITaskService* pService = NULL;
    HRESULT hr = initTaskService(&pService);
    if (FAILED(hr)) {
        if (needsUninit) CoUninitialize();
        setError(L"ITaskService init failed");
        return 2;
    }

    ITaskFolder* pFolder = NULL;
    hr = pService->GetFolder(_bstr_t(L"\\"), &pFolder);
    if (FAILED(hr)) {
        pService->Release();
        if (needsUninit) CoUninitialize();
        return 2;
    }

    int cleaned = 0;
    for (int i = 0; legacyNames[i]; i++) {
        IRegisteredTask* pTask = NULL;
        hr = pFolder->GetTask(_bstr_t(legacyNames[i]), &pTask);
        if (SUCCEEDED(hr) && pTask) {
            pTask->Release();
            HRESULT delHr = pFolder->DeleteTask(_bstr_t(legacyNames[i]), 0);
            if (SUCCEEDED(delHr)) cleaned++;
        }
    }

    pFolder->Release();
    pService->Release();
    if (needsUninit) CoUninitialize();

    // Clean registry legacy entries
    HKEY hKey = NULL;
    if (RegOpenKeyExW(HKEY_CURRENT_USER,
                      L"Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                      0, KEY_SET_VALUE | KEY_QUERY_VALUE, &hKey) == ERROR_SUCCESS) {
        RegDeleteValueW(hKey, L"QuickLauncher");
        RegDeleteValueW(hKey, L"QuickLauncherAutoStart");
        RegCloseKey(hKey);
    }

    return cleaned;
}
