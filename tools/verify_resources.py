
import os
import sys

def verify():
    print("Verifying resource paths...")
    
    # Simulate finding app.ico like in ui/tray_app.py
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Project root (tools/..)
    
    print(f"Project root: {base_dir}")
    
    possible_paths = [
        os.path.join(base_dir, 'assets', 'app.ico'),
        os.path.join(base_dir, 'app.ico'),
    ]
    
    found = False
    for path in possible_paths:
        if os.path.exists(path):
            print(f"[OK] Found app.ico at: {path}")
            found = True
            break
            
    if not found:
        print("[FAIL] app.ico not found!")
        
    # Verify setting.ico
    possible_setting_paths = [
        os.path.join(base_dir, 'assets', 'setting.ico'),
        os.path.join(base_dir, 'setting.ico'),
    ]
    
    found_setting = False
    for path in possible_setting_paths:
        if os.path.exists(path):
            print(f"[OK] Found setting.ico at: {path}")
            found_setting = True
            break
            
    if not found_setting:
        print("[FAIL] setting.ico not found!")

if __name__ == "__main__":
    verify()
