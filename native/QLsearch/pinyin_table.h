#pragma once

#include <cstdint>

struct PinyinEntry {
    uint32_t codepoint;
    const char* pinyin;
};

// Sorted by codepoint for binary search
static const PinyinEntry PINYIN_TABLE[] = {
    {0x4E09, "san"},    {0x4E0B, "xia"},    {0x4E0D, "bu"},     {0x4E16, "shi"},
    {0x4E1C, "dong"},   {0x4E2D, "zhong"},  {0x4E3B, "zhu"},    {0x4E50, "yue"},
    {0x4E8B, "shi"},    {0x4E8E, "yu"},     {0x4E91, "yun"},    {0x4EAC, "jing"},
    {0x4EE3, "dai"},    {0x4EE4, "ling"},   {0x4EF6, "jian"},   {0x4EFB, "ren"},
    {0x4ED8, "fu"},     {0x4FEE, "xiu"},    {0x4FE1, "xin"},    {0x50CF, "xiang"},
    {0x5168, "quan"},   {0x5171, "gong"},   {0x5173, "guan"},   {0x5177, "ju"},
    {0x5185, "nei"},    {0x518C, "ce"},     {0x51FA, "chu"},    {0x5206, "fen"},
    {0x5220, "shan"},   {0x5236, "zhi"},    {0x52A1, "wu"},     {0x52A8, "dong"},
    {0x52A9, "zhu"},    {0x5305, "bao"},    {0x5339, "pi"},     {0x5347, "sheng"},
    {0x538B, "ya"},     {0x5386, "li"},     {0x53D1, "fa"},     {0x53D6, "qu"},
    {0x53E3, "kou"},    {0x53F0, "tai"},    {0x53F2, "shi"},    {0x542F, "qi"},
    {0x5427, "ba"},     {0x547D, "ming"},   {0x548C, "he"},     {0x54D4, "bi"},
    {0x54E9, "li"},     {0x5668, "qi"},     {0x56DE, "hui"},    {0x56FD, "guo"},
    {0x56FE, "tu"},     {0x5730, "di"},     {0x573E, "ji"},     {0x5783, "la"},
    {0x5883, "jing"},   {0x5899, "qiang"},  {0x5907, "bei"},    {0x590D, "fu"},
    {0x591A, "duo"},    {0x5939, "jia"},    {0x597D, "hao"},    {0x5B89, "an"},
    {0x5B9D, "bao"},    {0x5BFC, "dao"},    {0x5C4F, "ping"},   {0x5C5E, "shu"},
    {0x5DE5, "gong"},   {0x5E2E, "bang"},   {0x5E7F, "guang"},  {0x5E8F, "xu"},
    {0x5E93, "ku"},     {0x5E94, "ying"},   {0x5EFA, "jian"},   {0x5F00, "kai"},
    {0x5F0F, "shi"},    {0x5F52, "gui"},    {0x5F55, "lu"},     {0x5F84, "jing"},
    {0x5FAE, "wei"},    {0x5FEB, "kuai"},   {0x6001, "tai"},    {0x6027, "xing"},
    {0x606F, "xi"},     {0x609F, "wu"},     {0x60F3, "xiang"},  {0x620F, "xi"},
    {0x622A, "jie"},    {0x6253, "da"},     {0x6258, "tuo"},    {0x626B, "sao"},
    {0x627E, "zhao"},   {0x6295, "tou"},    {0x6296, "dou"},    {0x62FE, "shi"},
    {0x6362, "huan"},   {0x636E, "ju"},     {0x63A5, "jie"},    {0x63A7, "kong"},
    {0x63CF, "miao"},   {0x63D0, "ti"},     {0x63D2, "cha"},    {0x64AD, "bo"},
    {0x652F, "zhi"},    {0x6536, "shou"},   {0x6539, "gai"},    {0x653E, "fang"},
    {0x6570, "shu"},    {0x6574, "zheng"},  {0x6587, "wen"},    {0x65B0, "xin"},
    {0x65B9, "fang"},   {0x65AD, "duan"},   {0x65F6, "shi"},    {0x6613, "yi"},
    {0x66F4, "geng"},   {0x66FF, "ti"},     {0x670D, "fu"},     {0x672C, "ben"},
    {0x673A, "ji"},     {0x677F, "ban"},    {0x6781, "ji"},     {0x67E5, "cha"},
    {0x684C, "zhuo"},   {0x6863, "dang"},   {0x68C0, "jian"},   {0x6B4C, "ge"},
    {0x6CB9, "you"},    {0x6CE8, "zhu"},    {0x6D4B, "ce"},     {0x6D4F, "liu"},
    {0x6D77, "hai"},    {0x6DD8, "tao"},    {0x6E05, "qing"},   {0x6E38, "you"},
    {0x6E90, "yuan"},   {0x706B, "huo"},    {0x7167, "zhao"},   {0x7247, "pian"},
    {0x7248, "ban"},    {0x7279, "te"},     {0x72D0, "hu"},     {0x7334, "hou"},
    {0x73AF, "huan"},   {0x7406, "li"},     {0x7528, "yong"},   {0x753B, "hua"},
    {0x754C, "jie"},    {0x767E, "bai"},    {0x7684, "de"},     {0x76D8, "pan"},
    {0x76DF, "meng"},   {0x76EE, "mu"},     {0x76F8, "xiang"},  {0x7801, "ma"},
    {0x793A, "shi"},    {0x795E, "shen"},   {0x79D2, "miao"},   {0x7A0B, "cheng"},
    {0x7A7A, "kong"},   {0x7A97, "chuang"}, {0x7AD9, "zhan"},   {0x7B14, "bi"},
    {0x7B26, "fu"},     {0x7B2C, "di"},     {0x7B97, "suan"},   {0x7B7E, "qian"},
    {0x7CBE, "jing"},   {0x7CFB, "xi"},     {0x7D22, "suo"},    {0x7F16, "bian"},
    {0x7F51, "wang"},   {0x7F6E, "zhi"},    {0x7EA7, "ji"},     {0x7EDC, "luo"},
    {0x7EDF, "tong"},   {0x7EC8, "zhong"},  {0x804A, "liao"},   {0x8054, "lian"},
    {0x80A1, "gu"},     {0x8111, "nao"},    {0x817E, "teng"},   {0x81EA, "zi"},
    {0x8272, "se"},     {0x82F1, "ying"},   {0x83DC, "cai"},    {0x864E, "hu"},
    {0x884C, "hang"},   {0x8868, "biao"},   {0x88C5, "zhuang"}, {0x89C6, "shi"},
    {0x89C8, "lan"},    {0x89E3, "jie"},    {0x8B66, "jing"},   {0x8BA1, "ji"},
    {0x8BAF, "xun"},    {0x8BB0, "ji"},     {0x8BBE, "she"},    {0x8BCA, "zhen"},
    {0x8BD5, "shi"},    {0x8BED, "yu"},     {0x8C03, "diao"},   {0x8C37, "gu"},
    {0x8D34, "tie"},    {0x8DEF, "lu"},     {0x8F6C, "zhuan"},  {0x8F6F, "ruan"},
    {0x8F7D, "zai"},    {0x8F85, "fu"},     {0x8F91, "ji"},     {0x8FDC, "yuan"},
    {0x8FD0, "yun"},    {0x9000, "tui"},    {0x9009, "xuan"},   {0x914D, "pei"},
    {0x91CC, "li"},     {0x91CD, "zhong"},  {0x9489, "ding"},   {0x952E, "jian"},
    {0x9632, "fang"},   {0x963F, "a"},      {0x9664, "chu"},    {0x96C4, "xiong"},
    {0x96C5, "ya"},     {0x9762, "mian"},   {0x9891, "pin"},    {0x9875, "ye"},
    {0x9879, "xiang"},  {0x9996, "shou"},   {0x9999, "xiang"},  {0x9A71, "qu"},
    {0x9A8C, "yan"},    {0x9B54, "mo"},     {0x9ED1, "hei"},    {0x97F3, "yin"},
};
static const int PINYIN_TABLE_SIZE = sizeof(PINYIN_TABLE) / sizeof(PINYIN_TABLE[0]);

struct GbRange {
    int lo, hi;
    char initial;
};
static const GbRange GB_INITIAL_RANGES[] = {
    {45217, 45252, 'a'}, {45253, 45760, 'b'}, {45761, 46317, 'c'},
    {46318, 46825, 'd'}, {46826, 47009, 'e'}, {47010, 47296, 'f'},
    {47297, 47613, 'g'}, {47614, 48118, 'h'}, {48119, 49061, 'j'},
    {49062, 49323, 'k'}, {49324, 49895, 'l'}, {49896, 50370, 'm'},
    {50371, 50613, 'n'}, {50614, 50621, 'o'}, {50622, 50905, 'p'},
    {50906, 51386, 'q'}, {51387, 51445, 'r'}, {51446, 52217, 's'},
    {52218, 52697, 't'}, {52698, 52979, 'w'}, {52980, 53688, 'x'},
    {53689, 54480, 'y'}, {54481, 55289, 'z'},
};
static const int GB_INITIAL_RANGES_SIZE = sizeof(GB_INITIAL_RANGES) / sizeof(GB_INITIAL_RANGES[0]);

inline const char* pinyin_lookup(uint32_t cp) {
    int lo = 0, hi = PINYIN_TABLE_SIZE - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (PINYIN_TABLE[mid].codepoint == cp) return PINYIN_TABLE[mid].pinyin;
        if (PINYIN_TABLE[mid].codepoint < cp) lo = mid + 1;
        else hi = mid - 1;
    }
    return nullptr;
}
