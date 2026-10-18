"""Dark Tk monitor. Tk stays on the main thread; sampling runs in a worker."""
from collections import deque
import os
import platform
import queue
import signal
import threading
import time

from .core import atomic_json, read_config
from .metrics import Sampler


def run(p, smoke_seconds=None):
    import fcntl
    import psutil
    p["root"].mkdir(parents=True, exist_ok=True)
    with (p["root"] / "widget.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # Existing widget owns the lock; never overwrite its heartbeat.
        state = {"pid": os.getpid(), "createTime": psutil.Process().create_time(), "status": "starting"}

        def record(status, error=None):
            state.update(status=status, updatedAt=time.time())
            if error:
                state["errorCode"] = error
            atomic_json(p["state"], state)

        root = None
        stopped = threading.Event()
        try:
            import tkinter as tk
            cfg = read_config(p["config"])
            record("starting")
            root = tk.Tk()
            root.title("Compact Task Manager")
            root.configure(bg="#191919")
            root.resizable(False, False)
            root.attributes("-topmost", cfg["alwaysOnTop"])
            row_count = 7 if platform.system() == "Darwin" else 5
            width, height = cfg["width"], 35 + row_count * 81
            # Portable v0.2 uses primary-screen placement. Compositors may override it.
            x = root.winfo_screenwidth() - width - 24 if cfg["x"] is None else cfg["x"]
            y = 40 if cfg["y"] is None else cfg["y"]
            x = max(0, min(x, root.winfo_screenwidth() - width))
            y = max(0, min(y, root.winfo_screenheight() - height))
            root.geometry("%dx%d+%d+%d" % (width, height, x, y))
            canvas = tk.Canvas(root, bg="#191919", highlightthickness=0, width=width, height=height)
            canvas.pack(fill="both", expand=True)
            histories = [deque(maxlen=60) for _ in range(row_count)]
            updates = queue.Queue(maxsize=1)

            def sample_worker():
                try:
                    sampler = Sampler(psutil, platform.system())
                    while not stopped.wait(cfg["intervalSeconds"]):
                        item = sampler.sample()
                        if updates.full():
                            try:
                                updates.get_nowait()
                            except queue.Empty:
                                pass
                        updates.put_nowait(item)
                except Exception as exc:
                    if updates.full():
                        try:
                            updates.get_nowait()
                        except queue.Empty:
                            pass
                    updates.put_nowait(type(exc).__name__)

            def close():
                stopped.set()
                cfg.update(x=root.winfo_x(), y=root.winfo_y())
                atomic_json(p["config"], cfg)
                record("error" if state.get("errorCode") else "stopped")
                root.destroy()

            root.protocol("WM_DELETE_WINDOW", close)
            old_term = signal.signal(signal.SIGTERM, lambda *_: root.after(0, close))
            threading.Thread(target=sample_worker, daemon=True).start()

            def refresh():
                try:
                    item = updates.get_nowait()
                except queue.Empty:
                    root.after(200, refresh)
                    return
                if isinstance(item, str):
                    record("error", "sampling_" + item)
                    canvas.delete("all")
                    canvas.create_text(16, 24, anchor="nw", text="Sampling failed. Run diagnose.", fill="#ffffff")
                    return
                canvas.delete("all")
                colors = ("#58bbdf", "#ae87dd", "#8cbd73", "#db8b66", "#d983ca", "#8cbd73", "#e1ba68")
                for i, (name, value, detail, percent) in enumerate(item):
                    top = 12 + i * 81
                    graph_left, graph_top, graph_width, graph_height = 12, top + 7, 82, 54
                    canvas.create_rectangle(graph_left, graph_top, graph_left + graph_width,
                                            graph_top + graph_height, fill="#252525", outline="#606060")
                    if name == "Pressure":
                        color = {"Normal": "#8cbd73", "Warning": "#e1ba68", "Critical": "#ef7676"}.get(detail, "#999999")
                        canvas.create_oval(graph_left + 28, graph_top + 14, graph_left + 54,
                                           graph_top + 40, fill=color, outline=color)
                    histories[i].append(value)
                    valid = [v for v in histories[i] if v is not None]
                    ceiling = 100 if percent else max([1] + valid)
                    segment = []
                    for j, v in enumerate(histories[i]):
                        if v is None:
                            if len(segment) >= 4:
                                canvas.create_line(*segment, fill=colors[i])
                            segment = []
                            continue
                        segment.extend((graph_left + graph_width * j / 59,
                                        graph_top + graph_height * (1 - min(v / ceiling, 1))))
                    if len(segment) >= 4:
                        canvas.create_line(*segment, fill=colors[i])
                    caption = name + ("  %.0f%%" % value if percent and value is not None else "")
                    canvas.create_text(108, top + 5, anchor="nw", text=caption, fill="#ffffff", font=("TkDefaultFont", 12, "bold"))
                    canvas.create_text(108, top + 31, anchor="nw", text=detail, fill="#c8c8c8", width=width - 120, font=("TkDefaultFont", 10))
                canvas.create_text(12, height - 18, anchor="nw", text="60 samples  •  Disk/network graphs auto-scale", fill="#999999", font=("TkDefaultFont", 9))
                state["samplesDrawn"] = state.get("samplesDrawn", 0) + 1
                record("running")  # A real sample was drawn, not just a process launched.
                root.after(200, refresh)

            canvas.create_text(16, 24, anchor="nw", text="Waiting for the first sample…", fill="#cccccc")
            root.after(200, refresh)
            if smoke_seconds:
                root.after(int(smoke_seconds * 1000), close)
            root.mainloop()
            signal.signal(signal.SIGTERM, old_term)
            return 0 if state["status"] != "error" else 1
        except Exception as exc:
            record("error", type(exc).__name__)
            return 1
        finally:
            stopped.set()
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass
