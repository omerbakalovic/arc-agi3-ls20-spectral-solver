// MediaPipe Hand Gesture Recognition - C++ Implementation
// Build: see CMakeLists.txt or BUILD (Bazel)
// Model: gesture_recognizer.task (GestureRecognizer Tasks API)

#include <atomic>
#include <cmath>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "mediapipe/framework/formats/image.h"
#include "mediapipe/framework/formats/image_frame.h"
#include "mediapipe/framework/formats/image_frame_opencv.h"
#include "mediapipe/tasks/cc/components/containers/gesture.h"
#include "mediapipe/tasks/cc/components/containers/landmark.h"
#include "mediapipe/tasks/cc/vision/core/running_mode.h"
#include "mediapipe/tasks/cc/vision/gesture_recognizer/gesture_recognizer.h"
#include "mediapipe/tasks/cc/vision/gesture_recognizer/gesture_recognizer_result.h"

#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>

namespace mp_vision = mediapipe::tasks::vision;
namespace mp_containers = mediapipe::tasks::components::containers;

using GestureRecognizer = mp_vision::GestureRecognizer;
using GestureRecognizerOptions = mp_vision::GestureRecognizerOptions;
using GestureRecognizerResult = mp_vision::GestureRecognizerResult;
using RunningMode = mp_vision::RunningMode;

// ---- Hand landmark topology (21 joints) --------------------------------- //
// MediaPipe defines these connections between landmarks for drawing skeleton.
static const std::vector<std::pair<int, int>> kHandConnections = {
    {0, 1},  {1, 2},  {2, 3},  {3, 4},   // Thumb
    {0, 5},  {5, 6},  {6, 7},  {7, 8},   // Index
    {0, 9},  {9, 10}, {10, 11},{11, 12},  // Middle
    {0, 13}, {13, 14},{14, 15},{15, 16},  // Ring
    {0, 17}, {17, 18},{18, 19},{19, 20},  // Pinky
    {5, 9},  {9, 13}, {13, 17}            // Palm knuckles
};

// Colours per finger for drawing (BGR)
static const cv::Scalar kThumbColour  {0,   200, 255};
static const cv::Scalar kIndexColour  {0,   255, 128};
static const cv::Scalar kMiddleColour {0,   255, 255};
static const cv::Scalar kRingColour   {128, 0,   255};
static const cv::Scalar kPinkyColour  {255, 128, 0  };
static const cv::Scalar kPalmColour   {200, 200, 200};

static cv::Scalar ConnectionColour(int a, int b) {
    if (a <= 4 || b <= 4)  return kThumbColour;
    if (a <= 8 || b <= 8)  return kIndexColour;
    if (a <= 12 || b <= 12) return kMiddleColour;
    if (a <= 16 || b <= 16) return kRingColour;
    if (a <= 20 || b <= 20) return kPinkyColour;
    return kPalmColour;
}

// ---- Result state shared between callback and render loop --------------- //
struct SharedResult {
    std::mutex mtx;
    GestureRecognizerResult result;
    bool fresh = false;
    int64_t timestamp_ms = 0;
};

// ---- Drawing helpers ---------------------------------------------------- //
static void DrawLandmarks(cv::Mat& frame,
                          const std::vector<mp_containers::NormalizedLandmark>& landmarks) {
    const int W = frame.cols;
    const int H = frame.rows;

    for (auto& [a, b] : kHandConnections) {
        if (a >= (int)landmarks.size() || b >= (int)landmarks.size()) continue;
        cv::Point pa{(int)(landmarks[a].x * W), (int)(landmarks[a].y * H)};
        cv::Point pb{(int)(landmarks[b].x * W), (int)(landmarks[b].y * H)};
        cv::line(frame, pa, pb, ConnectionColour(a, b), 2, cv::LINE_AA);
    }

    for (size_t i = 0; i < landmarks.size(); ++i) {
        cv::Point p{(int)(landmarks[i].x * W), (int)(landmarks[i].y * H)};
        bool isTip = (i == 4 || i == 8 || i == 12 || i == 16 || i == 20);
        cv::circle(frame, p, isTip ? 6 : 4, cv::Scalar(255, 255, 255), -1, cv::LINE_AA);
        cv::circle(frame, p, isTip ? 6 : 4, cv::Scalar(0, 0, 0),       1,  cv::LINE_AA);
    }
}

static void DrawGestureLabel(cv::Mat& frame, const std::string& gesture,
                              float confidence, const std::string& handedness,
                              int hand_index) {
    int y_offset = 40 + hand_index * 70;

    // Semi-transparent background pill
    std::string label = handedness + ": " + gesture;
    std::string conf_str = cv::format("%.1f%%", confidence * 100.f);

    int baseLine = 0;
    cv::Size ts_label = cv::getTextSize(label,    cv::FONT_HERSHEY_SIMPLEX, 0.8, 2, &baseLine);
    cv::Size ts_conf  = cv::getTextSize(conf_str, cv::FONT_HERSHEY_SIMPLEX, 0.6, 1, &baseLine);

    int pad = 8;
    int box_w = std::max(ts_label.width, ts_conf.width) + 2 * pad;
    int box_h = ts_label.height + ts_conf.height + 3 * pad;

    cv::Rect bg_rect{10, y_offset - ts_label.height - pad,
                     box_w, box_h};
    cv::Mat roi = frame(bg_rect & cv::Rect(0, 0, frame.cols, frame.rows));
    cv::Mat colour(roi.size(), CV_8UC3, cv::Scalar(30, 30, 30));
    cv::addWeighted(colour, 0.6, roi, 0.4, 0, roi);

    // Text
    cv::putText(frame, label,
                {10 + pad, y_offset},
                cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(50, 255, 50), 2, cv::LINE_AA);
    cv::putText(frame, conf_str,
                {10 + pad, y_offset + ts_conf.height + pad},
                cv::FONT_HERSHEY_SIMPLEX, 0.6, cv::Scalar(200, 200, 200), 1, cv::LINE_AA);
}

static void DrawFPS(cv::Mat& frame, double fps) {
    std::string fps_str = cv::format("FPS: %.1f", fps);
    cv::putText(frame, fps_str,
                {frame.cols - 130, 30},
                cv::FONT_HERSHEY_SIMPLEX, 0.7, cv::Scalar(0, 255, 255), 2, cv::LINE_AA);
}

// ---- Main --------------------------------------------------------------- //
int main(int argc, char* argv[]) {
    // Path to gesture_recognizer.task — override via first argument
    std::string model_path = "gesture_recognizer.task";
    if (argc >= 2) model_path = argv[1];

    // Camera index — override via second argument
    int cam_index = 0;
    if (argc >= 3) cam_index = std::stoi(argv[2]);

    // ---- Build GestureRecognizer ---------------------------------------- //
    auto options = std::make_unique<GestureRecognizerOptions>();
    options->base_options.model_asset_path = model_path;
    options->running_mode = RunningMode::LIVE_STREAM;
    options->num_hands = 2;
    options->min_hand_detection_confidence = 0.5f;
    options->min_hand_presence_confidence  = 0.5f;
    options->min_tracking_confidence       = 0.5f;

    // Shared result for the async callback
    SharedResult shared;

    options->result_callback = [&shared](
        absl::StatusOr<GestureRecognizerResult> result,
        const mediapipe::Image& /*image*/,
        int64_t timestamp_ms) {
        if (!result.ok()) {
            std::cerr << "GestureRecognizer error: " << result.status() << "\n";
            return;
        }
        std::lock_guard<std::mutex> lock(shared.mtx);
        shared.result = std::move(*result);
        shared.timestamp_ms = timestamp_ms;
        shared.fresh = true;
    };

    auto recognizer_or = GestureRecognizer::Create(std::move(options));
    if (!recognizer_or.ok()) {
        std::cerr << "Failed to create GestureRecognizer: "
                  << recognizer_or.status() << "\n";
        return EXIT_FAILURE;
    }
    auto recognizer = std::move(*recognizer_or);

    // ---- Open webcam ---------------------------------------------------- //
    cv::VideoCapture cap(cam_index, cv::CAP_ANY);
    if (!cap.isOpened()) {
        std::cerr << "Cannot open camera " << cam_index << "\n";
        return EXIT_FAILURE;
    }
    cap.set(cv::CAP_PROP_FRAME_WIDTH,  1280);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, 720);
    cap.set(cv::CAP_PROP_FPS, 30);

    std::cout << "Hand Gesture Recognition running.\n"
              << "  Press Q or ESC to quit.\n"
              << "  Press SPACE to pause/resume.\n";

    cv::namedWindow("Hand Gesture Recognition", cv::WINDOW_NORMAL);

    cv::Mat frame, rgb_frame;
    bool paused = false;
    double fps = 0.0;
    auto t_prev = std::chrono::steady_clock::now();

    while (true) {
        // Handle keyboard
        int key = cv::waitKey(1) & 0xFF;
        if (key == 'q' || key == 27) break;  // Q or ESC
        if (key == ' ') paused = !paused;

        if (paused) {
            cv::putText(frame, "PAUSED",
                        {frame.cols / 2 - 70, frame.rows / 2},
                        cv::FONT_HERSHEY_SIMPLEX, 1.5, cv::Scalar(0, 0, 255), 3, cv::LINE_AA);
            cv::imshow("Hand Gesture Recognition", frame);
            continue;
        }

        if (!cap.read(frame) || frame.empty()) {
            std::cerr << "Empty frame from camera.\n";
            break;
        }

        // Flip horizontally for mirror view
        cv::flip(frame, frame, 1);

        // FPS
        auto t_now = std::chrono::steady_clock::now();
        double dt  = std::chrono::duration<double>(t_now - t_prev).count();
        t_prev = t_now;
        fps = fps * 0.9 + (1.0 / (dt + 1e-9)) * 0.1;  // EWMA

        // ---- Send frame to GestureRecognizer (async) -------------------- //
        cv::cvtColor(frame, rgb_frame, cv::COLOR_BGR2RGB);

        auto image_frame = std::make_shared<mediapipe::ImageFrame>(
            mediapipe::ImageFormat::SRGB,
            rgb_frame.cols, rgb_frame.rows,
            mediapipe::ImageFrame::kDefaultAlignmentBoundary);

        std::memcpy(image_frame->MutablePixelData(),
                    rgb_frame.data,
                    rgb_frame.total() * rgb_frame.elemSize());

        mediapipe::Image mp_image(std::move(image_frame));

        int64_t ts_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            t_now.time_since_epoch()).count();

        auto status = recognizer->DetectAsync(mp_image, ts_ms);
        if (!status.ok()) {
            std::cerr << "DetectAsync error: " << status << "\n";
        }

        // ---- Render last known result ----------------------------------- //
        {
            std::lock_guard<std::mutex> lock(shared.mtx);
            if (shared.fresh) {
                const auto& res = shared.result;

                for (size_t h = 0; h < res.hand_landmarks.size(); ++h) {
                    DrawLandmarks(frame, res.hand_landmarks[h].landmarks);

                    std::string gesture_name = "Unknown";
                    float confidence = 0.f;
                    if (h < res.gestures.size() && !res.gestures[h].empty()) {
                        gesture_name = res.gestures[h][0].category_name;
                        confidence   = res.gestures[h][0].score;
                    }

                    std::string handedness = "?";
                    if (h < res.handedness.size() && !res.handedness[h].empty()) {
                        handedness = res.handedness[h][0].category_name;
                    }

                    DrawGestureLabel(frame, gesture_name, confidence,
                                     handedness, (int)h);
                }
            }
        }

        DrawFPS(frame, fps);
        cv::imshow("Hand Gesture Recognition", frame);
    }

    cap.release();
    cv::destroyAllWindows();

    auto close_status = recognizer->Close();
    if (!close_status.ok()) {
        std::cerr << "Close error: " << close_status << "\n";
    }

    return EXIT_SUCCESS;
}
