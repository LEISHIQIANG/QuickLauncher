#pragma once

#ifdef QLCLIPBOARD_EXPORTS
#define QLCLIPBOARD_API __declspec(dllexport)
#else
#define QLCLIPBOARD_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

struct QLClipboardFormatInfo {
    int formatId;
    char name[128];
};

QLCLIPBOARD_API int  QLclipboard_version(void);
QLCLIPBOARD_API const wchar_t* QLclipboard_lastError(void);

QLCLIPBOARD_API int  QLclipboard_EnsureComInit(void);

QLCLIPBOARD_API int  QLclipboard_ReadText(wchar_t* outBuffer,
                                           int bufferSize);
QLCLIPBOARD_API int  QLclipboard_WriteText(const wchar_t* text);

QLCLIPBOARD_API int  QLclipboard_CreateSnapshot(int* outSnapshotId,
                                                 int* outEntryCount);
QLCLIPBOARD_API int  QLclipboard_GetSnapshotEntry(int snapshotId,
                                                    int entryIndex,
                                                    int* outFormatId,
                                                    unsigned char* outData,
                                                    int dataBufferSize);
QLCLIPBOARD_API int  QLclipboard_GetSnapshotEntryName(int snapshotId,
                                                        int entryIndex,
                                                        wchar_t* outName,
                                                        int nameBufferSize);
QLCLIPBOARD_API int  QLclipboard_RestoreSnapshot(int snapshotId);
QLCLIPBOARD_API void QLclipboard_FreeSnapshot(int snapshotId);

QLCLIPBOARD_API int  QLclipboard_EnumFormats(QLClipboardFormatInfo* outFormats,
                                              int maxFormats);

QLCLIPBOARD_API int  QLclipboard_GetSequenceNumber(int* outSeqNum);

QLCLIPBOARD_API int  QLclipboard_BuildHtmlFormat(const char* htmlContent,
                                                  char* outBuffer,
                                                  int bufferSize);

#ifdef __cplusplus
}
#endif
