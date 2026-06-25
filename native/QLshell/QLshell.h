#pragma once

#ifdef QLSHELL_EXPORTS
#define QLSHELL_API __declspec(dllexport)
#else
#define QLSHELL_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

QLSHELL_API int  QLshell_version(void);
QLSHELL_API const wchar_t* QLshell_lastError(void);

QLSHELL_API int  QLshell_OpenPath(const wchar_t* path);
QLSHELL_API int  QLshell_Relaunch(const wchar_t* exePath,
                                   const wchar_t* const* argv);
QLSHELL_API int  QLshell_RunDetached(const wchar_t* exePath,
                                      const wchar_t* const* argv,
                                      const wchar_t* workingDir);
QLSHELL_API int  QLshell_LaunchWithFile(const wchar_t* exePath,
                                         const wchar_t* filePath,
                                         const wchar_t* workingDir,
                                         int useCmdStart);

#ifdef __cplusplus
}
#endif
