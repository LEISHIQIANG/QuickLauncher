#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
QuickLauncher Code Obfuscator
"""

import os
import sys
import shutil

# ============================================
# Configuration
# ============================================
OUTPUT_DIR = "obfuscated_src"
MAIN_FILE = "main.py"
EXTRA_FILES = ["qt_compat.py"]
SOURCE_DIRS = ["core", "hooks", "ui"]

EXCLUDE_DIRS = [
    '__pycache__', 
    '.git', 
    '.venv', 
    'venv',
    'dist', 
    'build',
    'obfuscated_src',
]
# ============================================


def install_minifier():
    try:
        import python_minifier
        return True
    except ImportError:
        print("  Installing python-minifier...")
        os.system(f'"{sys.executable}" -m pip install python-minifier -q -i https://pypi.tuna.tsinghua.edu.cn/simple')
        try:
            import python_minifier
            return True
        except ImportError:
            print("  [!] Install failed. Run: pip install python-minifier")
            return False


def obfuscate_code(code):
    import python_minifier
    
    return python_minifier.minify(
        code,
        rename_locals=True,
        rename_globals=False,
        remove_literal_statements=True,
        remove_annotations=True,
        remove_pass=True,
        remove_object_base=True,
        hoist_literals=False,
        convert_posargs_to_args=False,
    )


def obfuscate_file(src_path, dst_path):
    try:
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        if not code.strip():
            shutil.copy2(src_path, dst_path)
            return True, "skip"
        
        obfuscated = obfuscate_code(code)
        
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, 'w', encoding='utf-8') as f:
            f.write(obfuscated)
        
        return True, "ok"
        
    except Exception as e:
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return False, str(e)


def obfuscate_directory(src_dir, dst_dir):
    results = {"success": 0, "failed": 0, "skipped": 0}
    
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for filename in files:
            src_path = os.path.join(root, filename)
            rel_path = os.path.relpath(src_path, src_dir)
            dst_path = os.path.join(dst_dir, rel_path)
            
            if filename.endswith('.py'):
                print(f"    {rel_path}", end=" ... ")
                success, msg = obfuscate_file(src_path, dst_path)
                
                if msg == "skip":
                    print("skip")
                    results["skipped"] += 1
                elif success:
                    print("ok")
                    results["success"] += 1
                else:
                    print(f"fail ({msg})")
                    results["failed"] += 1
            else:
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
    
    return results


def main():
    print()
    print("=" * 55)
    print("  QuickLauncher Code Obfuscator")
    print("=" * 55)
    print()
    
    print("[1/4] Checking dependencies...")
    if not install_minifier():
        sys.exit(1)
    print("  OK: python-minifier ready")
    
    print()
    print("[2/4] Preparing output directory...")
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    print(f"  OK: Created {OUTPUT_DIR}/")
    
    total = {"success": 0, "failed": 0, "skipped": 0}
    
    print()
    print("[3/4] Obfuscating root files...")
    
    root_files = [MAIN_FILE] + EXTRA_FILES
    for filename in root_files:
        if os.path.exists(filename):
            print(f"    {filename}", end=" ... ")
            dst_path = os.path.join(OUTPUT_DIR, filename)
            success, msg = obfuscate_file(filename, dst_path)
            if success:
                print("ok")
                total["success"] += 1
            else:
                print(f"fail ({msg})")
                total["failed"] += 1
    
    print()
    print("[4/4] Obfuscating source directories...")
    
    for src_dir in SOURCE_DIRS:
        if os.path.exists(src_dir):
            print(f"\n  [{src_dir}/]")
            dst_dir = os.path.join(OUTPUT_DIR, src_dir)
            results = obfuscate_directory(src_dir, dst_dir)
            total["success"] += results["success"]
            total["failed"] += results["failed"]
            total["skipped"] += results["skipped"]
        else:
            print(f"  [!] Directory not found: {src_dir}/")
    
    print()
    print("=" * 55)
    print("  Obfuscation Complete!")
    print("=" * 55)
    print(f"  Success: {total['success']} files")
    print(f"  Failed:  {total['failed']} files (copied original)")
    print(f"  Skipped: {total['skipped']} files")
    print(f"  Output:  {os.path.abspath(OUTPUT_DIR)}/")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())