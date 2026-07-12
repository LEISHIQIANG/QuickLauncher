#define QLCLIPBOARD_EXPORTS
#include "QLclipboard.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <objbase.h>
#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <cstring>
#include <cstdio>

// ---- error handling ----

static thread_local wchar_t g_lastError[512] = L"";

static void setError(const wchar_t* msg) {
    wcsncpy_s(g_lastError, msg ? msg : L"", _TRUNCATE);
}

QLCLIPBOARD_API int QLclipboard_version(void) { return 1; }
QLCLIPBOARD_API const wchar_t* QLclipboard_lastError(void) { return g_lastError; }

// ---- COM init ----

QLCLIPBOARD_API int QLclipboard_EnsureComInit(void) {
    HRESULT hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (hr == S_OK || hr == S_FALSE) return 0;
    if (hr == RPC_E_CHANGED_MODE) return 0;
    setError(L"CoInitializeEx failed");
    return -1;
}

// ---- retry logic ----

static bool openClipboardWithRetry(HWND owner) {
    static const int delays[] = {10, 20, 50, 100, 100, 100, 200, 200};
    for (int i = 0; i < 8; i++) {
        if (OpenClipboard(owner)) return true;
        if (i < 7) Sleep(delays[i]);
    }
    return false;
}

// ---- text read/write ----

QLCLIPBOARD_API int QLclipboard_ReadText(wchar_t* outBuffer, int bufferSize) {
    if (!outBuffer || bufferSize <= 0) {
        setError(L"invalid buffer");
        return -1;
    }
    if (!openClipboardWithRetry(NULL)) {
        setError(L"OpenClipboard failed");
        return -1;
    }
    HANDLE hData = GetClipboardData(CF_UNICODETEXT);
    if (!hData) {
        CloseClipboard();
        return -1;
    }
    const wchar_t* pData = (const wchar_t*)GlobalLock(hData);
    if (!pData) {
        CloseClipboard();
        return -1;
    }
    int len = 0;
    while (pData[len] && len < bufferSize - 1) {
        outBuffer[len] = pData[len];
        len++;
    }
    outBuffer[len] = L'\0';
    GlobalUnlock(hData);
    CloseClipboard();
    return len;
}

QLCLIPBOARD_API int QLclipboard_WriteText(const wchar_t* text) {
    if (!text) {
        setError(L"null text");
        return -1;
    }
    size_t len = wcslen(text);
    size_t bytes = (len + 1) * sizeof(wchar_t);
    HGLOBAL hMem = GlobalAlloc(GMEM_MOVEABLE, bytes);
    if (!hMem) {
        setError(L"GlobalAlloc failed");
        return -1;
    }
    wchar_t* pMem = (wchar_t*)GlobalLock(hMem);
    if (!pMem) {
        GlobalFree(hMem);
        setError(L"GlobalLock failed");
        return -1;
    }
    wcscpy_s(pMem, len + 1, text);
    GlobalUnlock(hMem);

    if (!openClipboardWithRetry(NULL)) {
        GlobalFree(hMem);
        setError(L"OpenClipboard failed");
        return -1;
    }
    EmptyClipboard();
    if (!SetClipboardData(CF_UNICODETEXT, hMem)) {
        GlobalFree(hMem);
        CloseClipboard();
        setError(L"SetClipboardData failed");
        return -1;
    }
    CloseClipboard();
    return 0;
}

// ---- snapshot ----

struct ClipboardSnapshot {
    std::vector<std::pair<int, std::vector<unsigned char>>> entries;
    std::vector<std::wstring> formatNames;
};

static std::unordered_map<int, std::unique_ptr<ClipboardSnapshot>> g_snapshots;
static int g_nextSnapshotId = 1;

QLCLIPBOARD_API int QLclipboard_CreateSnapshot(int* outSnapshotId,
                                                int* outEntryCount) {
    if (!outSnapshotId || !outEntryCount) {
        setError(L"null output pointer");
        return -1;
    }
    if (!openClipboardWithRetry(NULL)) {
        setError(L"OpenClipboard failed");
        return -2;
    }

    auto snapshot = std::make_unique<ClipboardSnapshot>();
    UINT format = 0;
    while ((format = EnumClipboardFormats(format)) != 0) {
        HANDLE hData = GetClipboardData(format);
        if (!hData) continue;

        void* pData = GlobalLock(hData);
        if (!pData) continue;

        SIZE_T size = GlobalSize(hData);
        std::vector<unsigned char> dataCopy(
            static_cast<unsigned char*>(pData),
            static_cast<unsigned char*>(pData) + size);
        GlobalUnlock(hData);

        // Get format name
        wchar_t nameBuf[256] = L"";
        GetClipboardFormatNameW(format, nameBuf, 255);

        snapshot->entries.emplace_back(static_cast<int>(format), std::move(dataCopy));
        snapshot->formatNames.push_back(nameBuf);
    }
    CloseClipboard();

    int id = g_nextSnapshotId++;
    *outSnapshotId = id;
    *outEntryCount = (int)snapshot->entries.size();
    g_snapshots[id] = std::move(snapshot);
    return 0;
}

QLCLIPBOARD_API int QLclipboard_GetSnapshotEntry(int snapshotId,
                                                   int entryIndex,
                                                   int* outFormatId,
                                                   unsigned char* outData,
                                                   int dataBufferSize) {
    auto it = g_snapshots.find(snapshotId);
    if (it == g_snapshots.end()) {
        setError(L"invalid snapshot id");
        return -1;
    }
    auto& snapshot = *it->second;
    if (entryIndex < 0 || entryIndex >= (int)snapshot.entries.size()) {
        setError(L"invalid entry index");
        return -1;
    }
    auto& [formatId, data] = snapshot.entries[entryIndex];
    *outFormatId = formatId;
    int dataSize = (int)data.size();
    if (outData) {
        int copySize = std::min(dataSize, dataBufferSize);
        if (copySize < dataSize) {
            setError(L"buffer too small");
            return -2;
        }
        memcpy(outData, data.data(), dataSize);
    }
    return dataSize;
}

QLCLIPBOARD_API int QLclipboard_GetSnapshotEntryName(int snapshotId,
                                                       int entryIndex,
                                                       wchar_t* outName,
                                                       int nameBufferSize) {
    auto it = g_snapshots.find(snapshotId);
    if (it == g_snapshots.end()) {
        setError(L"invalid snapshot id");
        return -1;
    }
    auto& snapshot = *it->second;
    if (entryIndex < 0 || entryIndex >= (int)snapshot.formatNames.size()) {
        setError(L"invalid entry index");
        return -1;
    }
    if (!outName || nameBufferSize <= 0) return -1;
    int len = (int)snapshot.formatNames[entryIndex].length();
    wcsncpy_s(outName, nameBufferSize, snapshot.formatNames[entryIndex].c_str(), _TRUNCATE);
    return len;
}

QLCLIPBOARD_API int QLclipboard_RestoreSnapshot(int snapshotId) {
    auto it = g_snapshots.find(snapshotId);
    if (it == g_snapshots.end()) {
        setError(L"invalid snapshot id");
        return -1;
    }
    auto& snapshot = *it->second;

    if (!openClipboardWithRetry(NULL)) {
        setError(L"OpenClipboard failed");
        return -1;
    }
    EmptyClipboard();

    for (auto& [format, data] : snapshot.entries) {
        SIZE_T size = data.size();
        if (size == 0) continue;
        HGLOBAL hMem = GlobalAlloc(GMEM_MOVEABLE, size);
        if (!hMem) continue;

        void* pMem = GlobalLock(hMem);
        memcpy(pMem, data.data(), size);
        GlobalUnlock(hMem);

        SetClipboardData(format, hMem);
    }
    CloseClipboard();
    return 0;
}

QLCLIPBOARD_API void QLclipboard_FreeSnapshot(int snapshotId) {
    g_snapshots.erase(snapshotId);
}

// ---- format enumeration ----

QLCLIPBOARD_API int QLclipboard_EnumFormats(QLClipboardFormatInfo* outFormats,
                                             int maxFormats) {
    if (!outFormats || maxFormats <= 0) {
        setError(L"invalid buffer");
        return -1;
    }
    if (!openClipboardWithRetry(NULL)) {
        setError(L"OpenClipboard failed");
        return -1;
    }
    UINT format = 0;
    int count = 0;
    while ((format = EnumClipboardFormats(format)) != 0 && count < maxFormats) {
        outFormats[count].formatId = (int)format;
        wchar_t nameBuf[128] = L"";
        GetClipboardFormatNameW(format, nameBuf, 127);
        WideCharToMultiByte(CP_UTF8, 0, nameBuf, -1,
                           outFormats[count].name, 128, NULL, NULL);
        count++;
    }
    CloseClipboard();
    return count;
}

// ---- sequence number ----

QLCLIPBOARD_API int QLclipboard_GetSequenceNumber(int* outSeqNum) {
    if (!outSeqNum) { setError(L"null output"); return -1; }
    *outSeqNum = (int)GetClipboardSequenceNumber();
    return 0;
}

// ---- HTML format helper ----

QLCLIPBOARD_API int QLclipboard_BuildHtmlFormat(const char* htmlContent,
                                                 char* outBuffer,
                                                 int bufferSize) {
    if (!htmlContent || !outBuffer || bufferSize <= 0) {
        setError(L"invalid arguments");
        return -1;
    }
    static const char* header =
        "Version:0.9\r\n"
        "StartHTML:%010u\r\n"
        "EndHTML:%010u\r\n"
        "StartFragment:%010u\r\n"
        "EndFragment:%010u\r\n";
    static const char* prefix = "<html><body><!--StartFragment-->";
    static const char* suffix = "<!--EndFragment--></body></html>";

    char headerBuf[256];
    int headerLen = snprintf(headerBuf, sizeof(headerBuf), header,
                             0u, 0u, 0u, 0u);
    int prefixLen = (int)strlen(prefix);
    int contentLen = (int)strlen(htmlContent);
    int suffixLen = (int)strlen(suffix);

    int startHtml = 0;
    int endHtml = headerLen + prefixLen + contentLen + suffixLen;
    int startFragment = headerLen + prefixLen;
    int endFragment = startFragment + contentLen;

    int totalLen = endHtml;
    if (totalLen + 1 > bufferSize) {
        setError(L"buffer too small");
        return -1;
    }

    snprintf(outBuffer, bufferSize, header,
             (unsigned int)startHtml,
             (unsigned int)endHtml,
             (unsigned int)startFragment,
             (unsigned int)endFragment);
    memcpy(outBuffer + headerLen, prefix, prefixLen);
    memcpy(outBuffer + headerLen + prefixLen, htmlContent, contentLen);
    memcpy(outBuffer + headerLen + prefixLen + contentLen, suffix, suffixLen);
    outBuffer[totalLen] = '\0';
    return totalLen;
}
