#pragma once

#ifdef QLAUTOSTART_EXPORTS
#define QLAUTOSTART_API __declspec(dllexport)
#else
#define QLAUTOSTART_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

struct QLAutostartStatus {
    int method;
    int enabled;
    const wchar_t* reason;
};

QLAUTOSTART_API int  QLautostart_version(void);
QLAUTOSTART_API const wchar_t* QLautostart_lastError(void);

QLAUTOSTART_API int  QLautostart_Enable(const wchar_t* exePath,
                                         const wchar_t* arguments,
                                         const wchar_t* workingDir,
                                         int isAdmin);

QLAUTOSTART_API int  QLautostart_Disable(int isAdmin);

QLAUTOSTART_API int  QLautostart_IsEnabled(void);

QLAUTOSTART_API int  QLautostart_GetMethod(void);

QLAUTOSTART_API int  QLautostart_GetStatus(QLAutostartStatus* outStatus);

QLAUTOSTART_API int  QLautostart_RunHelper(const wchar_t* action,
                                            const wchar_t* exePath,
                                            const wchar_t* arguments,
                                            const wchar_t* workingDir);

QLAUTOSTART_API int  QLautostart_RunLauncher(const wchar_t* exePath,
                                              const wchar_t* arguments,
                                              const wchar_t* workingDir);

QLAUTOSTART_API int  QLautostart_IsAllowedTarget(const wchar_t* exePath,
                                                  const wchar_t* arguments,
                                                  const wchar_t* workingDir);

QLAUTOSTART_API int  QLautostart_CleanupLegacyTasks(void);

#ifdef __cplusplus
}
#endif
