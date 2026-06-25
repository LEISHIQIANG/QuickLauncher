#pragma once

#ifdef QLUPDATE_EXPORTS
#define QLUPDATE_API __declspec(dllexport)
#else
#define QLUPDATE_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*QLUpdateCallback)(int event, const char* jsonData);

QLUPDATE_API int  QLupdate_version(void);
QLUPDATE_API const wchar_t* QLupdate_lastError(void);

QLUPDATE_API int  QLupdate_Check(const char* currentVersion,
                                  const char* updateSource,
                                  const char* configJson,
                                  QLUpdateCallback callback);

QLUPDATE_API int  QLupdate_Download(const char* url,
                                     const char* expectedHash,
                                     long long expectedSize,
                                     long long maxBytes,
                                     const char* targetDir,
                                     const char* version,
                                     const char* allowedHostsJson,
                                     int verifySsl,
                                     int allowInsecureHttp,
                                     QLUpdateCallback callback);

QLUPDATE_API void QLupdate_CancelDownload(void);

QLUPDATE_API int  QLupdate_Install(const char* installerPath,
                                    const char* expectedHash,
                                    const char* installDir,
                                    const char* trustedDir,
                                    const char* logPath,
                                    QLUpdateCallback callback);

QLUPDATE_API int  QLupdate_GetLatestSession(const char* baseDir,
                                             char* outJson,
                                             int bufferSize);

QLUPDATE_API int  QLupdate_ConfirmFirstStart(const char* baseDir);

QLUPDATE_API int  QLupdate_ValidateDownloadUrl(const char* url,
                                                const char* allowedHostsJson,
                                                int allowInsecure);

QLUPDATE_API int  QLupdate_CheckConnectivity(void);

#ifdef __cplusplus
}
#endif
