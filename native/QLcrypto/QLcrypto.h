#pragma once

#ifdef QLCRYPTO_EXPORTS
#define QLCRYPTO_API __declspec(dllexport)
#else
#define QLCRYPTO_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum QLCryptoError {
    QLCRYPTO_OK              = 0,
    QLCRYPTO_ERR_INVALID_ARG = -1,
    QLCRYPTO_ERR_FILE_OPEN   = -2,
    QLCRYPTO_ERR_FILE_READ   = -3,
    QLCRYPTO_ERR_UNSUPPORTED = -4,
    QLCRYPTO_ERR_BUFFER      = -5,
    QLCRYPTO_ERR_INTERNAL    = -6,
};

#define QLCRYPTO_MAX_HEX_LEN 65

QLCRYPTO_API int QLcrypto_hashFile(const char* path,
                                   const char* algorithm,
                                   unsigned long long max_bytes,
                                   char* out_hex,
                                   unsigned int out_len);

QLCRYPTO_API int QLcrypto_version(void);
QLCRYPTO_API const char* QLcrypto_lastError(void);

#ifdef __cplusplus
}
#endif
