#define QLCRYPTO_EXPORTS
#define NOMINMAX
#include "QLcrypto.h"

#include <windows.h>
#include <bcrypt.h>
#include <string>
#include <vector>
#include <mutex>
#include <cstring>
#include <cstdio>
#include <cstdarg>

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "kernel32.lib")

// ---------------------------------------------------------------------------
// Thread-local last-error message
// ---------------------------------------------------------------------------

static thread_local std::string g_lastError;

static void set_last_error(const char* fmt, ...) {
    char buf[512];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    g_lastError = buf;
}

// ---------------------------------------------------------------------------
// Algorithm provider cache (thread-safe, call_once)
// ---------------------------------------------------------------------------

struct AlgoProvider {
    BCRYPT_ALG_HANDLE handle = nullptr;
    DWORD hashLength = 0;
    bool valid = false;
};

static AlgoProvider g_md5, g_sha1, g_sha256;
static std::once_flag g_algoInitFlag;

static bool init_algo(AlgoProvider& ap, LPCWSTR algoId) {
    NTSTATUS status = BCryptOpenAlgorithmProvider(&ap.handle, algoId, nullptr, 0);
    if (status != 0) {
        set_last_error("BCryptOpenAlgorithmProvider failed: 0x%08X", (unsigned)status);
        return false;
    }
    DWORD hashLen = 0;
    DWORD cbResult = 0;
    status = BCryptGetProperty(ap.handle, BCRYPT_HASH_LENGTH,
                               reinterpret_cast<PUCHAR>(&hashLen), sizeof(hashLen), &cbResult, 0);
    if (status != 0) {
        BCryptCloseAlgorithmProvider(ap.handle, 0);
        ap.handle = nullptr;
        set_last_error("BCryptGetProperty(hash_length) failed: 0x%08X", (unsigned)status);
        return false;
    }
    ap.hashLength = hashLen;
    ap.valid = true;
    return true;
}

static void init_algos() {
    std::call_once(g_algoInitFlag, []() {
        init_algo(g_md5, BCRYPT_MD5_ALGORITHM);
        init_algo(g_sha1, BCRYPT_SHA1_ALGORITHM);
        init_algo(g_sha256, BCRYPT_SHA256_ALGORITHM);
    });
}

static AlgoProvider* select_algo(const char* algorithm) {
    if (!algorithm) return nullptr;
    if (_stricmp(algorithm, "md5") == 0)    return g_md5.valid    ? &g_md5    : nullptr;
    if (_stricmp(algorithm, "sha1") == 0)   return g_sha1.valid   ? &g_sha1   : nullptr;
    if (_stricmp(algorithm, "sha256") == 0) return g_sha256.valid ? &g_sha256 : nullptr;
    return nullptr;
}

// ---------------------------------------------------------------------------
// Path conversion: UTF-8 -> wide, with long-path prefix
// ---------------------------------------------------------------------------

static std::wstring utf8_to_wide(const char* utf8) {
    if (!utf8 || !utf8[0]) return L"";
    int len = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, nullptr, 0);
    if (len <= 0) return L"";
    std::wstring wide(static_cast<size_t>(len), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, utf8, -1, wide.data(), len);
    if (!wide.empty() && wide.back() == L'\0') wide.pop_back();
    return wide;
}

static std::wstring make_long_path(const std::wstring& path) {
    if (path.empty()) return path;
    if (path.size() >= 4 &&
        path[0] == L'\\' && path[1] == L'\\' &&
        path[2] == L'?'  && path[3] == L'\\') {
        return path;
    }
    if (path.size() >= 2 && ((path[1] == L':' && path.size() > MAX_PATH) ||
                              path.size() > MAX_PATH)) {
        return L"\\\\?\\" + path;
    }
    return path;
}

// ---------------------------------------------------------------------------
// Hex encoding
// ---------------------------------------------------------------------------

static void bytes_to_hex_lower(const unsigned char* src, size_t len, char* dst) {
    static const char hex[] = "0123456789abcdef";
    for (size_t i = 0; i < len; ++i) {
        dst[i * 2]     = hex[src[i] >> 4];
        dst[i * 2 + 1] = hex[src[i] & 0x0F];
    }
    dst[len * 2] = '\0';
}

// ---------------------------------------------------------------------------
// Core implementation
// ---------------------------------------------------------------------------

static int hash_file_internal(const char* pathUtf8, const char* algorithm,
                              unsigned long long maxBytes,
                              char* outHex, unsigned int outLen) {
    if (!pathUtf8 || !pathUtf8[0] || !algorithm || !outHex) {
        set_last_error("invalid argument: null pointer");
        return QLCRYPTO_ERR_INVALID_ARG;
    }

    init_algos();
    AlgoProvider* algo = select_algo(algorithm);
    if (!algo) {
        set_last_error("unsupported algorithm: %s", algorithm);
        return QLCRYPTO_ERR_UNSUPPORTED;
    }

    size_t hexLen = static_cast<size_t>(algo->hashLength) * 2 + 1;
    if (outLen < hexLen) {
        set_last_error("output buffer too small: need %zu, got %u", hexLen, outLen);
        return QLCRYPTO_ERR_BUFFER;
    }

    std::wstring widePath = utf8_to_wide(pathUtf8);
    if (widePath.empty()) {
        set_last_error("path conversion failed");
        return QLCRYPTO_ERR_INVALID_ARG;
    }
    std::wstring longPath = make_long_path(widePath);

    HANDLE hFile = CreateFileW(
        longPath.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (hFile == INVALID_HANDLE_VALUE) {
        set_last_error("CreateFileW failed: error %lu (path: %s)", GetLastError(), pathUtf8);
        return QLCRYPTO_ERR_FILE_OPEN;
    }

    struct FileCloser {
        HANDLE h;
        ~FileCloser() { if (h != INVALID_HANDLE_VALUE) CloseHandle(h); }
    } fileCloser{hFile};

    BCRYPT_HASH_HANDLE hHash = nullptr;
    NTSTATUS status = BCryptCreateHash(algo->handle, &hHash, nullptr, 0, nullptr, 0, 0);
    if (status != 0) {
        set_last_error("BCryptCreateHash failed: 0x%08X", (unsigned)status);
        return QLCRYPTO_ERR_INTERNAL;
    }

    struct HashCloser {
        BCRYPT_HASH_HANDLE h;
        ~HashCloser() { if (h) BCryptDestroyHash(h); }
    } hashCloser{hHash};

    constexpr DWORD kBufSize = 4 * 1024 * 1024;
    std::vector<unsigned char> buffer(kBufSize);
    unsigned long long totalRead = 0;

    for (;;) {
        DWORD toRead = kBufSize;
        if (maxBytes > 0) {
            unsigned long long remaining = maxBytes - totalRead;
            if (remaining == 0) break;
            if (remaining < kBufSize) toRead = static_cast<DWORD>(remaining);
        }

        DWORD bytesRead = 0;
        BOOL ok = ReadFile(hFile, buffer.data(), toRead, &bytesRead, nullptr);
        if (!ok) {
            set_last_error("ReadFile failed: error %lu", GetLastError());
            return QLCRYPTO_ERR_FILE_READ;
        }
        if (bytesRead == 0) break;

        status = BCryptHashData(hHash, buffer.data(), bytesRead, 0);
        if (status != 0) {
            set_last_error("BCryptHashData failed: 0x%08X", (unsigned)status);
            return QLCRYPTO_ERR_INTERNAL;
        }

        totalRead += bytesRead;
        if (maxBytes > 0 && totalRead >= maxBytes) break;
    }

    std::vector<unsigned char> digest(algo->hashLength);
    status = BCryptFinishHash(hHash, digest.data(), static_cast<ULONG>(digest.size()), 0);
    if (status != 0) {
        set_last_error("BCryptFinishHash failed: 0x%08X", (unsigned)status);
        return QLCRYPTO_ERR_INTERNAL;
    }

    bytes_to_hex_lower(digest.data(), digest.size(), outHex);
    return QLCRYPTO_OK;
}

// ---------------------------------------------------------------------------
// Exported functions
// ---------------------------------------------------------------------------

extern "C" {

QLCRYPTO_API int QLcrypto_hashFile(const char* path,
                                   const char* algorithm,
                                   unsigned long long max_bytes,
                                   char* out_hex,
                                   unsigned int out_len) {
    return hash_file_internal(path, algorithm, max_bytes, out_hex, out_len);
}

QLCRYPTO_API int QLcrypto_version(void) {
    return 1;
}

QLCRYPTO_API const char* QLcrypto_lastError(void) {
    if (g_lastError.empty()) return "";
    return g_lastError.c_str();
}

} // extern "C"
