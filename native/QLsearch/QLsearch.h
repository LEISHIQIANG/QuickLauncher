#pragma once

#ifdef QLSEARCH_EXPORTS
#define QLSEARCH_API __declspec(dllexport)
#else
#define QLSEARCH_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum QLSortMode {
    QL_SORT_CUSTOM = 0,
    QL_SORT_SMART  = 1,
    QL_SORT_NAME   = 2,
};

struct QLResult {
    int shortcut_id;
    int folder_id;
    double score;
    unsigned int matched_fields_mask;
};

typedef double (*HistoryBonusFn)(const char* query_normalized, const char* shortcut_id_utf8);

QLSEARCH_API int  QLsearch_version(void);
QLSEARCH_API const char* QLsearch_lastError(void);

QLSEARCH_API int  QLsearch_init(void);
QLSEARCH_API void QLsearch_release(void);

QLSEARCH_API int  QLsearch_loadAll(const unsigned char* data, int data_len);

QLSEARCH_API int  QLsearch_search(const char* query_normalized,
                                  int sort_mode,
                                  int limit,
                                  QLResult* out_results,
                                  int out_capacity);

QLSEARCH_API void QLsearch_setHistoryBonuses(const int* shortcut_ids,
                                             const double* bonuses,
                                             int count);

#ifdef __cplusplus
}
#endif
