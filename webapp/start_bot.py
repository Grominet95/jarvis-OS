#!/usr/bin/env python3

import sys
import os
import subprocess
import io
from pathlib import Path

if sys.platform == "win32":
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def main():
    script_dir = Path(__file__).parent
    bot_script = script_dir / "bot.py"
    
    if not bot_script.exists():
        print(f"Error: bot.py not found at {bot_script}", file=sys.stderr)
        sys.exit(1)
    
    os.chdir(script_dir)
    
    cmd = ["uv", "run", "bot.py"]
    
    try:
        process = subprocess.Popen(
            cmd,
            cwd=script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )
        
        if process.stdout:
            for line in process.stdout:
                print(line, end='', flush=True)
        
        process.wait()
        sys.exit(process.returncode)
    except KeyboardInterrupt:
        if process:
            process.terminate()
        sys.exit(0)
    except Exception as e:
        print(f"Error running bot: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
