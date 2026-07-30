#!/usr/bin/env python3
"""
PCB 缺陷检测系统 — 一键启动脚本
同时启动后端 (FastAPI :5000) 和前端 (Vite :5173)
"""

import subprocess
import sys
import os
import signal
import time
import threading
import urllib.request
import urllib.error
try:
    import queue
except ImportError:
    import Queue as queue

# 让控制台输出使用 UTF-8，避免 Vite 输出含 ➜ 等字符时
# 在 GBK 控制台下触发 UnicodeEncodeError 而意外退出并关闭服务
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 获取项目根目录
ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
FRONTEND_DIR = os.path.join(ROOT, "web2")


# ── 自动使用项目虚拟环境 ──
# 避免 `python start.py` 时用系统 Python（未装依赖）启动后端。
def _venv_python():
    for rel in (os.path.join(".venv", "Scripts", "python.exe"),
                os.path.join(".venv", "bin", "python")):
        p = os.path.abspath(os.path.join(ROOT, rel))
        if os.path.isfile(p):
            return p
    return None


VENV_PY = _venv_python() or sys.executable

# 若当前进程不是 venv 的 Python，则用 venv Python 重新启动本脚本
if VENV_PY != sys.executable:
    _in_venv = False
    try:
        _in_venv = os.path.samefile(sys.executable, VENV_PY)
    except (OSError, ValueError):
        _in_venv = False
    if not _in_venv:
        print(f"[*] 使用项目虚拟环境: {VENV_PY}")
        _rc = subprocess.call([VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])
        sys.exit(_rc)

processes = []


# 验证依赖
def check_deps():
    missing = []
    try:
        import uvicorn
    except ImportError:
        missing.append("uvicorn")
    try:
        import fastapi
    except ImportError:
        missing.append("fastapi")
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")
    try:
        import psutil
    except ImportError:
        missing.append("psutil")
    if missing:
        print("Missing Python dependencies. Run:")
        print(f"  pip install {' '.join(missing)}")
        return False
    # 检查前端依赖
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        print("Frontend dependencies not installed. Run:")
        print(f"  cd web2 && npm install")
        return False
    return True


def cleanup(signum=None, frame=None):
    print("\nStopping services...")
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        p.wait(timeout=5)
    print("All services stopped")
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# 依赖检查
if not check_deps():
    sys.exit(1)

print("=" * 56)
print("  PCB Defect Detection System - Starting")
print("=" * 56)

# 等待后端就绪（最多 15 秒）
print("\n[1/2] Starting Backend (FastAPI) ...")
backend_proc = subprocess.Popen(
    [VENV_PY, "-u", "main.py"],   # -u 禁用缓冲，实时输出
    cwd=BACKEND_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
)
processes.append(backend_proc)

# 轮询等待后端启动（最多 15 秒）
for i in range(30):
    if backend_proc.poll() is not None:
        print(f"[Backend] 进程已退出 (code={backend_proc.returncode})，请检查错误日志")
        cleanup()
    try:
        urllib.request.urlopen("http://localhost:5000/api/ping", timeout=1)
        print("[Backend] 就绪")
        break
    except urllib.error.URLError:
        time.sleep(0.5)
else:
    print("[Backend] 启动超时，继续启动前端...")

# 2. 启动前端
print("[2/2] Starting Frontend (Vite)   ...")
frontend_proc = subprocess.Popen(
    ["npx.cmd", "vite", "--host", "0.0.0.0", "--port", "5173"],
    cwd=FRONTEND_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
)
processes.append(frontend_proc)

# 等待服务就绪
time.sleep(2)

print("\n" + "=" * 56)
print("  Services Started Successfully")
print("=" * 56)
print(f"  Frontend: http://localhost:5173")
print(f"  Backend:  http://localhost:5000")
print(f"  WS:       ws://localhost:5000/ws")
print(f"\n  Login:    admin / pcb_admin")
print("=" * 56)
print("  Press Ctrl+C to stop all services")
print("=" * 56)

# 使用线程读取子进程输出，避免主线程被 readline 阻塞导致 Ctrl+C 无效
output_queue: queue.Queue = queue.Queue()

def reader_thread(proc, label):
    try:
        for line in iter(proc.stdout.readline, ""):
            output_queue.put((label, line.rstrip()))
    except Exception:
        pass

for i, p in enumerate(processes):
    label = "[Frontend]" if i == 1 else "[Backend]"
    t = threading.Thread(target=reader_thread, args=(p, label), daemon=True)
    t.start()

# 实时输出日志
try:
    while True:
        try:
            label, line = output_queue.get(timeout=0.2)
            print(f"{label} {line}", flush=True)
        except queue.Empty:
            pass
        # 检查进程是否退出
        for i, p in enumerate(processes):
            if p.poll() is not None:
                # 等待队列清空
                time.sleep(0.3)
                while not output_queue.empty():
                    try:
                        label, line = output_queue.get_nowait()
                        print(f"{label} {line}", flush=True)
                    except queue.Empty:
                        break
                print(f"\nProcess {i} exited (code={p.returncode})")
                cleanup()
except KeyboardInterrupt:
    cleanup()
except Exception as e:
    print(f"\nError: {e}")
    cleanup()
