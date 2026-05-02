# Hand Gesture Recognition — C++ Setup Guide

## Model

The `gesture_recognizer.task` model is already on your machine:

```
C:\Users\media\mediapipe_python\mediapipe-env\Include\gesture_recognizer.task
```

It recognizes: **None, Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up, Victory, ILoveYou**

---

## Option A — Build with Bazel (Official, Recommended)

MediaPipe's primary build system is Bazel. This is the cleanest path on Linux/macOS.
On Windows it works but requires WSL or careful VS toolchain setup.

### 1. Prerequisites

```bash
# Linux / WSL
sudo apt-get install -y bazel-6.1.0 python3 git build-essential

# macOS
brew install bazel
```

### 2. Clone MediaPipe

```bash
git clone https://github.com/google-ai-edge/mediapipe.git
cd mediapipe
```

### 3. Copy this project into the MediaPipe tree

```bash
mkdir -p mediapipe/examples/desktop/hand_gesture
cp /path/to/hand_gesture_recognition.cpp mediapipe/examples/desktop/hand_gesture/
cp /path/to/BUILD                         mediapipe/examples/desktop/hand_gesture/
```

### 4. Build

```bash
# From the mediapipe/ repo root:
bazel build -c opt //mediapipe/examples/desktop/hand_gesture:hand_gesture_recognition

# Run (pass model path and optional camera index)
bazel-bin/mediapipe/examples/desktop/hand_gesture/hand_gesture_recognition \
    /full/path/to/gesture_recognizer.task 0
```

---

## Option B — Build with CMake (Windows, VS2022)

### 1. Prerequisites

- Visual Studio 2022 with "Desktop development with C++" workload
- CMake 3.18+
- OpenCV 4.x (`winget install -e --id OpenCV.OpenCV` or vcpkg)
- MediaPipe source cloned (same as Bazel step 2 above)

### 2. Build MediaPipe Tasks library via Bazel first

Even if you use CMake for your project, you need the MediaPipe .lib/.dll:

```bash
# In WSL or Git Bash with Bazel:
bazel build -c opt //mediapipe/tasks/cc/vision/gesture_recognizer:gesture_recognizer
```

### 3. Configure and build

```bat
cmake -B build -S . ^
    -DMEDIAPIPE_ROOT=C:\path\to\mediapipe ^
    -DOpenCV_DIR=C:\path\to\opencv\build

cmake --build build --config Release
```

### 4. Run

```bat
build\Release\hand_gesture_recognition.exe ^
    "C:\Users\media\mediapipe_python\mediapipe-env\Include\gesture_recognizer.task" ^
    0
```

---

## Controls

| Key | Action |
|-----|--------|
| Q / ESC | Quit |
| SPACE | Pause / Resume |

---

## Supported Gestures

| Label | Description |
|-------|-------------|
| `None` | No recognized gesture |
| `Closed_Fist` | Fist |
| `Open_Palm` | Open hand |
| `Pointing_Up` | Index finger up |
| `Thumb_Down` | Thumbs down |
| `Thumb_Up` | Thumbs up |
| `Victory` | V / Peace sign |
| `ILoveYou` | ILY hand sign |

---

## Quickest Path on Windows (no Bazel)

If you don't want to compile MediaPipe from source, use the Python binding
to call C++ under the hood from a `.pyd` — or use the pre-built C API
package `mediapipe-cpp` once it becomes stable.

For now the most practical no-build option on Windows is the Python version:

```python
import mediapipe as mp
import cv2

BaseOptions = mp.tasks.BaseOptions
GestureRecognizer = mp.tasks.vision.GestureRecognizer
GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

model_path = r"C:\Users\media\mediapipe_python\mediapipe-env\Include\gesture_recognizer.task"

options = GestureRecognizerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.LIVE_STREAM,
    num_hands=2,
    result_callback=lambda result, image, ts: print(result)
)
with GestureRecognizer.create_from_options(options) as recognizer:
    cap = cv2.VideoCapture(0)
    ts = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.flip(frame, 1, frame)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        recognizer.recognize_async(mp_image, ts)
        ts += 33
        cv2.imshow("Gesture", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()
```
