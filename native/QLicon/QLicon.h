#pragma once

#ifdef QLICON_EXPORTS
#define QLICON_API __declspec(dllexport)
#else
#define QLICON_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

struct QLIconOptions {
    int size;
    int flags;
    int iconIndex;
};

#define QL_ICON_FLAG_LARGE   0x01
#define QL_ICON_FLAG_OVERLAY 0x02
#define QL_ICON_FLAG_DEFAULT 0x04

struct QLIconResult {
    int width;
    int height;
    int channels;
    int pixelCount;
};

QLICON_API int  QLicon_version(void);
QLICON_API const wchar_t* QLicon_lastError(void);

QLICON_API int  QLicon_ExtractFromFile(const wchar_t* filePath,
                                        const QLIconOptions* options,
                                        unsigned char* outRgba,
                                        QLIconResult* outResult);

QLICON_API int  QLicon_ExtractFromResource(const wchar_t* filePath,
                                             int iconIndex,
                                             int size,
                                             unsigned char* outRgba,
                                             int* outWidth,
                                             int* outHeight);

QLICON_API int  QLicon_LoadImageFile(const wchar_t* imagePath,
                                      int size,
                                      unsigned char* outRgba,
                                      int* outWidth,
                                      int* outHeight);

QLICON_API int  QLicon_IsEmpty(const unsigned char* rgba,
                                int width, int height);

QLICON_API int  QLicon_GetFileTypeName(const wchar_t* filePath,
                                        wchar_t* outBuffer,
                                        int bufferSize);

#ifdef __cplusplus
}
#endif
