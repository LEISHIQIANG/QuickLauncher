#define QLICON_EXPORTS
#include "QLicon.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>
#include <string>
#include <cstring>

static thread_local wchar_t g_lastError[512] = L"";

static void setError(const wchar_t* msg) {
    wcsncpy_s(g_lastError, msg ? msg : L"", _TRUNCATE);
}

QLICON_API int QLicon_version(void) { return 1; }
QLICON_API const wchar_t* QLicon_lastError(void) { return g_lastError; }

static std::wstring getLowerExtension(const wchar_t* path) {
    std::wstring s(path);
    auto dot = s.rfind(L'.');
    if (dot == std::wstring::npos) return L"";
    std::wstring ext = s.substr(dot);
    for (auto& c : ext) c = (wchar_t)towlower(c);
    return ext;
}

static void unpremultiplyAlpha(unsigned char* rgba, int pixelCount) {
    for (int i = 0; i < pixelCount; i++) {
        unsigned char* p = rgba + i * 4;
        unsigned char a = p[3];
        if (a == 0) {
            p[0] = p[1] = p[2] = 0;
        } else if (a < 255) {
            p[0] = (unsigned char)((int)p[0] * 255 / a);
            p[1] = (unsigned char)((int)p[1] * 255 / a);
            p[2] = (unsigned char)((int)p[2] * 255 / a);
        }
    }
}

static int hiconToRgba(HICON hIcon, int targetSize,
                       unsigned char* rgba, int* outWidth, int* outHeight) {
    ICONINFO iconInfo;
    if (!GetIconInfo(hIcon, &iconInfo)) return -3;

    BITMAP bm;
    if (!GetObjectW(iconInfo.hbmColor, sizeof(bm), &bm)) {
        if (iconInfo.hbmColor) DeleteObject(iconInfo.hbmColor);
        if (iconInfo.hbmMask) DeleteObject(iconInfo.hbmMask);
        return -3;
    }

    *outWidth = bm.bmWidth;
    *outHeight = bm.bmHeight;

    BITMAPINFO bmi = {};
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bmi.bmiHeader.biWidth = bm.bmWidth;
    bmi.bmiHeader.biHeight = -bm.bmHeight;
    bmi.bmiHeader.biPlanes = 1;
    bmi.bmiHeader.biBitCount = 32;
    bmi.bmiHeader.biCompression = BI_RGB;

    HDC hdc = GetDC(NULL);
    int pixelCount = bm.bmWidth * bm.bmHeight;
    GetDIBits(hdc, iconInfo.hbmColor, 0, bm.bmHeight, rgba, &bmi, DIB_RGB_COLORS);
    ReleaseDC(NULL, hdc);

    unpremultiplyAlpha(rgba, pixelCount);

    if (iconInfo.hbmColor) DeleteObject(iconInfo.hbmColor);
    if (iconInfo.hbmMask) DeleteObject(iconInfo.hbmMask);
    return 0;
}

QLICON_API int QLicon_ExtractFromFile(const wchar_t* filePath,
                                       const QLIconOptions* options,
                                       unsigned char* outRgba,
                                       QLIconResult* outResult) {
    if (!filePath || !options || !outRgba || !outResult) {
        setError(L"invalid arguments"); return -1;
    }
    if (GetFileAttributesW(filePath) == INVALID_FILE_ATTRIBUTES) {
        setError(L"file not found"); return -1;
    }

    std::wstring ext = getLowerExtension(filePath);

    if (ext == L".png" || ext == L".jpg" || ext == L".jpeg" || ext == L".bmp") {
        int w, h;
        int rc = QLicon_LoadImageFile(filePath, options->size, outRgba, &w, &h);
        if (rc == 0) {
            outResult->width = w;
            outResult->height = h;
            outResult->channels = 4;
            outResult->pixelCount = w * h;
            return 0;
        }
    }

    if (ext == L".exe" || ext == L".dll") {
        HICON hIcon = NULL;
        if (PrivateExtractIconsW(filePath, options->iconIndex,
                                 options->size, options->size,
                                 &hIcon, NULL, 1, 0) > 0 && hIcon) {
            int w, h;
            int ret = hiconToRgba(hIcon, options->size, outRgba, &w, &h);
            DestroyIcon(hIcon);
            if (ret == 0) {
                outResult->width = w;
                outResult->height = h;
                outResult->channels = 4;
                outResult->pixelCount = w * h;
                return 0;
            }
        }
        HICON hIcon2 = ExtractIconW(NULL, filePath, options->iconIndex);
        if (hIcon2 && hIcon2 != (HICON)1) {
            int w, h;
            int ret = hiconToRgba(hIcon2, options->size, outRgba, &w, &h);
            DestroyIcon(hIcon2);
            if (ret == 0) {
                outResult->width = w;
                outResult->height = h;
                outResult->channels = 4;
                outResult->pixelCount = w * h;
                return 0;
            }
        }
    }

    SHFILEINFOW sfi = {};
    DWORD flags = SHGFI_ICON | SHGFI_USEFILEATTRIBUTES;
    if (options->flags & QL_ICON_FLAG_LARGE) flags |= SHGFI_LARGEICON;
    if (!SHGetFileInfoW(filePath, FILE_ATTRIBUTE_NORMAL, &sfi, sizeof(sfi), flags)) {
        if (options->flags & QL_ICON_FLAG_DEFAULT) {
            flags |= SHGFI_USEFILEATTRIBUTES;
            if (!SHGetFileInfoW(L".txt", FILE_ATTRIBUTE_NORMAL, &sfi, sizeof(sfi), flags)) {
                setError(L"no icon available");
                return -2;
            }
        } else {
            setError(L"no icon available");
            return -2;
        }
    }

    int w, h;
    int ret = hiconToRgba(sfi.hIcon, options->size, outRgba, &w, &h);
    DestroyIcon(sfi.hIcon);

    if (ret == 0) {
        outResult->width = w;
        outResult->height = h;
        outResult->channels = 4;
        outResult->pixelCount = w * h;
        return 0;
    }
    setError(L"hicon to rgba failed");
    return -2;
}

QLICON_API int QLicon_ExtractFromResource(const wchar_t* filePath,
                                            int iconIndex,
                                            int size,
                                            unsigned char* outRgba,
                                            int* outWidth,
                                            int* outHeight) {
    if (!filePath || !outRgba || !outWidth || !outHeight) {
        setError(L"invalid arguments"); return -1;
    }
    HICON hIcon = NULL;
    if (PrivateExtractIconsW(filePath, iconIndex, size, size,
                             &hIcon, NULL, 1, 0) > 0 && hIcon) {
        int ret = hiconToRgba(hIcon, size, outRgba, outWidth, outHeight);
        DestroyIcon(hIcon);
        if (ret == 0) return 0;
    }
    HICON hIcon2 = ExtractIconW(NULL, filePath, iconIndex);
    if (hIcon2 && hIcon2 != (HICON)1) {
        int ret = hiconToRgba(hIcon2, size, outRgba, outWidth, outHeight);
        DestroyIcon(hIcon2);
        if (ret == 0) return 0;
    }
    setError(L"no icon in resource");
    return -2;
}

QLICON_API int QLicon_LoadImageFile(const wchar_t* imagePath,
                                     int size,
                                     unsigned char* outRgba,
                                     int* outWidth,
                                     int* outHeight) {
    if (!imagePath || !outRgba || !outWidth || !outHeight) {
        setError(L"invalid arguments"); return -1;
    }
    if (GetFileAttributesW(imagePath) == INVALID_FILE_ATTRIBUTES) {
        setError(L"file not found"); return -1;
    }

    // Use GDI+ via LoadImage for simple image loading
    HANDLE hImage = LoadImageW(NULL, imagePath, IMAGE_BITMAP,
                                size > 0 ? size : 0,
                                size > 0 ? size : 0,
                                LR_LOADFROMFILE | LR_CREATEDIBSECTION);
    if (!hImage) {
        setError(L"LoadImage failed");
        return -3;
    }

    HBITMAP hBitmap = (HBITMAP)hImage;
    BITMAP bm;
    if (!GetObjectW(hBitmap, sizeof(bm), &bm)) {
        DeleteObject(hBitmap);
        return -3;
    }

    *outWidth = bm.bmWidth;
    *outHeight = bm.bmHeight;

    BITMAPINFO bmi = {};
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bmi.bmiHeader.biWidth = bm.bmWidth;
    bmi.bmiHeader.biHeight = -bm.bmHeight;
    bmi.bmiHeader.biPlanes = 1;
    bmi.bmiHeader.biBitCount = 32;
    bmi.bmiHeader.biCompression = BI_RGB;

    HDC hdc = GetDC(NULL);
    GetDIBits(hdc, hBitmap, 0, bm.bmHeight, outRgba, &bmi, DIB_RGB_COLORS);
    ReleaseDC(NULL, hdc);
    DeleteObject(hBitmap);
    return 0;
}

QLICON_API int QLicon_IsEmpty(const unsigned char* rgba,
                               int width, int height) {
    if (!rgba || width <= 0 || height <= 0) return 1;
    int stride = 8;
    for (int y = 0; y < height; y += stride) {
        for (int x = 0; x < width; x += stride) {
            int idx = (y * width + x) * 4;
            if (rgba[idx + 3] > 0) return 0;
        }
    }
    return 1;
}

QLICON_API int QLicon_GetFileTypeName(const wchar_t* filePath,
                                       wchar_t* outBuffer,
                                       int bufferSize) {
    if (!filePath || !outBuffer || bufferSize <= 0) {
        setError(L"invalid arguments"); return -1;
    }
    SHFILEINFOW sfi = {};
    if (!SHGetFileInfoW(filePath, FILE_ATTRIBUTE_NORMAL, &sfi, sizeof(sfi),
                        SHGFI_TYPENAME | SHGFI_USEFILEATTRIBUTES)) {
        setError(L"SHGetFileInfo failed");
        return -1;
    }
    int len = (int)wcslen(sfi.szTypeName);
    wcsncpy_s(outBuffer, bufferSize, sfi.szTypeName, _TRUNCATE);
    return len;
}
