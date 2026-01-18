import subprocess
import time
import requests
import sys
import os
import signal
import json

# Ensure we are in the root
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def run_test():
    print(">>> [TEST] Killing old instances on Port 8001...")
    # Bruteforce kill python to ensure port is free
    subprocess.call("taskkill /F /IM python.exe /FI \"WINDOWTITLE ne Bakasura Launcher\"", shell=True)
    subprocess.call("taskkill /F /IM uvicorn.exe", shell=True)
    time.sleep(2)
    
    print(">>> [TEST] Starting Backend (core/main.py)...")
    # Launch backend as a subprocess
    # We use the same command as the batch file: python core/main.py
    # We assume the environment is already activated or we use the full path to python
    python_exe = sys.executable
    
    # Start the server (cwd is 'core', so just 'main.py')
    backend_process = subprocess.Popen(
        [python_exe, "main.py"],
        cwd="core",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered
    )

    print(">>> [TEST] Backend PID:", backend_process.pid)
    
    # Wait for server to be ready (poll port or wait for log line)
    server_ready = False
    base_url = "http://127.0.0.1:8001"
    
    print(">>> [TEST] Waiting for server port 8001...")
    for i in range(30):
        try:
            resp = requests.get(base_url, timeout=1)
            if resp.status_code == 200:
                print(">>> [TEST] Server is UP!")
                server_ready = True
                break
        except:
            time.sleep(1)
            print(".", end="", flush=True)
            
    if not server_ready:
        print("\n>>> [TEST FAIL] Server failed to start in 30s.")
        # Dump logs
        outs, errs = backend_process.communicate(timeout=5)
        print("STDOUT:\n", outs)
        print("STDERR:\n", errs)
        backend_process.kill()
        return

    # Send PAYLOAD
    payload = {
        "profile": {
            "name": "Павел Столбовский",
            "city": "Барнаул",
            "country": "Russia"
        }
    }
    
    print(f"\n>>> [TEST] Sending Analysis Request: {json.dumps(payload)}")
    
    # Capture logs in real-time or dump at end
    # Since we use PIPE, we can't see them real-time easily in this simple script 
    # without threading. But we can dump them after the request.
    
    try:
        start_time = time.time()
        resp = requests.post(f"{base_url}/api/analyze", json=payload, timeout=120)
        duration = time.time() - start_time
        
        print(f">>> [TEST] Response received in {duration:.2f}s")
        print(">>> [TEST] Status:", resp.status_code)
        
        # DUMP LOGS NOW
        print("\n>>> [TEST] Backend Logs (Snapshot):")
        # This is tricky with subprocess.PIPE if it blocked. 
        # But for a short test it usually buffers OK. 
        # Actually, if we want to see logs, we should probably let them inherit stdout/stderr 
        # OR kill and read.
        
        try:
            data = resp.json()
            print(">>> [TEST] Response Body (Truncated):")
            print(str(data)[:1000])
            
            if resp.status_code == 200 and "gathered_data" in data:
                items = data.get("gathered_data", [])
                print(f">>> [TEST] SUCCESS! Found {len(items)} items.")
                for item in items:
                    print(f"   - {item.get('title')[:50]}... ({len(item.get('snippet', ''))} chars)")
            else:
                 print(">>> [TEST FAIL] Invalid response format.")
                 
        except:
            print(">>> [TEST FAIL] Response is not JSON:", resp.text)
            
    except Exception as e:
        print(f">>> [TEST FAIL] Request Error: {e}")

    # CLEANUP
    print("\n>>> [TEST] Killing Backend...")
    # Windows kill
    subprocess.call(['taskkill', '/F', '/T', '/PID', str(backend_process.pid)])
    
    # Read remaining logs
    outs, errs = backend_process.communicate()
    if outs:
        print("\n--- BACKEND STDOUT ---\n")
        print(outs)
    if errs:
        print("\n--- BACKEND STDERR ---\n")
        print(errs)
    
if __name__ == "__main__":
    run_test()
