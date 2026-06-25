#define QLUPDATE_EXPORTS
#include "QLupdate.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winhttp.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <wininet.h>
#include <bcrypt.h>

#include <string>
#include <vector>
#include <atomic>
#include <algorithm>
#include <cstdio>
#include <cstring>

#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "wininet.lib")
#pragma comment(lib, "bcrypt.lib")

static thread_local wchar_t g_lastError[512] = L"";

static void setError(const wchar_t* msg) {
    wcsncpy_s(g_lastError, msg ? msg : L"", _TRUNCATE);
}

QLUPDATE_API int QLupdate_version(void) { return 1; }
QLUPDATE_API const wchar_t* QLupdate_lastError(void) { return g_lastError; }

// ---- connectivity ----

QLUPDATE_API int QLupdate_CheckConnectivity(void) {
    DWORD flags = 0;
    return InternetGetConnectedState(&flags, 0) ? 0 : -1;
}

// ---- URL validation ----

static std::wstring toWide(const char* utf8) {
    if (!utf8) return L"";
    int len = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, NULL, 0);
    if (len <= 0) return L"";
    std::wstring result(len - 1, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, utf8, -1, &result[0], len);
    return result;
}

static std::string toUtf8(const wchar_t* wide) {
    if (!wide) return "";
    int len = WideCharToMultiByte(CP_UTF8, 0, wide, -1, NULL, 0, NULL, NULL);
    if (len <= 0) return "";
    std::string result(len - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, wide, -1, &result[0], len, NULL, NULL);
    return result;
}

static unsigned int parseIpv4(const char* ipStr) {
    unsigned int a = 0, b = 0, c = 0, d = 0;
    if (sscanf_s(ipStr, "%u.%u.%u.%u", &a, &b, &c, &d) == 4 &&
        a <= 255 && b <= 255 && c <= 255 && d <= 255) {
        return (a << 24) | (b << 16) | (c << 8) | d;
    }
    return 0xFFFFFFFF;
}

static bool isPublicIpv4(unsigned int ip_be) {
    if ((ip_be & 0xFF000000) == 0x0A000000) return false;
    if ((ip_be & 0xFFF00000) == 0xAC100000) return false;
    if ((ip_be & 0xFFFF0000) == 0xC0A80000) return false;
    if ((ip_be & 0xFF000000) == 0x7F000000) return false;
    if ((ip_be & 0xFFFF0000) == 0xA9FE0000) return false;
    if ((ip_be & 0xFFC00000) == 0x64400000) return false;
    if ((ip_be & 0xF0000000) == 0xE0000000) return false;
    return true;
}

static bool hostMatches(const char* host, const char* allowedHostsJson) {
    if (!allowedHostsJson || !*allowedHostsJson) return true;
    std::string json(allowedHostsJson);
    std::string hostStr(host);
    for (auto& c : hostStr) c = (char)tolower((unsigned char)c);
    size_t pos = 0;
    while ((pos = json.find('"', pos)) != std::string::npos) {
        size_t start = pos + 1;
        size_t end = json.find('"', start);
        if (end == std::string::npos) break;
        std::string allowed = json.substr(start, end - start);
        for (auto& c : allowed) c = (char)tolower((unsigned char)c);
        if (hostStr == allowed || (hostStr.size() > allowed.size() + 1 &&
            hostStr.compare(hostStr.size() - allowed.size() - 1, allowed.size() + 1,
                           "." + allowed) == 0)) {
            return true;
        }
        pos = end + 1;
    }
    return false;
}

QLUPDATE_API int QLupdate_ValidateDownloadUrl(const char* url,
                                               const char* allowedHostsJson,
                                               int allowInsecure) {
    if (!url) { setError(L"empty URL"); return -1; }
    const char* schemeEnd = strstr(url, "://");
    if (!schemeEnd) { setError(L"unsupported scheme"); return -1; }
    std::string scheme(url, schemeEnd);
    bool isHttps = (scheme == "https");
    if (!isHttps && scheme != "http") { setError(L"unsupported scheme"); return -1; }
    if (!isHttps && !allowInsecure) { setError(L"HTTP not allowed"); return -1; }

    const char* hostStart = schemeEnd + 3;
    const char* hostEnd = strpbrk(hostStart, ":/?#");
    std::string host(hostStart, hostEnd ? (size_t)(hostEnd - hostStart) : strlen(hostStart));
    if (host.empty()) { setError(L"missing host"); return -1; }
    if (!hostMatches(host.c_str(), allowedHostsJson)) {
        setError(L"host not in allowed list"); return -2;
    }

    unsigned int ipv4 = parseIpv4(host.c_str());
    if (ipv4 != 0xFFFFFFFF && !isPublicIpv4(ipv4)) {
        setError(L"private IP blocked"); return -2;
    }
    return 0;
}

// ---- session state ----

static std::string readFile(const wchar_t* path) {
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL,
                           OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return "";
    DWORD size = GetFileSize(h, NULL);
    std::string content(size, '\0');
    DWORD read = 0;
    ReadFile(h, &content[0], size, &read, NULL);
    CloseHandle(h);
    if (read != size) return "";
    return content;
}

static bool writeFile(const wchar_t* path, const std::string& content) {
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    WriteFile(h, content.data(), (DWORD)content.size(), &written, NULL);
    CloseHandle(h);
    return written == content.size();
}

QLUPDATE_API int QLupdate_GetLatestSession(const char* baseDir,
                                            char* outJson,
                                            int bufferSize) {
    if (!baseDir || !outJson || bufferSize <= 0) {
        setError(L"invalid arguments"); return -1;
    }
    std::wstring dir = toWide(baseDir);
    if (dir.empty()) { setError(L"baseDir conversion failed"); return -1; }

    WIN32_FIND_DATAW fd;
    std::wstring pattern = dir + L"\\update_session_*.json";
    HANDLE hFind = FindFirstFileW(pattern.c_str(), &fd);
    if (hFind == INVALID_HANDLE_VALUE) {
        setError(L"no session files found"); return -1;
    }

    std::wstring latestPath;
    FILETIME latestTime = {};
    do {
        if (CompareFileTime(&fd.ftCreationTime, &latestTime) > 0 || latestTime.dwLowDateTime == 0) {
            latestTime = fd.ftCreationTime;
            latestPath = dir + L"\\" + fd.cFileName;
        }
    } while (FindNextFileW(hFind, &fd));
    FindClose(hFind);

    if (latestPath.empty()) { setError(L"no session files found"); return -1; }

    std::string content = readFile(latestPath.c_str());
    if (content.empty()) { setError(L"failed to read session file"); return -1; }

    int len = (int)content.size();
    if (len >= bufferSize) { len = bufferSize - 1; }
    memcpy(outJson, content.c_str(), len);
    outJson[len] = '\0';
    return len;
}

QLUPDATE_API int QLupdate_ConfirmFirstStart(const char* baseDir) {
    if (!baseDir) { setError(L"invalid arguments"); return -1; }
    std::wstring dir = toWide(baseDir);
    if (dir.empty()) return -1;
    std::wstring marker = dir + L"\\first_start_confirmed";
    HANDLE h = CreateFileW(marker.c_str(), GENERIC_WRITE, 0, NULL,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) { setError(L"failed to create marker"); return -1; }
    CloseHandle(h);
    return 0;
}

// ---- download cancel ----

static std::atomic<bool> g_cancelDownload{false};

QLUPDATE_API void QLupdate_CancelDownload(void) {
    g_cancelDownload = true;
}

// ---- download ----

QLUPDATE_API int QLupdate_Download(const char* url,
                                    const char* expectedHash,
                                    long long expectedSize,
                                    long long maxBytes,
                                    const char* targetDir,
                                    const char* version,
                                    const char* allowedHostsJson,
                                    int verifySsl,
                                    int allowInsecureHttp,
                                    QLUpdateCallback callback) {
    if (!url || !targetDir) { setError(L"invalid arguments"); return -1; }

    // Validate URL
    int valRc = QLupdate_ValidateDownloadUrl(url, allowedHostsJson, allowInsecureHttp);
    if (valRc != 0) return valRc;

    g_cancelDownload = false;

    std::wstring wUrl = toWide(url);
    std::wstring wTargetDir = toWide(targetDir);
    std::wstring wVersion = toWide(version);

    // Parse URL components
    URL_COMPONENTS urlComp = { sizeof(urlComp) };
    wchar_t hostName[256] = L"";
    wchar_t urlPath[2048] = L"";
    urlComp.lpszHostName = hostName;
    urlComp.dwHostNameLength = 255;
    urlComp.lpszUrlPath = urlPath;
    urlComp.dwUrlPathLength = 2047;

    if (!WinHttpCrackUrl(wUrl.c_str(), (DWORD)wUrl.length(), 0, &urlComp)) {
        setError(L"WinHttpCrackUrl failed"); return -1;
    }

    bool isHttps = (urlComp.nScheme == INTERNET_SCHEME_HTTPS);

    HINTERNET hSession = WinHttpOpen(
        L"QuickLauncher/Update",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS, 0);

    if (!hSession) { setError(L"WinHttpOpen failed"); return -1; }

    DWORD timeout = 30000;
    WinHttpSetOption(hSession, WINHTTP_OPTION_CONNECT_TIMEOUT, &timeout, sizeof(timeout));
    WinHttpSetOption(hSession, WINHTTP_OPTION_RECEIVE_TIMEOUT, &timeout, sizeof(timeout));

    HINTERNET hConnect = WinHttpConnect(hSession, hostName, urlComp.nPort, 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); setError(L"WinHttpConnect failed"); return -1; }

    DWORD openFlags = isHttps ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", urlPath,
                                             NULL, WINHTTP_NO_REFERER,
                                             WINHTTP_DEFAULT_ACCEPT_TYPES, openFlags);
    if (!hRequest) {
        WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession);
        setError(L"WinHttpOpenRequest failed"); return -1;
    }

    if (!verifySsl && isHttps) {
        DWORD securityFlags = SECURITY_FLAG_IGNORE_UNKNOWN_CA |
                              SECURITY_FLAG_IGNORE_CERT_CN_INVALID |
                              SECURITY_FLAG_IGNORE_CERT_DATE_INVALID;
        WinHttpSetOption(hRequest, WINHTTP_OPTION_SECURITY_FLAGS,
                        &securityFlags, sizeof(securityFlags));
    }

    if (!WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                            WINHTTP_NO_REQUEST_DATA, 0, 0, 0)) {
        WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession); setError(L"WinHttpSendRequest failed"); return -1;
    }

    if (!WinHttpReceiveResponse(hRequest, NULL)) {
        WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession); setError(L"WinHttpReceiveResponse failed"); return -1;
    }

    DWORD statusCode = 0;
    DWORD statusSize = sizeof(statusCode);
    WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                       NULL, &statusCode, &statusSize, NULL);

    if (statusCode != 200) {
        WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        setError(L"HTTP status not 200"); return -1;
    }

    // Create target file
    std::wstring tmpPath = wTargetDir + L"\\update_download.tmp";
    std::wstring finalPath = wTargetDir + L"\\QuickLauncher_Setup.exe";

    HANDLE hFile = CreateFileW(tmpPath.c_str(), GENERIC_WRITE, 0, NULL,
                               CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        setError(L"failed to create output file"); return -1;
    }

    long long downloaded = 0;
    DWORD bufferSize = 65536;
    std::vector<unsigned char> buffer(bufferSize);
    bool cancelled = false;

    // BCrypt hash
    BCRYPT_ALG_HANDLE hAlg = NULL;
    BCRYPT_HASH_HANDLE hHash = NULL;
    bool doHash = (expectedHash && expectedHash[0]);
    if (doHash) {
        BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_SHA256_ALGORITHM, NULL, 0);
        if (hAlg) BCryptCreateHash(hAlg, &hHash, NULL, 0, NULL, 0, 0);
    }

    while (true) {
        if (g_cancelDownload) { cancelled = true; break; }

        DWORD available = 0;
        if (!WinHttpQueryDataAvailable(hRequest, &available)) break;
        if (available == 0) break;

        DWORD toRead = (available > bufferSize) ? bufferSize : available;
        DWORD bytesRead = 0;
        if (!WinHttpReadData(hRequest, buffer.data(), toRead, &bytesRead)) break;
        if (bytesRead == 0) break;

        if (maxBytes > 0 && downloaded + bytesRead > maxBytes) {
            setError(L"download exceeds max bytes"); break;
        }

        DWORD written = 0;
        WriteFile(hFile, buffer.data(), bytesRead, &written, NULL);
        if (written != bytesRead) break;

        if (doHash && hHash) {
            BCryptHashData(hHash, buffer.data(), bytesRead, 0);
        }

        downloaded += bytesRead;

        if (callback) {
            DWORD totalSize = 0;
            DWORD contentLenSize = sizeof(totalSize);
            WinHttpQueryHeaders(hRequest,
                WINHTTP_QUERY_CONTENT_LENGTH | WINHTTP_QUERY_FLAG_NUMBER,
                NULL, &totalSize, &contentLenSize, NULL);

            char progressJson[256];
            int percent = totalSize > 0 ? (int)(downloaded * 100 / totalSize) : 0;
            snprintf(progressJson, sizeof(progressJson),
                "{\"downloaded\":%lld,\"total\":%lu,\"percent\":%d}",
                downloaded, totalSize, percent);
            callback(6, progressJson);  // QL_UPDATE_DOWNLOAD_PROGRESS
        }
    }

    CloseHandle(hFile);

    // Finalize hash
    if (doHash && hHash) {
        BYTE hash[32];
        BCryptFinishHash(hHash, hash, 32, 0);
        BCryptDestroyHash(hHash);
        BCryptCloseAlgorithmProvider(hAlg, 0);

        // Compare with expected
        if (expectedHash && expectedHash[0]) {
            const char* hashPrefix = "sha256:";
            const char* expectedHex = expectedHash;
            if (strncmp(expectedHash, hashPrefix, 7) == 0)
                expectedHex = expectedHash + 7;

            char actualHex[65];
            for (int i = 0; i < 32; i++)
                snprintf(actualHex + i * 2, 3, "%02x", hash[i]);
            actualHex[64] = '\0';

            if (_stricmp(actualHex, expectedHex) != 0) {
                DeleteFileW(tmpPath.c_str());
                WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
                setError(L"SHA-256 mismatch");
                return -3;
            }
        }
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);

    if (cancelled) {
        DeleteFileW(tmpPath.c_str());
        if (callback) callback(9, "{}");  // QL_UPDATE_DOWNLOAD_CANCELLED
        return -2;
    }

    // Check expected size
    if (expectedSize > 0 && downloaded != expectedSize) {
        DeleteFileW(tmpPath.c_str());
        setError(L"download size mismatch");
        return -1;
    }

    // Rename temp to final
    MoveFileExW(tmpPath.c_str(), finalPath.c_str(), MOVEFILE_REPLACE_EXISTING);

    char doneJson[512];
    std::string finalPathUtf8 = toUtf8(finalPath.c_str());
    snprintf(doneJson, sizeof(doneJson),
        "{\"installer_path\":\"%s\",\"bytes\":%lld}", finalPathUtf8.c_str(), downloaded);
    if (callback) callback(7, doneJson);  // QL_UPDATE_DOWNLOAD_FINISHED
    return 0;
}

// ---- install ----

QLUPDATE_API int QLupdate_Install(const char* installerPath,
                                   const char* expectedHash,
                                   const char* installDir,
                                   const char* trustedDir,
                                   const char* logPath,
                                   QLUpdateCallback callback) {
    if (!installerPath || !installDir) {
        setError(L"invalid arguments"); return -1;
    }
    std::wstring wPath = toWide(installerPath);
    std::wstring wDir = toWide(installDir);

    if (GetFileAttributesW(wPath.c_str()) == INVALID_FILE_ATTRIBUTES) {
        setError(L"installer not found"); return -1;
    }

    // Path safety: ensure installer is under trusted directory
    if (trustedDir && trustedDir[0]) {
        std::wstring wTrusted = toWide(trustedDir);
        wchar_t fullPath[MAX_PATH];
        if (GetFullPathNameW(wPath.c_str(), MAX_PATH, fullPath, NULL)) {
            wchar_t fullTrusted[MAX_PATH];
            if (GetFullPathNameW(wTrusted.c_str(), MAX_PATH, fullTrusted, NULL)) {
                std::wstring fp(fullPath), ft(fullTrusted);
                for (auto& c : fp) c = (wchar_t)towlower(c);
                for (auto& c : ft) c = (wchar_t)towlower(c);
                if (fp.find(ft) != 0) {
                    setError(L"installer not in trusted directory"); return -1;
                }
            }
        }
    }

    if (callback) callback(10, "{}");  // QL_UPDATE_INSTALL_STARTED

    wchar_t cmdLine[4096];
    if (logPath && logPath[0]) {
        std::wstring wLog = toWide(logPath);
        swprintf_s(cmdLine,
            L"\"%s\" /VERYSILENT /SUPPRESSMSGBOXES /DIR=\"%s\" "
            L"/TASKS=desktopicon /MERGETASKS=!associate_qlauncher /LOG=\"%s\"",
            wPath.c_str(), wDir.c_str(), wLog.c_str());
    } else {
        swprintf_s(cmdLine,
            L"\"%s\" /VERYSILENT /SUPPRESSMSGBOXES /DIR=\"%s\" "
            L"/TASKS=desktopicon /MERGETASKS=!associate_qlauncher",
            wPath.c_str(), wDir.c_str());
    }

    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {};
    DWORD flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | 0x01000000;

    if (!CreateProcessW(NULL, cmdLine, NULL, NULL, FALSE, flags, NULL, NULL, &si, &pi)) {
        flags &= ~0x01000000;
        if (!CreateProcessW(NULL, cmdLine, NULL, NULL, FALSE, flags, NULL, NULL, &si, &pi)) {
            if (callback) callback(11, "{}");  // QL_UPDATE_INSTALL_FAILED
            setError(L"CreateProcess failed"); return -1;
        }
    }

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

// ---- version check ----

QLUPDATE_API int QLupdate_Check(const char* currentVersion,
                                 const char* updateSource,
                                 const char* configJson,
                                 QLUpdateCallback callback) {
    if (!currentVersion || !updateSource) {
        setError(L"invalid arguments"); return -1;
    }
    if (!callback) return 0;

    // Determine check URL from config
    std::string source(updateSource);
    std::string checkUrl;

    if (source == "github") {
        checkUrl = "https://api.github.com/repos/LEISHIQIANG/QuickLauncher/releases/latest";
    } else {
        if (configJson && configJson[0]) {
            // Simple JSON extraction of check_url
            std::string config(configJson);
            auto pos = config.find("\"check_url\"");
            if (pos != std::string::npos) {
                auto start = config.find('"', pos + 11);
                if (start != std::string::npos) {
                    auto end = config.find('"', start + 1);
                    if (end != std::string::npos) {
                        checkUrl = config.substr(start + 1, end - start - 1);
                    }
                }
            }
        }
        if (checkUrl.empty()) checkUrl = "https://api.leishiqiang.com/check";
    }

    std::wstring wUrl = toWide(checkUrl.c_str());

    URL_COMPONENTS urlComp = { sizeof(urlComp) };
    wchar_t hostName[256] = L"";
    wchar_t urlPath[2048] = L"";
    urlComp.lpszHostName = hostName;
    urlComp.dwHostNameLength = 255;
    urlComp.lpszUrlPath = urlPath;
    urlComp.dwUrlPathLength = 2047;

    if (!WinHttpCrackUrl(wUrl.c_str(), (DWORD)wUrl.length(), 0, &urlComp)) {
        if (callback) callback(1, "{\"errortype\":\"parse\",\"message\":\"invalid URL\"}");
        return -1;
    }

    HINTERNET hSession = WinHttpOpen(L"QuickLauncher/Update",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) {
        if (callback) callback(1, "{\"errortype\":\"network\",\"message\":\"WinHttpOpen failed\"}");
        return -1;
    }

    DWORD timeout = 15000;
    WinHttpSetOption(hSession, WINHTTP_OPTION_CONNECT_TIMEOUT, &timeout, sizeof(timeout));
    WinHttpSetOption(hSession, WINHTTP_OPTION_RECEIVE_TIMEOUT, &timeout, sizeof(timeout));

    HINTERNET hConnect = WinHttpConnect(hSession, hostName, urlComp.nPort, 0);
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", urlPath,
                                             NULL, WINHTTP_NO_REFERER,
                                             WINHTTP_DEFAULT_ACCEPT_TYPES,
                                             urlComp.nScheme == INTERNET_SCHEME_HTTPS
                                                ? WINHTTP_FLAG_SECURE : 0);

    if (!hRequest) {
        WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession);
        if (callback) callback(1, "{\"errortype\":\"network\",\"message\":\"request failed\"}");
        return -1;
    }

    if (!WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                            WINHTTP_NO_REQUEST_DATA, 0, 0, 0)) {
        WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        if (callback) callback(1, "{\"errortype\":\"network\",\"message\":\"send failed\"}");
        return -1;
    }

    if (!WinHttpReceiveResponse(hRequest, NULL)) {
        WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        if (callback) callback(1, "{\"errortype\":\"network\",\"message\":\"receive failed\"}");
        return -1;
    }

    // Read response
    std::string response;
    DWORD bytesAvail = 0;
    char buf[4096];
    while (WinHttpQueryDataAvailable(hRequest, &bytesAvail) && bytesAvail > 0) {
        DWORD bytesRead = 0;
        DWORD toRead = (bytesAvail < (DWORD)sizeof(buf)) ? bytesAvail : (DWORD)sizeof(buf);
        if (WinHttpReadData(hRequest, buf, toRead, &bytesRead))
            response.append(buf, bytesRead);
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);

    if (response.empty()) {
        if (callback) callback(1, "{\"errortype\":\"network\",\"message\":\"empty response\"}");
        return -1;
    }

    // Simple JSON version extraction from GitHub
    std::string latestVersion;
    std::string downloadUrl;
    auto tagPos = response.find("\"tag_name\"");
    if (tagPos != std::string::npos) {
        auto vStart = response.find('"', tagPos + 10);
        if (vStart != std::string::npos) {
            auto vEnd = response.find('"', vStart + 1);
            if (vEnd != std::string::npos) {
                latestVersion = response.substr(vStart + 1, vEnd - vStart - 1);
                if (latestVersion.size() > 0 && latestVersion[0] == 'v' || latestVersion[0] == 'V')
                    latestVersion = latestVersion.substr(1);
            }
        }
    }

    char resultJson[1024];
    if (latestVersion.empty()) {
        if (callback) callback(2, "{\"message\":\"up_to_date\"}");
        return 0;
    }

    snprintf(resultJson, sizeof(resultJson),
        "{\"current_version\":\"%s\",\"latest_version\":\"%s\",\"has_update\":%s}",
        currentVersion, latestVersion.c_str(),
        (strcmp(latestVersion.c_str(), currentVersion) != 0) ? "true" : "false");

    int event = (strcmp(latestVersion.c_str(), currentVersion) == 0) ? 2 : 3;
    callback(event, resultJson);
    return 0;
}
