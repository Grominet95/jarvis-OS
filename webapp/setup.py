#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_command(cmd, name, install_url=None, use_where=False):
    found = False
    
    if use_where and sys.platform == "win32":
        try:
            result = subprocess.run(["where", cmd], capture_output=True, text=True, timeout=5)
            found = result.returncode == 0
        except:
            pass
    
    if not found:
        found = shutil.which(cmd) is not None
    
    if found:
        try:
            version = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5, shell=sys.platform == "win32")
            if version.returncode == 0:
                version_str = version.stdout.strip().split('\n')[0].split()[0] if version.stdout else "unknown"
                print(f"✓ {name} found: {version_str}")
                return True
        except (subprocess.TimeoutExpired, Exception):
            pass
    
    print(f"✗ {name} not found")
    if install_url:
        print(f"  Install from: {install_url}")
    return False

def check_python():
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        print(f"✓ Python found: {version.major}.{version.minor}.{version.micro}")
        return True
    print(f"✗ Python 3.10+ required, found {version.major}.{version.minor}.{version.micro}")
    print("  Install from: https://www.python.org/downloads/")
    return False

def check_uv():
    return check_command("uv", "uv", "https://docs.astral.sh/uv/getting-started/installation/")

def check_node():
    return check_command("node", "Node.js", "https://nodejs.org/")

def check_npm():
    npm_result = check_command("npm", "npm", "https://nodejs.org/", use_where=True)
    if not npm_result:
        print("  Trying alternative detection method...")
        try:
            result = subprocess.run(
                ["npm", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=5, 
                shell=sys.platform == "win32"
            )
            if result.returncode == 0:
                print(f"✓ npm found: {result.stdout.strip()}")
                return True
        except:
            pass
        return False
    return True

def setup_env_file():
    env_path = Path(".env")
    env_example_path = Path("env.example")
    
    if env_path.exists():
        print("✓ .env file already exists")
        return True
    
    if not env_example_path.exists():
        print("✗ env.example not found")
        return False
    
    print("Creating .env file from env.example...")
    shutil.copy(env_example_path, env_path)
    print("✓ .env file created")
    print("⚠ Please edit .env and add your API keys:")
    print("  - DEEPGRAM_API_KEY")
    print("  - OPENAI_API_KEY")
    print("  - CARTESIA_API_KEY")
    return True

def run_uv_sync():
    print("\nInstalling Python dependencies with uv...")
    try:
        result = subprocess.run(["uv", "sync"], check=False)
        if result.returncode == 0:
            print("✓ Python dependencies installed successfully")
            return True
        else:
            print("✗ Failed to install Python dependencies")
            print("  Try running 'uv sync' manually to see the error")
            return False
    except FileNotFoundError:
        print("✗ uv command not found")
        return False
    except Exception as e:
        print(f"✗ Error running uv sync: {e}")
        return False

def run_npm_install():
    package_json = Path("package.json")
    if not package_json.exists():
        print("⚠ package.json not found, skipping npm install")
        return True
    
    print("\nInstalling Electron dependencies with npm...")
    try:
        result = subprocess.run(
            ["npm", "install"], 
            check=False,
            shell=sys.platform == "win32"
        )
        if result.returncode == 0:
            print("✓ Electron dependencies installed successfully")
            return True
        else:
            print("✗ Failed to install Electron dependencies")
            print("  Try running 'npm install' manually to see the error")
            return False
    except FileNotFoundError:
        print("✗ npm command not found")
        return False
    except Exception as e:
        print(f"✗ Error running npm install: {e}")
        return False

def main():
    print("=" * 60)
    print("Jarvis - Project Setup")
    print("=" * 60)
    print()
    
    all_ok = True
    
    print("Checking prerequisites...")
    print("-" * 60)
    
    if not check_python():
        all_ok = False
    
    if not check_uv():
        all_ok = False
    
    node_ok = check_node()
    if not node_ok:
        all_ok = False
    
    npm_ok = check_npm()
    if not npm_ok and node_ok:
        print("⚠ npm not detected in PATH, but Node.js is installed")
        print("  npm should come with Node.js - will try to use it anyway")
    
    print()
    
    if not all_ok:
        print("✗ Some prerequisites are missing. Please install them and run this script again.")
        sys.exit(1)
    
    print("Setting up project files...")
    print("-" * 60)
    
    if not setup_env_file():
        print("✗ Failed to setup .env file")
        sys.exit(1)
    
    print()
    
    if not run_uv_sync():
        print("✗ Setup failed")
        sys.exit(1)
    
    if not run_npm_install():
        print("⚠ Electron dependencies installation failed, but you can continue")
        print("  Run 'npm install' manually if you want to use the Electron app")
    
    print()
    print("=" * 60)
    print("✓ Setup completed successfully!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Edit .env and add your API keys")
    print("2. Run the bot with:")
    print("   - Electron app: ./start.sh (Linux/Mac) or start.bat (Windows)")
    print("   - Command line: uv run bot.py")
    print()

if __name__ == "__main__":
    main()
