#define QLVALIDATE_EXPORTS
#include "QLvalidate.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <string>
#include <cstring>

#pragma comment(lib, "ws2_32.lib")

static thread_local char g_lastError[256] = "";

static void setError(const char* msg) {
    strncpy_s(g_lastError, msg ? msg : "", _TRUNCATE);
}

QLVALIDATE_API int QLvalidate_version(void) { return 1; }

QLVALIDATE_API const char* QLvalidate_lastError(void) { return g_lastError; }

QLVALIDATE_API int QLvalidate_IsPublicIpv4(unsigned int ip_be) {
    if ((ip_be & 0xFF000000) == 0x0A000000) return 0;
    if ((ip_be & 0xFFF00000) == 0xAC100000) return 0;
    if ((ip_be & 0xFFFF0000) == 0xC0A80000) return 0;
    if ((ip_be & 0xFF000000) == 0x7F000000) return 0;
    if ((ip_be & 0xFFFF0000) == 0xA9FE0000) return 0;
    if ((ip_be & 0xFFC00000) == 0x64400000) return 0;
    if ((ip_be & 0xFFFFFF00) == 0xC0000200) return 0;
    if ((ip_be & 0xFFFFFF00) == 0xC6336400) return 0;
    if ((ip_be & 0xFFFFFF00) == 0xCB007100) return 0;
    if ((ip_be & 0xFFFE0000) == 0xC6120000) return 0;
    if ((ip_be & 0xF0000000) == 0xE0000000) return 0;
    if ((ip_be & 0xFF000000) == 0x00000000) return 0;
    if ((ip_be & 0xF0000000) == 0xF0000000) return 0;
    return 1;
}

QLVALIDATE_API int QLvalidate_IsPublicIpv6(const unsigned char* ipv6) {
    if (!ipv6) return 0;
    if (ipv6[0] == 0 && ipv6[1] == 0 && ipv6[2] == 0 && ipv6[3] == 0 &&
        ipv6[4] == 0 && ipv6[5] == 0 && ipv6[6] == 0 && ipv6[7] == 0 &&
        ipv6[8] == 0 && ipv6[9] == 0 && ipv6[10] == 0 && ipv6[11] == 0 &&
        ipv6[12] == 0 && ipv6[13] == 0 && ipv6[14] == 0) {
        if (ipv6[15] == 0) return 0;
        if (ipv6[15] == 1) return 0;
    }
    if (ipv6[0] == 0xFE && (ipv6[1] & 0xC0) == 0x80) return 0;
    if (ipv6[0] == 0xFE && (ipv6[1] & 0xC0) == 0xC0) return 0;
    if (ipv6[0] == 0xFF) return 0;
    if (ipv6[0] == 0xFC) return 0;
    if (ipv6[0] == 0xFD) return 0;
    return 1;
}

static unsigned int parseIpv4(const char* ipStr) {
    unsigned int a = 0, b = 0, c = 0, d = 0;
    if (sscanf_s(ipStr, "%u.%u.%u.%u", &a, &b, &c, &d) == 4 &&
        a <= 255 && b <= 255 && c <= 255 && d <= 255) {
        return (a << 24) | (b << 16) | (c << 8) | d;
    }
    return 0xFFFFFFFF;
}

QLVALIDATE_API int QLvalidate_IsPublicIpString(const char* ipStr) {
    if (!ipStr) return -1;
    unsigned int ipv4 = parseIpv4(ipStr);
    if (ipv4 != 0xFFFFFFFF) return QLvalidate_IsPublicIpv4(ipv4);
    struct in6_addr addr6;
    if (inet_pton(AF_INET6, ipStr, &addr6) == 1)
        return QLvalidate_IsPublicIpv6(addr6.u.Byte);
    return -1;
}

QLVALIDATE_API int QLvalidate_ResolveHost(const char* hostname,
                                           QLIpResult* outResults,
                                           int maxResults) {
    if (!hostname || !outResults || maxResults <= 0) {
        setError("invalid arguments");
        return -1;
    }
    struct addrinfo hints = {}, *result = nullptr;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    int rc = getaddrinfo(hostname, nullptr, &hints, &result);
    if (rc != 0 || !result) {
        setError("DNS resolution failed");
        return -1;
    }
    int count = 0;
    for (struct addrinfo* ptr = result; ptr && count < maxResults; ptr = ptr->ai_next) {
        if (ptr->ai_family == AF_INET) {
            struct sockaddr_in* sa = (struct sockaddr_in*)ptr->ai_addr;
            inet_ntop(AF_INET, &sa->sin_addr,
                      outResults[count].address, sizeof(outResults[count].address));
            outResults[count].family = AF_INET;
            outResults[count].is_public = QLvalidate_IsPublicIpv4(
                (unsigned int)sa->sin_addr.s_addr);
            count++;
        } else if (ptr->ai_family == AF_INET6) {
            struct sockaddr_in6* sa = (struct sockaddr_in6*)ptr->ai_addr;
            inet_ntop(AF_INET6, &sa->sin6_addr,
                      outResults[count].address, sizeof(outResults[count].address));
            outResults[count].family = AF_INET6;
            outResults[count].is_public = QLvalidate_IsPublicIpv6(sa->sin6_addr.u.Byte);
            count++;
        }
    }
    freeaddrinfo(result);
    return count;
}

QLVALIDATE_API int QLvalidate_NormalizeUrl(const char* inputUrl,
                                            char* outBuffer,
                                            int bufferSize) {
    if (!inputUrl || !outBuffer || bufferSize <= 0) return -1;
    std::string url(inputUrl);
    while (!url.empty() && (url.front() == ' ' || url.front() == '\t'))
        url.erase(0, 1);
    while (!url.empty() && (url.back() == ' ' || url.back() == '\t'))
        url.pop_back();
    if (url.find("://") == std::string::npos) url = "https://" + url;
    int len = (int)url.length();
    if (len >= bufferSize) len = bufferSize - 1;
    memcpy(outBuffer, url.c_str(), len);
    outBuffer[len] = '\0';
    return len;
}

static std::string toLower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = (char)tolower((unsigned char)c);
    return r;
}

static bool endsWith(const std::string& str, const std::string& suffix) {
    if (suffix.size() > str.size()) return false;
    return str.compare(str.size() - suffix.size(), suffix.size(), suffix) == 0;
}

QLVALIDATE_API int QLvalidate_PublicUrl(const char* url,
                                         int trustProxy,
                                         char* errorBuf,
                                         int errorBufSize) {
    if (!url) { setError("empty URL"); return 1; }

    const char* schemeEnd = strstr(url, "://");
    if (!schemeEnd) { setError("unsupported scheme"); return 2; }
    std::string scheme(url, schemeEnd);
    if (scheme != "http" && scheme != "https") {
        setError("unsupported scheme"); return 2;
    }

    const char* hostStart = schemeEnd + 3;
    const char* hostEnd = strpbrk(hostStart, ":/?#");
    std::string host(hostStart, hostEnd ? (size_t)(hostEnd - hostStart) : strlen(hostStart));

    if (host.empty()) { setError("missing host"); return 3; }

    std::string hostLower = toLower(host);
    if (hostLower == "localhost" || endsWith(hostLower, ".localhost")) {
        setError("localhost blocked"); return 4;
    }

    unsigned int ipv4 = parseIpv4(host.c_str());
    if (ipv4 != 0xFFFFFFFF) {
        return QLvalidate_IsPublicIpv4(ipv4) ? 0 : 5;
    }

    if (trustProxy) return 0;

    QLIpResult results[16];
    int count = QLvalidate_ResolveHost(host.c_str(), results, 16);
    if (count < 0) { setError("DNS failed"); return 6; }

    for (int i = 0; i < count; i++) {
        if (!results[i].is_public) {
            setError("DNS resolves to private IP"); return 7;
        }
    }
    return 0;
}

QLVALIDATE_API int QLvalidate_IsLoopbackIpv4(unsigned int ip_be) {
    return ((ip_be & 0xFF000000) == 0x7F000000) ? 1 : 0;
}

QLVALIDATE_API int QLvalidate_IsPrivateIpv4(unsigned int ip_be) {
    if ((ip_be & 0xFF000000) == 0x0A000000) return 1;
    if ((ip_be & 0xFFF00000) == 0xAC100000) return 1;
    if ((ip_be & 0xFFFF0000) == 0xC0A80000) return 1;
    if ((ip_be & 0xFFC00000) == 0x64400000) return 1;
    if ((ip_be & 0xFF000000) == 0x00000000) return 1;
    return 0;
}

QLVALIDATE_API int QLvalidate_IsLinkLocalIpv4(unsigned int ip_be) {
    return ((ip_be & 0xFFFF0000) == 0xA9FE0000) ? 1 : 0;
}

QLVALIDATE_API int QLvalidate_IsMulticastIpv4(unsigned int ip_be) {
    return ((ip_be & 0xF0000000) == 0xE0000000) ? 1 : 0;
}
