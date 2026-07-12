#pragma once

#ifdef QLWATCH_EXPORTS
#define QLWATCH_API __declspec(dllexport)
#else
#define QLWATCH_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*QLWatchCallback)(const char* folderId);

QLWATCH_API int  QLwatch_version(void);
QLWATCH_API const wchar_t* QLwatch_lastError(void);

QLWATCH_API int  QLwatch_Init(void);
QLWATCH_API void QLwatch_Release(void);

QLWATCH_API int  QLwatch_Start(const char* folderId,
                                const wchar_t* path,
                                QLWatchCallback callback);
QLWATCH_API int  QLwatch_Stop(const char* folderId);
QLWATCH_API void QLwatch_StopAll(void);

#ifdef __cplusplus
}
#endif
