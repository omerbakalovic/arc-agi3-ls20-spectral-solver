# Bazel BUILD file for hand_gesture_recognition
# Usage (from the MediaPipe repo root):
#   1. Copy this file and hand_gesture_recognition.cpp into the MediaPipe source tree, e.g.:
#        mediapipe/examples/desktop/hand_gesture/
#   2. bazel build -c opt //mediapipe/examples/desktop/hand_gesture:hand_gesture_recognition
#   3. bazel-bin/mediapipe/examples/desktop/hand_gesture/hand_gesture_recognition \
#        /path/to/gesture_recognizer.task [cam_index]

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "hand_gesture_recognition",
    srcs = ["hand_gesture_recognition.cpp"],
    deps = [
        "//mediapipe/framework/formats:image",
        "//mediapipe/framework/formats:image_frame",
        "//mediapipe/framework/formats:image_frame_opencv",
        "//mediapipe/tasks/cc/components/containers:gesture",
        "//mediapipe/tasks/cc/components/containers:landmark",
        "//mediapipe/tasks/cc/vision/core:running_mode",
        "//mediapipe/tasks/cc/vision/gesture_recognizer",
        "@com_google_absl//absl/status:statusor",
        "@opencv//:opencv",
    ],
)
