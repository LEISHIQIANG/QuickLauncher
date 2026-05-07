
import time
import threading
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hooks.mouse_hook import MouseHook

def stress_test():
    print("Initializing MouseHook Stress Test...")
    
    hook = MouseHook()
    counter = 0
    
    def on_click(x, y):
        nonlocal counter
        counter += 1
        print(f"Click #{counter} detected at {x}, {y}")
        # Simulate some work
        # time.sleep(0.01) 
    
    print("Installing hook...")
    success = hook.install(on_click)
    if not success:
        print("Failed to install hook!")
        return
        
    print("Hook installed. Please press MIDDLE MOUSE BUTTON rapidly.")
    print("The watchdog is active. If the mouse gets stuck, it should auto-release in ~1s.")
    print("Running for 20 seconds...")
    
    try:
        for i in range(20):
            time.sleep(1)
            print(f"Time: {i+1}/20s | Clicks detected: {counter}")
    except KeyboardInterrupt:
        pass
        
    print("Uninstalling hook...")
    hook.uninstall()
    print("Test complete.")

if __name__ == "__main__":
    stress_test()
