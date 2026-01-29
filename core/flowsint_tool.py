"""
Lightweight Maigret wrapper for BAKASURA.
Calls maigret CLI directly without heavy Flowsint dependencies.
"""
import subprocess
import json
import tempfile
import os
from pathlib import Path


async def search_username_with_maigret(username: str) -> list[dict]:
    """
    Runs Maigret CLI tool to find social profiles.
    Returns a list of dictionaries with profile details.
    """
    print(f"[MAIGRET] Investigating username: {username} ...")
    
    temp_dir = tempfile.gettempdir()
    output_file = Path(temp_dir) / f"report_{username}_simple.json"
    
    # Clean up old file if exists
    if output_file.exists():
        try:
            output_file.unlink()
        except:
            pass
    
    try:
        # Determine maigret executable path
        # Check if running from venv
        venv_maigret = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.venv', 'Scripts', 'maigret.exe')
        if os.path.exists(venv_maigret):
            maigret_cmd = venv_maigret
        else:
            maigret_cmd = "maigret"  # Fallback to PATH
        
        # Run maigret CLI with proper encoding
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        
        result = subprocess.run(
            [maigret_cmd, username, "-J", "simple", "-fo", temp_dir],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minutes max
            encoding='utf-8',
            errors='replace',
            env=env
        )
        
        print(f"[MAIGRET] CLI finished with code: {result.returncode}")
        
        if result.stderr:
            # Filter out noise
            for line in result.stderr.split('\n'):
                if 'error' in line.lower() or 'fail' in line.lower():
                    print(f"[MAIGRET STDERR] {line}")
        
    except FileNotFoundError:
        print("[MAIGRET] ERROR: maigret command not found. Install with: pip install maigret")
        return []
    except subprocess.TimeoutExpired:
        print("[MAIGRET] ERROR: Scan timed out after 120 seconds")
        return []
    except Exception as e:
        print(f"[MAIGRET] ERROR during execution: {e}")
        return []
    
    # Parse results
    if not output_file.exists():
        print(f"[MAIGRET] No output file found at {output_file}")
        return []
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"[MAIGRET] Failed to parse output: {e}")
        return []
    
    # Format results
    clean_results = []
    false_positives = ["LeagueOfLegends", "Duolingo", "Spotify"]
    
    for platform, profile in raw_data.items():
        status = profile.get("status", {})
        
        # Only "Claimed" status means confirmed account
        if status.get("status") != "Claimed":
            continue
        
        # Skip known false positives
        if any(fp in platform for fp in false_positives):
            continue
        
        profile_url = status.get("url") or profile.get("url_user")
        if not profile_url:
            continue
        
        entry = {
            "platform": platform,
            "url": profile_url,
            "username": username,
            "title": f"Maigret Found: {platform}",
            "snippet": f"Verified Social Profile on {platform}.\nURL: {profile_url}\nMatch Confidence: High"
        }
        clean_results.append(entry)
    
    print(f"[MAIGRET] Found {len(clean_results)} verified profiles.")
    return clean_results
