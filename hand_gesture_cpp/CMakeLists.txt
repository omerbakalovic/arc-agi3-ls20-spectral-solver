cmake_minimum_required(VERSION 3.18)
project(hand_gesture_recognition CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# DEPENDENCY PATHS — edit these to match your environment
# ---------------------------------------------------------------------------

# Root of the MediaPipe source tree (after "git clone https://github.com/google-ai-edge/mediapipe")
set(MEDIAPIPE_ROOT "" CACHE PATH "Path to MediaPipe source root")

# Root of the pre-built MediaPipe Tasks C++ library (if using pre-built binaries)
# Download from: https://github.com/google-ai-edge/mediapipe/releases
set(MEDIAPIPE_TASKS_LIB_DIR "" CACHE PATH "Path to pre-built MediaPipe Tasks lib dir")
set(MEDIAPIPE_TASKS_INCLUDE_DIR "" CACHE PATH "Path to MediaPipe Tasks include dir")

# OpenCV (required for camera capture and display)
# Install: pip install opencv-python, or vcpkg install opencv4
find_package(OpenCV REQUIRED COMPONENTS core highgui imgproc videoio)
message(STATUS "OpenCV version: ${OpenCV_VERSION}")

# ---------------------------------------------------------------------------
# Build from MediaPipe source (preferred — uses Bazel instead, see BUILD file)
# CMake is provided here for IDEs and Windows users who prefer it.
# ---------------------------------------------------------------------------

if(MEDIAPIPE_ROOT)
    # Add MediaPipe as an include directory
    include_directories(
        ${MEDIAPIPE_ROOT}
        ${MEDIAPIPE_ROOT}/third_party/flatbuffers/include
        ${MEDIAPIPE_ROOT}/third_party/abseil-cpp
    )

    # Find the compiled MediaPipe Tasks library
    find_library(MP_TASKS_LIB
        NAMES mediapipe_tasks_vision mediapipe_gesture_recognizer
        HINTS ${MEDIAPIPE_ROOT}/bazel-bin/mediapipe/tasks/cc/vision/gesture_recognizer
              ${MEDIAPIPE_TASKS_LIB_DIR}
        REQUIRED
    )

    add_executable(hand_gesture_recognition hand_gesture_recognition.cpp)

    target_include_directories(hand_gesture_recognition PRIVATE
        ${MEDIAPIPE_ROOT}
        ${MEDIAPIPE_TASKS_INCLUDE_DIR}
        ${OpenCV_INCLUDE_DIRS}
    )

    target_link_libraries(hand_gesture_recognition PRIVATE
        ${MP_TASKS_LIB}
        ${OpenCV_LIBS}
    )

    # Copy the model file next to the binary
    set(MODEL_SRC "C:/Users/media/mediapipe_python/mediapipe-env/Include/gesture_recognizer.task")
    if(EXISTS "${MODEL_SRC}")
        add_custom_command(TARGET hand_gesture_recognition POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${MODEL_SRC}"
                "$<TARGET_FILE_DIR:hand_gesture_recognition>/gesture_recognizer.task"
            COMMENT "Copying gesture_recognizer.task model"
        )
    endif()

else()
    message(WARNING
        "MEDIAPIPE_ROOT not set.\n"
        "Preferred build method is Bazel — see the BUILD file.\n"
        "For CMake, set -DMEDIAPIPE_ROOT=/path/to/mediapipe"
    )
endif()

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install(TARGETS hand_gesture_recognition DESTINATION bin)
install(FILES
    "C:/Users/media/mediapipe_python/mediapipe-env/Include/gesture_recognizer.task"
    DESTINATION bin
    OPTIONAL
)
