#define QLWATCH_EXPORTS
#include "QLwatch.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <atomic>
#include <thread>
#include <mutex>

static thread_local wchar_t g_lastError[512] = L"";

static void setError(const wchar_t* msg) {
    wcsncpy_s(g_lastError, msg ? msg : L"", _TRUNCATE);
}

QLWATCH_API int  QLwatch_version(void) { return 1; }
QLWATCH_API const wchar_t* QLwatch_lastError(void) { return g_lastError; }

// ---- internal state ----

static HANDLE g_hIOCP = NULL;
static std::thread g_workerThread;
static std::atomic<bool> g_running{false};

struct WatchEntry {
    std::string folderId;
    HANDLE hDir;
    OVERLAPPED overlapped;
    BYTE buffer[64 * 1024];
    QLWatchCallback callback;
    double lastTriggerTime;
};

static std::unordered_map<std::string, std::unique_ptr<WatchEntry>> g_watches;
static std::mutex g_watchesMutex;
static LARGE_INTEGER g_perfFreq;

static double nowSec() {
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return (double)t.QuadPart / (double)g_perfFreq.QuadPart;
}

static void processChanges(WatchEntry* entry, DWORD bytesTransferred) {
    double now = nowSec();
    if (now - entry->lastTriggerTime < 2.0) return;
    entry->lastTriggerTime = now;
    if (entry->callback) entry->callback(entry->folderId.c_str());
}

static void beginRead(WatchEntry* entry) {
    entry->overlapped = {};
    ReadDirectoryChangesW(
        entry->hDir,
        entry->buffer, sizeof(entry->buffer),
        FALSE, // non-recursive
        FILE_NOTIFY_CHANGE_FILE_NAME
        | FILE_NOTIFY_CHANGE_DIR_NAME
        | FILE_NOTIFY_CHANGE_SIZE
        | FILE_NOTIFY_CHANGE_LAST_WRITE,
        NULL, &entry->overlapped, NULL);
}

static void iocpWorker() {
    while (g_running) {
        DWORD bytesTransferred = 0;
        ULONG_PTR completionKey = 0;
        LPOVERLAPPED lpOverlapped = NULL;

        BOOL ok = GetQueuedCompletionStatus(
            g_hIOCP, &bytesTransferred, &completionKey, &lpOverlapped, 500);

        if (!lpOverlapped) continue;

        WatchEntry* entry = CONTAINING_RECORD(lpOverlapped, WatchEntry, overlapped);

        if (!ok || bytesTransferred == 0) continue;

        processChanges(entry, bytesTransferred);
        beginRead(entry);
    }
}

QLWATCH_API int QLwatch_Init(void) {
    if (g_hIOCP) return 0;
    QueryPerformanceFrequency(&g_perfFreq);
    g_hIOCP = CreateIoCompletionPort(INVALID_HANDLE_VALUE, NULL, 0, 1);
    if (!g_hIOCP) { setError(L"CreateIoCompletionPort failed"); return -1; }
    g_running = true;
    g_workerThread = std::thread(iocpWorker);
    return 0;
}

QLWATCH_API void QLwatch_Release(void) {
    g_running = false;
    if (g_workerThread.joinable()) g_workerThread.join();

    {
        std::lock_guard<std::mutex> lock(g_watchesMutex);
        for (auto& [id, entry] : g_watches) {
            CancelIo(entry->hDir);
            CloseHandle(entry->hDir);
        }
        g_watches.clear();
    }
    if (g_hIOCP) { CloseHandle(g_hIOCP); g_hIOCP = NULL; }
}

QLWATCH_API int QLwatch_Start(const char* folderId,
                               const wchar_t* path,
                               QLWatchCallback callback) {
    if (!g_hIOCP) { setError(L"QLwatch not initialized"); return -1; }
    if (!folderId || !path || !callback) { setError(L"invalid arguments"); return -1; }

    QLwatch_Stop(folderId);

    HANDLE hDir = CreateFileW(
        path,
        FILE_LIST_DIRECTORY,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL, OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
        NULL);

    if (hDir == INVALID_HANDLE_VALUE) {
        setError(L"failed to open directory");
        return -2;
    }

    if (!CreateIoCompletionPort(hDir, g_hIOCP, 0, 0)) {
        CloseHandle(hDir);
        setError(L"CreateIoCompletionPort association failed");
        return -2;
    }

    auto entry = std::make_unique<WatchEntry>();
    entry->folderId = folderId;
    entry->hDir = hDir;
    entry->callback = callback;
    entry->lastTriggerTime = 0;
    beginRead(entry.get());

    {
        std::lock_guard<std::mutex> lock(g_watchesMutex);
        g_watches[folderId] = std::move(entry);
    }
    return 0;
}

QLWATCH_API int QLwatch_Stop(const char* folderId) {
    std::unique_ptr<WatchEntry> entry;
    {
        std::lock_guard<std::mutex> lock(g_watchesMutex);
        auto it = g_watches.find(folderId);
        if (it == g_watches.end()) return -1;
        entry = std::move(it->second);
        g_watches.erase(it);
    }
    CancelIo(entry->hDir);
    CloseHandle(entry->hDir);
    return 0;
}

QLWATCH_API void QLwatch_StopAll(void) {
    std::lock_guard<std::mutex> lock(g_watchesMutex);
    for (auto& [id, entry] : g_watches) {
        CancelIo(entry->hDir);
        CloseHandle(entry->hDir);
    }
    g_watches.clear();
}
