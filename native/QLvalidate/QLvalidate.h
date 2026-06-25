#pragma once

#ifdef QLVALIDATE_EXPORTS
#define QLVALIDATE_API __declspec(dllexport)
#else
#define QLVALIDATE_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

struct QLIpResult {
    int family;
    char address[46];
    int is_public;
};

QLVALIDATE_API int  QLvalidate_version(void);
QLVALIDATE_API const char* QLvalidate_lastError(void);

QLVALIDATE_API int  QLvalidate_IsPublicIpv4(unsigned int ipv4);
QLVALIDATE_API int  QLvalidate_IsPublicIpv6(const unsigned char* ipv6);
QLVALIDATE_API int  QLvalidate_IsPublicIpString(const char* ipStr);

QLVALIDATE_API int  QLvalidate_ResolveHost(const char* hostname,
                                            QLIpResult* outResults,
                                            int maxResults);

QLVALIDATE_API int  QLvalidate_NormalizeUrl(const char* inputUrl,
                                             char* outBuffer,
                                             int bufferSize);

QLVALIDATE_API int  QLvalidate_PublicUrl(const char* url,
                                          int trustProxy,
                                          char* errorBuf,
                                          int errorBufSize);

QLVALIDATE_API int  QLvalidate_IsLoopbackIpv4(unsigned int ipv4);
QLVALIDATE_API int  QLvalidate_IsPrivateIpv4(unsigned int ipv4);
QLVALIDATE_API int  QLvalidate_IsLinkLocalIpv4(unsigned int ipv4);
QLVALIDATE_API int  QLvalidate_IsMulticastIpv4(unsigned int ipv4);

#ifdef __cplusplus
}
#endif
