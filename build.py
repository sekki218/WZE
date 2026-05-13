# Build script for Zapret Auto-Selector
# Creates a standalone Windows executable using PyInstaller

import os
import sys
import subprocess

def build():
    print("🔨 Building Zapret Auto-Selector...")
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Build command
    build_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "ZapretAutoSelector",
        "--icon=NONE",  # Add icon path if you have one
        "--add-data", "bin;bin",
        "--add-data", "lists;lists",
        "--add-data", "utils;utils",
        "--hidden-import", "PyQt6",
        "--hidden-import", "requests",
        "main.py"
    ]
    
    print(f"Running: {' '.join(build_cmd)}")
    subprocess.check_call(build_cmd)
    
    print("\n✅ Build completed!")
    print("Executable location: dist/ZapretAutoSelector.exe")
    
    # Clean up build folder (optional)
    # Uncomment to remove build artifacts
    # import shutil
    # shutil.rmtree('build', ignore_errors=True)
    # os.remove('ZapretAutoSelector.spec')

if __name__ == "__main__":
    build()
