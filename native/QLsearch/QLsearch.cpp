#define QLSEARCH_EXPORTS
#define NOMINMAX
#define _WIN32_WINNT 0x0A00
#include "QLsearch.h"
#include "pinyin_table.h"

#include <windows.h>
#include <winnls.h>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <cstring>
#include <cstdio>
#include <cmath>
#include <ctime>
#include <clocale>

#pragma comment(lib, "normaliz.lib")
#pragma comment(lib, "kernel32.lib")

// ---------------------------------------------------------------------------
// Thread-local last-error
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
// UTF-8 / UTF-16 conversion
// ---------------------------------------------------------------------------

static std::wstring utf8_to_wide(const std::string& utf8) {
    if (utf8.empty()) return L"";
    int len = MultiByteToWideChar(CP_UTF8, 0, utf8.data(), (int)utf8.size(), nullptr, 0);
    if (len <= 0) return L"";
    std::wstring out(len, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, utf8.data(), (int)utf8.size(), out.data(), len);
    return out;
}

static std::string wide_to_utf8(const std::wstring& wide) {
    if (wide.empty()) return "";
    int len = WideCharToMultiByte(CP_UTF8, 0, wide.data(), (int)wide.size(), nullptr, 0, nullptr, nullptr);
    if (len <= 0) return "";
    std::string out(len, '\0');
    WideCharToMultiByte(CP_UTF8, 0, wide.data(), (int)wide.size(), out.data(), len, nullptr, nullptr);
    return out;
}

// ---------------------------------------------------------------------------
// UTF-8 codepoint helpers
// ---------------------------------------------------------------------------

static int utf8_byte_len(unsigned char c) {
    if (c < 0x80) return 1;
    if ((c & 0xE0) == 0xC0) return 2;
    if ((c & 0xF0) == 0xE0) return 3;
    if ((c & 0xF8) == 0xF0) return 4;
    return 1;
}

static int utf8_decode(const unsigned char* s, size_t len, size_t& pos) {
    if (pos >= len) return -1;
    unsigned char c = s[pos];
    if (c < 0x80) { pos++; return c; }
    if ((c & 0xE0) == 0xC0 && pos + 1 < len) {
        int cp = ((c & 0x1F) << 6) | (s[pos + 1] & 0x3F);
        pos += 2; return cp;
    }
    if ((c & 0xF0) == 0xE0 && pos + 2 < len) {
        int cp = ((c & 0x0F) << 12) | ((s[pos + 1] & 0x3F) << 6) | (s[pos + 2] & 0x3F);
        pos += 3; return cp;
    }
    if ((c & 0xF8) == 0xF0 && pos + 3 < len) {
        int cp = ((c & 0x07) << 18) | ((s[pos + 1] & 0x3F) << 12) | ((s[pos + 2] & 0x3F) << 6) | (s[pos + 3] & 0x3F);
        pos += 4; return cp;
    }
    pos++; return c;
}

static void utf8_encode(int cp, std::string& out) {
    if (cp < 0x80) { out.push_back((char)cp); }
    else if (cp < 0x800) { out.push_back((char)(0xC0 | (cp >> 6))); out.push_back((char)(0x80 | (cp & 0x3F))); }
    else if (cp < 0x10000) { out.push_back((char)(0xE0 | (cp >> 12))); out.push_back((char)(0x80 | ((cp >> 6) & 0x3F))); out.push_back((char)(0x80 | (cp & 0x3F))); }
    else { out.push_back((char)(0xF0 | (cp >> 18))); out.push_back((char)(0x80 | ((cp >> 12) & 0x3F))); out.push_back((char)(0x80 | ((cp >> 6) & 0x3F))); out.push_back((char)(0x80 | (cp & 0x3F))); }
}

static bool is_unicode_alnum(int cp) {
    if (cp < 0) return false;
    if (cp < 128) return (cp >= '0' && cp <= '9') || (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z');
    if (cp >= 0x4E00 && cp <= 0x9FFF) return true;   // CJK Unified Ideographs
    if (cp >= 0x3400 && cp <= 0x4DBF) return true;   // CJK Extension A
    if (cp >= 0xF900 && cp <= 0xFAFF) return true;   // CJK Compatibility
    if (cp >= 0x3040 && cp <= 0x309F) return true;   // Hiragana
    if (cp >= 0x30A0 && cp <= 0x30FF) return true;   // Katakana
    if (cp >= 0xAC00 && cp <= 0xD7AF) return true;   // Hangul
    if (cp >= 0xFF21 && cp <= 0xFF3A) return true;   // Fullwidth A-Z
    if (cp >= 0xFF41 && cp <= 0xFF5A) return true;   // Fullwidth a-z
    if (cp >= 0xFF10 && cp <= 0xFF19) return true;   // Fullwidth 0-9
    if (cp >= 0x20000 && cp <= 0x2A6DF) return true; // CJK Extension B
    return false;
}

static bool is_cjk_codepoint(int cp) {
    return (cp >= 0x4E00 && cp <= 0x9FFF) ||
           (cp >= 0x3400 && cp <= 0x4DBF) ||
           (cp >= 0xF900 && cp <= 0xFA5F);
}

// ---------------------------------------------------------------------------
// normalize_text  (NFKC + remove combining + casefold + whitespace compress)
// ---------------------------------------------------------------------------

static std::string normalize_text(const std::string& value) {
    if (value.empty()) return "";

    // Step 1: trim
    size_t start = 0, end = value.size();
    while (start < end && (value[start] == ' ' || value[start] == '\t' || value[start] == '\r' || value[start] == '\n')) start++;
    while (end > start && (value[end - 1] == ' ' || value[end - 1] == '\t' || value[end - 1] == '\r' || value[end - 1] == '\n')) end--;
    if (start >= end) return "";

    // Step 2: NFKC via NormalizeString
    std::wstring wide = utf8_to_wide(value.substr(start, end - start));
    if (wide.empty()) return "";

    int nfkc_len = NormalizeString(NormalizationKC, wide.data(), (int)wide.size(), nullptr, 0);
    if (nfkc_len <= 0) return "";
    std::wstring nfkc(nfkc_len, L'\0');
    NormalizeString(NormalizationKC, wide.data(), (int)wide.size(), nfkc.data(), nfkc_len);

    // Step 3: remove combining characters + casefold + whitespace compress
    std::wstring filtered;
    filtered.reserve(nfkc.size());
    bool in_space = false;
    for (size_t i = 0; i < nfkc.size(); ) {
        wchar_t ch = nfkc[i];
        WORD type3 = 0;
        GetStringTypeW(CT_CTYPE3, &ch, 1, &type3);
        if (type3 & (C3_NONSPACING | C3_DIACRITIC)) { i++; continue; }
        if (ch == L' ' || ch == L'\t' || ch == L'\r' || ch == L'\n') {
            if (!in_space) { filtered.push_back(L' '); in_space = true; }
            i++; continue;
        }
        in_space = false;
        // Casefold via CharLowerBuffW
        wchar_t lowered[2] = {ch, L'\0'};
        CharLowerBuffW(lowered, 1);
        filtered.push_back(lowered[0]);
        i++;
    }
    // Trim trailing space
    while (!filtered.empty() && filtered.back() == L' ') filtered.pop_back();

    return wide_to_utf8(filtered);
}

// ---------------------------------------------------------------------------
// compact_text  (alnum only, after normalization)
// ---------------------------------------------------------------------------

static std::string compact_text(const std::string& value) {
    std::string norm = normalize_text(value);
    if (norm.empty()) return "";
    std::string out;
    size_t pos = 0;
    const auto* s = reinterpret_cast<const unsigned char*>(norm.data());
    size_t len = norm.size();
    while (pos < len) {
        int cp = utf8_decode(s, len, pos);
        if ((cp >= '0' && cp <= '9') || (cp >= 'a' && cp <= 'z')) {
            out.push_back((char)cp);
        } else if (cp >= 128 && is_unicode_alnum(cp)) {
            utf8_encode(cp, out);
        }
    }
    return out;
}

// ---------------------------------------------------------------------------
// basename / stem
// ---------------------------------------------------------------------------

static std::string basename(const std::string& value) {
    if (value.empty()) return "";
    size_t pos = value.find_last_of("\\/");
    return (pos != std::string::npos) ? value.substr(pos + 1) : value;
}

static std::string stem(const std::string& value) {
    std::string base = basename(value);
    size_t dot = base.find_last_of('.');
    if (dot != std::string::npos && dot > 0) return base.substr(0, dot);
    return base;
}

// ---------------------------------------------------------------------------
// word_text / word_tokens / acronym
// ---------------------------------------------------------------------------

static std::string word_text(const std::string& value) {
    std::string norm = normalize_text(value);
    if (norm.empty()) return "";
    std::string out;
    size_t pos = 0;
    const auto* s = reinterpret_cast<const unsigned char*>(norm.data());
    size_t len = norm.size();
    int prev_cp = -1;
    while (pos < len) {
        int cp = utf8_decode(s, len, pos);
        // CamelCase boundary detection
        if (prev_cp >= 'a' && prev_cp <= 'z' && cp >= 'A' && cp <= 'Z') {
            out.push_back(' ');
        }
        if ((cp >= '0' && cp <= '9') || (cp >= 'a' && cp <= 'z') || (cp >= 'A' && cp <= 'Z') ||
            (cp >= 128 && is_unicode_alnum(cp))) {
            utf8_encode(cp, out);
        } else {
            if (!out.empty() && out.back() != ' ') out.push_back(' ');
        }
        prev_cp = cp;
    }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

static std::vector<std::string> word_tokens(const std::string& value) {
    std::string wt = word_text(value);
    std::vector<std::string> tokens;
    std::string current;
    for (size_t i = 0; i < wt.size(); ++i) {
        if (wt[i] == ' ') {
            if (!current.empty()) { tokens.push_back(current); current.clear(); }
        } else {
            current.push_back(wt[i]);
        }
    }
    if (!current.empty()) tokens.push_back(current);
    return tokens;
}

static std::string acronym(const std::string& value) {
    auto tokens = word_tokens(value);
    std::string out;
    for (const auto& tok : tokens) {
        if (!tok.empty()) out.push_back(tok[0]);
    }
    return out;
}

// ---------------------------------------------------------------------------
// GB2312 initial consonant lookup
// ---------------------------------------------------------------------------

static char gb2312_initial_lookup(uint32_t cp) {
    if (cp < 0x80) return 0;
    // Convert to GBK (CP936) via WideCharToMultiByte
    wchar_t wch = (wchar_t)cp;
    char gb_buf[4] = {};
    int gb_len = WideCharToMultiByte(936, 0, &wch, 1, gb_buf, sizeof(gb_buf), nullptr, nullptr);
    if (gb_len != 2) return 0;
    int val = ((unsigned char)gb_buf[0] << 8) | (unsigned char)gb_buf[1];
    for (int i = 0; i < GB_INITIAL_RANGES_SIZE; ++i) {
        if (val >= GB_INITIAL_RANGES[i].lo && val <= GB_INITIAL_RANGES[i].hi)
            return GB_INITIAL_RANGES[i].initial;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// pinyin_variants
// ---------------------------------------------------------------------------

static std::vector<std::string> pinyin_variants(const std::string& text) {
    if (text.empty()) return {};

    // Filter to CJK + ASCII alnum
    std::string filtered;
    {
        size_t pos = 0;
        const auto* s = reinterpret_cast<const unsigned char*>(text.data());
        size_t len = text.size();
        while (pos < len) {
            int cp = utf8_decode(s, len, pos);
            if (is_cjk_codepoint(cp) || (cp < 128 && ((cp >= '0' && cp <= '9') || (cp >= 'a' && cp <= 'z') || (cp >= 'A' && cp <= 'Z'))))
                utf8_encode(cp, filtered);
        }
    }

    // Check for CJK presence
    bool has_cjk = false;
    {
        size_t pos = 0;
        const auto* s = reinterpret_cast<const unsigned char*>(filtered.data());
        size_t len = filtered.size();
        while (pos < len) {
            int cp = utf8_decode(s, len, pos);
            if (is_cjk_codepoint(cp)) { has_cjk = true; break; }
        }
    }
    if (!has_cjk) return {};

    // Build using built-in table + GB2312 fallback
    std::string full, initials;
    bool has_mapped = false;
    size_t pos = 0;
    const auto* s = reinterpret_cast<const unsigned char*>(filtered.data());
    size_t len = filtered.size();
    while (pos < len) {
        int cp = utf8_decode(s, len, pos);
        const char* py = pinyin_lookup((uint32_t)cp);
        if (py) {
            has_mapped = true;
            full += py;
            if (py[0]) initials.push_back(py[0]);
        } else if (is_cjk_codepoint(cp)) {
            char ini = gb2312_initial_lookup((uint32_t)cp);
            if (ini) {
                has_mapped = true;
                full.push_back(ini);
                initials.push_back(ini);
            }
        } else if (cp < 128 && ((cp >= '0' && cp <= '9') || (cp >= 'a' && cp <= 'z') || (cp >= 'A' && cp <= 'Z'))) {
            full.push_back((char)((cp >= 'A' && cp <= 'Z') ? cp + 32 : cp));
            initials.push_back((char)((cp >= 'A' && cp <= 'Z') ? cp + 32 : cp));
        }
    }
    if (!has_mapped) return {};

    std::vector<std::string> result;
    if (!full.empty()) result.push_back(full);
    if (!initials.empty() && initials != full) result.push_back(initials);
    return result;
}

// ---------------------------------------------------------------------------
// field_variants (forward declaration)
// ---------------------------------------------------------------------------

struct Variant;
static void build_field_variants(const std::string& raw_value, std::vector<Variant>& out);

// ---------------------------------------------------------------------------
// split_terms (for query)
// ---------------------------------------------------------------------------

static std::vector<std::string> split_terms(const std::string& text) {
    std::vector<std::string> terms;
    std::string current;
    size_t pos = 0;
    const auto* s = reinterpret_cast<const unsigned char*>(text.data());
    size_t len = text.size();
    while (pos < len) {
        int cp = utf8_decode(s, len, pos);
        if (cp == ' ' || cp == ',' || cp == ';' || cp == '|' ||
            cp == 0xFF0C || cp == 0x3001 || cp == 0xFF1B || cp == 0x3002) {
            if (!current.empty()) { terms.push_back(current); current.clear(); }
        } else {
            utf8_encode(cp, current);
        }
    }
    if (!current.empty()) terms.push_back(current);
    return terms;
}

// ---------------------------------------------------------------------------
// Binary buffer reader
// ---------------------------------------------------------------------------

struct BufReader {
    const unsigned char* data;
    size_t len;
    size_t pos;

    bool ok() const { return pos <= len; }

    int32_t read_i32() {
        if (pos + 4 > len) { pos = len + 1; return 0; }
        int32_t v;
        memcpy(&v, data + pos, 4);
        pos += 4;
        return v;
    }

    int64_t read_i64() {
        if (pos + 8 > len) { pos = len + 1; return 0; }
        int64_t v;
        memcpy(&v, data + pos, 8);
        pos += 8;
        return v;
    }

    double read_f64() {
        if (pos + 8 > len) { pos = len + 1; return 0.0; }
        double v;
        memcpy(&v, data + pos, 8);
        pos += 8;
        return v;
    }

    std::string read_string() {
        int32_t slen = read_i32();
        if (slen < 0 || pos + (size_t)slen > len) { pos = len + 1; return ""; }
        std::string s(reinterpret_cast<const char*>(data + pos), slen);
        pos += slen;
        return s;
    }
};

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------

struct Variant {
    std::string normalized;
    std::string compact;
    std::vector<std::string> tokens;
    std::string acronym;
};

struct Field {
    std::vector<Variant> variants;
    double weight;
};

struct Shortcut {
    int id;
    int folder_id;
    bool enabled;
    int order;
    int smart_order;
    int use_count;
    long long last_used_at;
    std::string shortcut_id;
    Field fields[7];
};

struct Folder {
    int id;
    std::string name;
};

// ---------------------------------------------------------------------------
// build_field_variants (implementation — after struct definitions)
// ---------------------------------------------------------------------------

static void build_field_variants(const std::string& raw_value, std::vector<Variant>& out) {
    if (raw_value.empty()) return;

    std::string raw = raw_value;
    while (!raw.empty() && (raw.front() == ' ' || raw.front() == '\t')) raw.erase(0, 1);
    while (!raw.empty() && (raw.back() == ' ' || raw.back() == '\t')) raw.pop_back();
    if (raw.empty()) return;

    std::vector<std::string> variant_strs = {raw};

    std::string base = basename(raw);
    if (!base.empty() && base != raw) variant_strs.push_back(base);

    std::string stm = stem(raw);
    if (!stm.empty() && stm != raw && stm != base) variant_strs.push_back(stm);

    std::string compact = compact_text(raw);
    if (!compact.empty()) variant_strs.push_back(compact);

    std::string words = word_text(raw);
    if (!words.empty() && std::find(variant_strs.begin(), variant_strs.end(), words) == variant_strs.end())
        variant_strs.push_back(words);

    auto pinyin = pinyin_variants(raw);
    for (auto& py : pinyin) {
        if (!py.empty() && std::find(variant_strs.begin(), variant_strs.end(), py) == variant_strs.end())
            variant_strs.push_back(std::move(py));
    }

    std::unordered_set<std::string> seen;
    for (const auto& vs : variant_strs) {
        std::string norm = normalize_text(vs);
        if (norm.empty() || seen.count(norm)) continue;
        seen.insert(norm);

        Variant var;
        var.normalized = norm;
        var.compact = compact_text(vs);
        var.tokens = word_tokens(vs);
        var.acronym = acronym(vs);
        out.push_back(std::move(var));
    }
}

// ---------------------------------------------------------------------------
// Scoring (ported from Python fuzzy_search.py)
// ---------------------------------------------------------------------------

static const double FIELD_WEIGHTS[7] = {120.0, 110.0, 95.0, 55.0, 50.0, 45.0, 35.0};

static double word_boundary_bonus(const std::string& haystack, int start) {
    if (start < 0) return 0.0;
    if (start == 0) return 18.0;
    char prev = haystack[start - 1];
    char curr = haystack[start];
    if (prev == ' ' || prev == '_' || prev == '-' || prev == '.' ||
        prev == '/' || prev == '\\' || prev == '(' || prev == ')' ||
        prev == '[' || prev == ']' || prev == '{' || prev == '}') {
        return 14.0;
    }
    if (prev >= 'a' && prev <= 'z' && curr >= 'A' && curr <= 'Z') {
        return 10.0;
    }
    return 0.0;
}

static bool subsequence_match(const std::string& needle, const std::string& haystack,
                              std::vector<int>& positions) {
    positions.clear();
    size_t start = 0;
    for (size_t i = 0; i < needle.size(); ++i) {
        size_t pos = haystack.find(needle[i], start);
        if (pos == std::string::npos) return false;
        positions.push_back((int)pos);
        start = pos + 1;
    }
    return true;
}

static double subsequence_score(const std::string& needle, const std::string& haystack) {
    if (needle.empty()) return 0.0;
    if (haystack.empty()) return -1.0;

    size_t exact_pos = haystack.find(needle);
    if (exact_pos != std::string::npos) {
        double score = 70.0 + (double)needle.size() * 6.0;
        score += std::max(0.0, 20.0 - (double)exact_pos);
        score += word_boundary_bonus(haystack, (int)exact_pos);
        if (exact_pos == 0 && needle.size() == haystack.size()) {
            score += 45.0;
        }
        return score;
    }

    std::vector<int> positions;
    if (!subsequence_match(needle, haystack, positions)) return -1.0;

    int span = positions.back() - positions.front() + 1;
    int gaps = std::max(0, span - (int)needle.size());
    int contiguous_pairs = 0;
    for (size_t i = 0; i + 1 < positions.size(); ++i) {
        if (positions[i + 1] == positions[i] + 1) contiguous_pairs++;
    }
    double score = 38.0 + (double)needle.size() * 5.0;
    score += contiguous_pairs * 8.0;
    score += std::max(0.0, 16.0 - (double)positions[0]);
    score += word_boundary_bonus(haystack, positions[0]);
    score -= gaps * 2.0;
    return std::max(1.0, score);
}

static int longest_common_substring(const std::string& a, const std::string& b,
                                     size_t& a_start, size_t& b_start) {
    size_t best_len = 0;
    size_t best_a = 0, best_b = 0;
    for (size_t i = 0; i < a.size(); ++i) {
        for (size_t j = 0; j < b.size(); ++j) {
            size_t k = 0;
            while (i + k < a.size() && j + k < b.size() && a[i + k] == b[j + k]) ++k;
            if (k > best_len) { best_len = k; best_a = i; best_b = j; }
        }
    }
    a_start = best_a; b_start = best_b;
    return (int)best_len;
}

static int ratcliff_match(const std::string& a, const std::string& b) {
    size_t a_start, b_start;
    int match_len = longest_common_substring(a, b, a_start, b_start);
    if (match_len == 0) return 0;
    int total = match_len;
    if (a_start > 0 && b_start > 0) {
        total += ratcliff_match(a.substr(0, a_start), b.substr(0, b_start));
    }
    size_t a_right_start = a_start + match_len;
    size_t b_right_start = b_start + match_len;
    if (a_right_start < a.size() && b_right_start < b.size()) {
        total += ratcliff_match(a.substr(a_right_start), b.substr(b_right_start));
    }
    return total;
}

static double ratcliff_ratio(const std::string& a, const std::string& b) {
    if (a.empty() && b.empty()) return 1.0;
    if (a.empty() || b.empty()) return 0.0;
    int matched = ratcliff_match(a, b);
    return 2.0 * (double)matched / (double)(a.size() + b.size());
}

static double near_word_score(const std::string& needle, const std::vector<std::string>& tokens) {
    if (needle.size() < 3) return -1.0;
    double best = 0.0;
    for (const auto& token : tokens) {
        if (token.size() < 3) continue;
        double ratio = ratcliff_ratio(needle, token);
        if (ratio >= 0.78) {
            best = std::max(best, 42.0 + ratio * 38.0);
        }
    }
    return best > 0.0 ? best : -1.0;
}

static double single_term_score(const std::string& term_norm, const std::string& term_compact,
                                const Field& field) {
    double best = -1.0;

    for (const auto& variant : field.variants) {
        const std::string& normalized = variant.normalized;
        const std::string& compact = variant.compact;
        const auto& tokens = variant.tokens;
        const std::string& acronym = variant.acronym;

        std::vector<double> candidates;

        if (term_norm == normalized) {
            candidates.push_back(138.0 + (double)term_norm.size() * 7.0);
        }
        for (const auto& token : tokens) {
            if (token == term_norm) {
                candidates.push_back(122.0 + (double)term_norm.size() * 6.0);
            }
        }
        for (const auto& token : tokens) {
            if (token.size() > term_norm.size() && token.compare(0, term_norm.size(), term_norm) == 0) {
                candidates.push_back(104.0 + (double)term_norm.size() * 5.0 +
                                     std::max(0.0, 12.0 - (double)token.size()));
            }
        }

        if (!acronym.empty()) {
            if (acronym == term_compact) {
                double shortest = 12.0;
                for (const auto& token : tokens) shortest = std::min(shortest, (double)token.size());
                candidates.push_back(118.0 + (double)term_compact.size() * 6.0 +
                                     std::max(0.0, 12.0 - shortest));
            } else if (acronym.size() > term_compact.size() &&
                       acronym.compare(0, term_compact.size(), term_compact) == 0) {
                candidates.push_back(102.0 + (double)term_compact.size() * 5.0);
            } else if (!term_compact.empty() &&
                       acronym.find(term_compact) != std::string::npos) {
                candidates.push_back(84.0 + (double)term_compact.size() * 4.0);
            }
        }

        if (!term_compact.empty()) {
            size_t compact_pos = compact.find(term_compact);
            if (compact_pos != std::string::npos) {
                candidates.push_back(76.0 + (double)term_compact.size() * 5.0 +
                                     std::max(0.0, 12.0 - (double)compact_pos) +
                                     std::max(0.0, 24.0 - (double)compact.size()) * 0.5);
            }
        }

        double subs = subsequence_score(term_norm, normalized);
        if (subs >= 0.0) candidates.push_back(subs);
        if (compact != normalized) {
            double subs_c = subsequence_score(term_compact, compact);
            if (subs_c >= 0.0) candidates.push_back(subs_c - 4.0);
        }

        double nw = near_word_score(term_norm, tokens);
        if (nw >= 0.0) candidates.push_back(nw);

        if (!candidates.empty()) {
            double score = *std::max_element(candidates.begin(), candidates.end());
            if (best < 0.0 || score > best) best = score;
        }
    }
    return best;
}

static double usage_bonus(int use_count, long long last_used_at) {
    double count_bonus = std::min(35.0, (double)std::max(0, use_count) * 1.8);
    double time_bonus = 0.0;
    if (last_used_at > 0) {
        double elapsed = std::max(0.0, (double)time(nullptr) - (double)last_used_at);
        time_bonus = 20.0 * std::pow(0.5, elapsed / 259200.0);
    }
    return count_bonus + time_bonus;
}

// ---------------------------------------------------------------------------
// Search engine state
// ---------------------------------------------------------------------------

struct SearchEngine {
    std::vector<Shortcut> shortcuts;
    std::unordered_map<int, size_t> id_index;
    std::vector<Folder> folders;
    std::unordered_map<int, size_t> folder_index;
    std::unordered_map<int, double> history_bonuses;
    bool initialized = false;
};

static SearchEngine* g_engine = nullptr;

// ---------------------------------------------------------------------------
// loadAll: parse binary buffer (NEW PROTOCOL: raw field strings, DLL computes variants)
// ---------------------------------------------------------------------------
// Buffer layout:
//   int32 folder_count
//   for each folder: int32 id, string name
//   int32 shortcut_count
//   for each shortcut:
//     int32 id / int32 folder_id / int32 enabled / int32 order /
//     int32 smart_order / int32 use_count / int64 last_used_at /
//     string shortcut_id_str
//     for field 0..6:
//       float64 weight
//       string raw_value      // raw field text — DLL computes variants internally

static int load_all_internal(const unsigned char* data, int data_len) {
    if (!data || data_len <= 0) {
        set_last_error("loadAll: invalid buffer");
        return -1;
    }

    BufReader r{data, (size_t)data_len, 0};

    int32_t folder_count = r.read_i32();
    if (!r.ok()) { set_last_error("loadAll: failed reading folder count"); return -1; }

    std::vector<Folder> folders;
    folders.reserve(folder_count);
    for (int i = 0; i < folder_count; ++i) {
        Folder f;
        f.id = r.read_i32();
        f.name = r.read_string();
        if (!r.ok()) { set_last_error("loadAll: failed reading folder %d", i); return -1; }
        folders.push_back(std::move(f));
    }

    int32_t shortcut_count = r.read_i32();
    if (!r.ok()) { set_last_error("loadAll: failed reading shortcut count"); return -1; }

    std::vector<Shortcut> shortcuts;
    shortcuts.reserve(shortcut_count);
    std::unordered_map<int, size_t> id_index;

    for (int i = 0; i < shortcut_count; ++i) {
        Shortcut sc;
        sc.id = r.read_i32();
        sc.folder_id = r.read_i32();
        sc.enabled = r.read_i32() != 0;
        sc.order = r.read_i32();
        sc.smart_order = r.read_i32();
        sc.use_count = r.read_i32();
        sc.last_used_at = r.read_i64();
        sc.shortcut_id = r.read_string();
        if (!r.ok()) { set_last_error("loadAll: failed reading shortcut header %d", i); return -1; }

        for (int f = 0; f < 7; ++f) {
            sc.fields[f].weight = r.read_f64();
            std::string raw_value = r.read_string();
            if (!r.ok()) { set_last_error("loadAll: failed reading field %d of shortcut %d", f, i); return -1; }
            build_field_variants(raw_value, sc.fields[f].variants);
        }

        id_index[sc.id] = shortcuts.size();
        shortcuts.push_back(std::move(sc));
    }

    g_engine->shortcuts = std::move(shortcuts);
    g_engine->id_index = std::move(id_index);
    g_engine->folders = std::move(folders);
    g_engine->folder_index.clear();
    for (size_t i = 0; i < g_engine->folders.size(); ++i) {
        g_engine->folder_index[g_engine->folders[i].id] = i;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// search
// ---------------------------------------------------------------------------

struct ScoredItem {
    double score;
    int shortcut_idx;
    int order_val;
    unsigned int matched_mask;
};

static int search_internal(const char* query_normalized, int sort_mode, int limit,
                           QLResult* out_results, int out_capacity) {
    if (!query_normalized || !out_results || out_capacity <= 0) {
        set_last_error("search: invalid arguments");
        return -1;
    }

    std::string query(query_normalized);
    if (query.empty()) return 0;

    std::vector<std::string> terms = split_terms(query);
    if (terms.empty()) return 0;

    std::vector<std::string> terms_compact;
    terms_compact.reserve(terms.size());
    for (const auto& term : terms) {
        terms_compact.push_back(compact_text(term));
    }

    std::string query_compact = compact_text(query);
    bool query_compact_diff = (query_compact != query);

    bool use_usage_bonus = (sort_mode == QL_SORT_SMART);

    std::vector<ScoredItem> results;
    results.reserve(g_engine->shortcuts.size());

    for (size_t si = 0; si < g_engine->shortcuts.size(); ++si) {
        const Shortcut& sc = g_engine->shortcuts[si];

        if (!sc.enabled) continue;

        double total = 0.0;
        unsigned int matched_mask = 0;
        bool failed = false;

        for (size_t ti = 0; ti < terms.size(); ++ti) {
            const std::string& term_norm = terms[ti];
            const std::string& term_compact = terms_compact[ti];

            double best_term_score = -1.0;
            int best_field = -1;
            double best_weight = 0.0;

            for (int fi = 0; fi < 7; ++fi) {
                double fs = single_term_score(term_norm, term_compact, sc.fields[fi]);
                if (fs < 0.0) continue;
                double weighted = fs + sc.fields[fi].weight;
                if (best_term_score < 0.0 || weighted > best_term_score) {
                    best_term_score = weighted;
                    best_field = fi;
                    best_weight = sc.fields[fi].weight;
                }
            }

            if (best_term_score < 0.0) {
                failed = true;
                break;
            }

            total += best_term_score;
            if (best_field >= 0 && !(matched_mask & (1u << best_field))) {
                matched_mask |= (1u << best_field);
            }
            total += best_weight / 12.0;
        }

        if (failed) continue;

        double score = total / (double)terms.size();

        for (int fi = 0; fi < 7; ++fi) {
            double phrase_score = single_term_score(query, "", sc.fields[fi]);
            double compact_score = -1.0;
            if (query_compact_diff) {
                compact_score = single_term_score(query_compact, "", sc.fields[fi]);
            }

            double best_phrase = -1.0;
            if (phrase_score >= 0.0) best_phrase = phrase_score;
            if (compact_score >= 0.0) best_phrase = std::max(best_phrase, compact_score);

            if (best_phrase < 0.0) continue;
            double weighted_phrase = best_phrase + sc.fields[fi].weight + 18.0;
            if (weighted_phrase > score) {
                score = weighted_phrase;
                if (!(matched_mask & (1u << fi))) {
                    matched_mask |= (1u << fi);
                }
            }
        }

        if (terms.size() > 1) {
            score += std::min(18.0, (double)(terms.size() - 1) * 6.0);
        }

        if (!sc.shortcut_id.empty()) {
            auto it = g_engine->history_bonuses.find(sc.id);
            if (it != g_engine->history_bonuses.end()) {
                score += it->second;
            }
        }

        if (use_usage_bonus) {
            score += usage_bonus(sc.use_count, sc.last_used_at);
        }

        int order_val = (sort_mode == QL_SORT_SMART && sc.smart_order >= 0)
                            ? sc.smart_order : sc.order;
        results.push_back({score, (int)si, order_val, matched_mask});
    }

    std::stable_sort(results.begin(), results.end(),
        [](const ScoredItem& a, const ScoredItem& b) {
            if (a.score != b.score) return a.score > b.score;
            return a.order_val < b.order_val;
        });

    int n = std::min((int)results.size(), limit > 0 ? limit : (int)results.size());
    n = std::min(n, out_capacity);
    for (int i = 0; i < n; ++i) {
        const ScoredItem& item = results[i];
        const Shortcut& sc = g_engine->shortcuts[item.shortcut_idx];
        out_results[i].shortcut_id = sc.id;
        out_results[i].folder_id = sc.folder_id;
        out_results[i].score = item.score;
        out_results[i].matched_fields_mask = item.matched_mask;
    }
    return n;
}

// ---------------------------------------------------------------------------
// Exported functions
// ---------------------------------------------------------------------------

extern "C" {

QLSEARCH_API int QLsearch_version(void) {
    return 2;
}

QLSEARCH_API const char* QLsearch_lastError(void) {
    if (g_lastError.empty()) return "";
    return g_lastError.c_str();
}

QLSEARCH_API int QLsearch_init(void) {
    if (g_engine) return 0;
    g_engine = new SearchEngine();
    g_engine->initialized = true;
    return 0;
}

QLSEARCH_API void QLsearch_release(void) {
    delete g_engine;
    g_engine = nullptr;
}

QLSEARCH_API int QLsearch_loadAll(const unsigned char* data, int data_len) {
    if (!g_engine) {
        g_engine = new SearchEngine();
    }
    return load_all_internal(data, data_len);
}

QLSEARCH_API int QLsearch_search(const char* query_normalized,
                                 int sort_mode,
                                 int limit,
                                 QLResult* out_results,
                                 int out_capacity) {
    if (!g_engine) {
        set_last_error("search: engine not initialized");
        return -1;
    }
    return search_internal(query_normalized, sort_mode, limit, out_results, out_capacity);
}

QLSEARCH_API void QLsearch_setHistoryBonuses(const int* shortcut_ids,
                                              const double* bonuses,
                                              int count) {
    if (!g_engine) return;
    g_engine->history_bonuses.clear();
    if (!shortcut_ids || !bonuses || count <= 0) return;
    for (int i = 0; i < count; ++i) {
        if (bonuses[i] != 0.0) {
            g_engine->history_bonuses[shortcut_ids[i]] = bonuses[i];
        }
    }
}

} // extern "C"
