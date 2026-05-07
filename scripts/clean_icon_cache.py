#!/usr/bin/env python3
"""
图标缓存清理脚本

用法:
    python clean_icon_cache.py          # 预览要清理的文件
    python clean_icon_cache.py --clean  # 实际执行清理
"""

import os
import sys

# 添加项目根目录到路径
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

from core.data_manager import DataManager


def main():
    dry_run = "--clean" not in sys.argv
    
    print("=" * 60)
    print("QuickLauncher 图标缓存清理工具")
    print("=" * 60)
    
    dm = DataManager()
    
    # 先显示当前状态
    print("\n【当前缓存状态】")
    stats = dm.get_icon_cache_stats()
    print(f"  总文件数: {stats['total_files']}")
    print(f"  总大小: {stats['total_size_mb']:.2f} MB")
    print(f"  无效文件: {stats['invalid_files']} ({stats['invalid_size_mb']:.2f} MB)")
    print("\n  按扩展名分类:")
    for ext, ext_stats in sorted(stats["by_extension"].items(), key=lambda x: -x[1]["size_mb"]):
        print(f"    {ext}: {ext_stats['count']} 个文件, {ext_stats['size_mb']:.2f} MB")
    
    print("\n" + "-" * 60)
    
    if dry_run:
        print("\n【预览模式】以下文件将被清理（实际运行请添加 --clean 参数）:")
    else:
        print("\n【清理模式】正在清理...")
    
    result = dm.clean_icon_cache(dry_run=dry_run)
    
    print("\n【清理结果】")
    print(f"  可执行文件: {result['exe_files_removed']} 个 ({result['exe_files_size_mb']:.2f} MB)")
    print(f"  过大文件: {result['large_files_removed']} 个 ({result['large_files_size_mb']:.2f} MB)")
    print(f"  孤儿文件: {result['orphan_files_removed']} 个 ({result['orphan_files_size_mb']:.2f} MB)")
    print(f"  重复文件: {result['duplicate_files_removed']} 个 ({result['duplicate_files_size_mb']:.2f} MB)")
    print(f"  ─────────────────────────────────────")
    print(f"  总计: {result['total_removed']} 个文件, {result['total_size_freed_mb']:.2f} MB")
    
    if dry_run:
        print("\n提示: 运行 'python clean_icon_cache.py --clean' 来实际执行清理")
    else:
        print("\n✓ 清理完成!")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
