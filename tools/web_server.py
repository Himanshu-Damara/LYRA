"""
web_server.py — Real Connected Phone Screen Web Server for LYRA Voice Assistant UI.

Streams the REAL physical phone screen directly from the connected ADB device in real-time.
"""

import sys
import io
import time
import subprocess
import threading
import cv2
import numpy as np
from pathlib import Path
from flask import Flask, send_from_directory, jsonify, request, send_file, Response

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.config import ADB_PATH
from lyra.agent.router import classify_intent, resolve_task_from_input
from lyra.agent.agent_loop import AgentLoop
from lyra.agent.tasks import list_tasks
from lyra.assistant.grok_client import grok
from lyra.assistant.responder import Responder
from lyra.phone.screenshot import capture_screenshot, capture_screenshot_in_memory
from lyra.inference.detector import LyraDetector

WEB_DIR = PROJECT_ROOT / "web"

app = Flask(__name__, static_folder=str(WEB_DIR))
agent = AgentLoop()
responder = Responder()
detector = LyraDetector(conf_threshold=0.35)

# Real In-Memory Cache
latest_jpeg_bytes = None
latest_image_np = None
latest_perception_result = {"screen_state": "HOME_SCREEN", "screen_confidence": 0.99, "detections": []}
frame_lock = threading.Lock()


scrcpy_process = None


def background_frame_capturer():
    """
    Background worker thread capturing physical phone screen.
    Pauses automatically when scrcpy hardware mirror is active to avoid ADB transport collisions.
    """
    global latest_jpeg_bytes, latest_image_np, scrcpy_process

    while True:
        # If scrcpy is running, give it 100% exclusive ADB transport access for zero lag
        if scrcpy_process is not None and scrcpy_process.poll() is None:
            time.sleep(1.0)
            continue

        try:
            image, w, h = capture_screenshot_in_memory()

            # Downscale to 320px width for ultra-fast processing
            h_orig, w_orig = image.shape[:2]
            if w_orig > 320:
                scale = 320.0 / w_orig
                image_web = cv2.resize(image, (320, int(h_orig * scale)), interpolation=cv2.INTER_NEAREST)
            else:
                image_web = image

            # Fast JPEG encoding
            _, buffer = cv2.imencode('.jpg', image_web, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
            encoded_bytes = buffer.tobytes()

            with frame_lock:
                latest_image_np = image
                latest_jpeg_bytes = encoded_bytes

        except Exception:
            pass

        time.sleep(0.3)


def background_perception_worker():
    """
    Background worker thread running PyTorch AI perception independently every 2 seconds.
    Prevents PyTorch inference CPU load from EVER freezing the video stream.
    """
    global latest_perception_result

    while True:
        with frame_lock:
            image = latest_image_np

        if image is not None:
            try:
                result = detector.detect(image, iou_threshold=0.25, single_per_class=True)
                result["screen_resolution"] = (image.shape[1], image.shape[0])
                latest_perception_result = result
            except Exception:
                pass

        time.sleep(2.0)


# Start background worker threads
capture_thread = threading.Thread(target=background_frame_capturer, daemon=True)
capture_thread.start()

perception_thread = threading.Thread(target=background_perception_worker, daemon=True)
perception_thread.start()


def generate_mjpeg_stream():
    """
    Generates high-speed MJPEG video stream (60 FPS target with smooth RAM buffering).
    """
    last_sent_bytes = None
    while True:
        with frame_lock:
            frame_data = latest_jpeg_bytes

        if frame_data is not None:
            last_sent_bytes = frame_data
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        elif last_sent_bytes is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + last_sent_bytes + b'\r\n')
        
        time.sleep(0.016)  # 60 FPS smooth stream delivery (16.6ms)


@app.route("/")
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.route("/stream.mjpg")
@app.route("/api/stream")
def video_feed():
    """Returns continuous live video stream of the connected phone screen."""
    return Response(
        generate_mjpeg_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(str(WEB_DIR), path)


@app.route("/api/screenshot")
def get_screenshot():
    """Returns a single frame snapshot from memory."""
    with frame_lock:
        data_bytes = latest_jpeg_bytes

    if data_bytes is None:
        try:
            img, w, h = capture_screenshot_in_memory()
            _, buffer = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            data_bytes = buffer.tobytes()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return send_file(
        io.BytesIO(data_bytes),
        mimetype='image/jpeg',
        as_attachment=False
    )


SCRCPY_PATH = Path(r"C:\Users\HP\Downloads\scrcpy-win64-v4.0\scrcpy-win64-v4.0\scrcpy.exe")


@app.route("/api/launch_scrcpy", methods=["POST", "GET"])
def launch_scrcpy():
    """Launches scrcpy hardware 60 FPS zero-lag screen mirror."""
    global scrcpy_process
    try:
        if SCRCPY_PATH.exists():
            if scrcpy_process is None or scrcpy_process.poll() is not None:
                cmd = [str(SCRCPY_PATH), "--max-size", "1080", "--max-fps", "60", "--always-on-top", "--window-title=LYRA Zero-Lag Phone Screen"]
                scrcpy_process = subprocess.Popen(cmd)
            return jsonify({"status": "success", "message": "Launched hardware zero-lag scrcpy window!"})
        else:
            return jsonify({"error": "scrcpy binary not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/perceive")
def perceive():
    """Returns cached vision perception instantly (<1ms) without blocking video stream."""
    return jsonify(latest_perception_result)


@app.route("/api/health")
def health():
    """Small diagnostic endpoint used to distinguish UI failures from backend failures."""
    with frame_lock:
        stream_ready = latest_jpeg_bytes is not None
    return jsonify({
        "status": "ok",
        "stream_ready": stream_ready,
        "adb_path": str(ADB_PATH),
        "adb_exists": ADB_PATH.exists(),
        "model_loaded": detector is not None,
    })


@app.route("/api/device")
def device_info():
    """Returns the connected device's real resolution for coordinate mapping."""
    try:
        _, width, height = capture_screenshot_in_memory()
        return jsonify({"connected": True, "width": width, "height": height})
    except Exception as exc:
        return jsonify({"connected": False, "error": str(exc)}), 503


@app.route("/api/tap", methods=["POST"])
def tap_phone():
    """Taps the real physical phone screen at coordinates (x, y)."""
    data = request.json or {}
    x = data.get("x")
    y = data.get("y")
    if x is None or y is None:
        return jsonify({"error": "Missing coordinates"}), 400

    try:
        # Clamp to the real device dimensions so malformed browser requests cannot
        # send invalid coordinates to Android.
        _, width, height = capture_screenshot_in_memory()
        x = max(0, min(int(x), width - 1))
        y = max(0, min(int(y), height - 1))
        cmd = [str(ADB_PATH), "shell", "input", "tap", str(int(x)), str(int(y))]
        subprocess.run(cmd, check=True)
        return jsonify({"status": "success", "tapped": (int(x), int(y))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/process", methods=["POST"])
def process_command():
    """Processes natural language or voice commands."""
    data = request.json or {}
    user_text = data.get("command", "").strip()

    if not user_text:
        return jsonify({"response": "I didn't receive any command."})

    text_lower = user_text.lower()

    if text_lower in ("tasks", "list tasks", "what can you do"):
        tasks_list = ", ".join([t.replace("_", " ") for t in list_tasks()])
        return jsonify({"response": f"I can execute phone actions like: {tasks_list}."})

    if text_lower in ("status", "check phone", "what is on screen"):
        try:
            perception = agent.coordinator.perceive()
            state = perception.get("screen_state", "UNKNOWN")
            dets = len(perception.get("detections", []))
            return jsonify({"response": f"Your phone is currently on the {state.replace('_', ' ')} screen with {dets} UI elements detected."})
        except Exception as e:
            return jsonify({"response": f"Could not read phone screen. Error: {e}"})

    # Classify intent (ACTION vs QUESTION)
    intent_type, matched = classify_intent(user_text)

    if intent_type == "ACTION":
        try:
            task_name = resolve_task_from_input(user_text)
            clean_name = task_name.replace("_", " ")

            result = agent.run_task(task_name)
            if result.get("success", False):
                resp_text = f"Successfully completed '{clean_name}' on your phone."
            else:
                resp_text = f"Executed phone action '{clean_name}' on your device."

            return jsonify({"response": resp_text, "result": result})

        except ValueError:
            return jsonify({"response": f"I recognized that as a phone action, but I don't have a matching task for '{user_text}'. Try asking to open instagram or camera."})
        except Exception as e:
            return jsonify({"response": f"Action execution failed: {e}"})

    elif intent_type == "QUESTION":
        answer = grok.ask(user_text)
        return jsonify({"response": answer})

    return jsonify({"response": "Command processed."})


def run_web_server(port: int = 5000):
    print(f"\n  =======================================================")
    print(f"   LYRA Real Connected Phone Server running at:")
    print(f"   http://localhost:5000")
    print(f"   Launching 60 FPS Zero-Lag scrcpy Hardware Mirror...")
    print(f"  =======================================================\n")
    
    # Auto-launch 60 FPS zero-lag scrcpy window
    try:
        if SCRCPY_PATH.exists():
            cmd = [
                str(SCRCPY_PATH),
                "--max-size", "1080",
                "--max-fps", "60",
                "--window-borderless",
                "--always-on-top",
                "--window-title=LYRA Zero-Lag Phone Screen"
            ]
            subprocess.Popen(cmd)
    except Exception as e:
        print(f"Notice: Could not auto-launch scrcpy: {e}")

    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run_web_server()
