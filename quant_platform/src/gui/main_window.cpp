#ifdef _WIN32

#include "gui/main_window.h"
#include "gui/gui_panels.h"
#include "gui/gui_controller.h"
#include <commctrl.h>

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "comdlg32.lib")

namespace qp {

static GuiPanels     s_panels;
static GuiController s_controller;

LRESULT CALLBACK MainWindow::windowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_CREATE:
            createPanels(hwnd, s_panels);
            s_controller.init(&s_panels);
            return 0;

        case WM_SIZE:
            layoutPanels(hwnd, s_panels, LOWORD(lParam), HIWORD(lParam));
            return 0;

        case WM_COMMAND:
            switch (LOWORD(wParam)) {
                case ID_BTN_LOAD_DATA:
                    s_controller.onLoadData(hwnd);
                    break;
                case ID_BTN_RUN_BACKTEST:
                    s_controller.onRunBacktest();
                    break;
                case ID_BTN_RUN_OPTIMIZE:
                    s_controller.onRunOptimizer();
                    break;
                case ID_BTN_RUN_TRUTH:
                    s_controller.onRunTruthEngine();
                    break;
                case ID_BTN_RUN_PAPER:
                    s_controller.onRunPaperTrading();
                    break;
            }
            return 0;

        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
    }

    return DefWindowProcA(hwnd, msg, wParam, lParam);
}

int MainWindow::run(HINSTANCE hInstance, int nCmdShow) {
    // Initialize common controls
    INITCOMMONCONTROLSEX icc = {};
    icc.dwSize = sizeof(icc);
    icc.dwICC = ICC_STANDARD_CLASSES | ICC_WIN95_CLASSES;
    InitCommonControlsEx(&icc);

    // Register window class
    WNDCLASSEXA wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = windowProc;
    wc.hInstance = hInstance;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    wc.lpszClassName = "QuantPlatformWindow";
    wc.hIcon = LoadIcon(nullptr, IDI_APPLICATION);

    if (!RegisterClassExA(&wc)) {
        MessageBoxA(nullptr, "Failed to register window class", "Error", MB_OK | MB_ICONERROR);
        return 1;
    }

    // Create window
    HWND hwnd = CreateWindowExA(
        0, "QuantPlatformWindow", "Quant Platform v1.0",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT, CW_USEDEFAULT, 800, 700,
        nullptr, nullptr, hInstance, nullptr);

    if (!hwnd) {
        MessageBoxA(nullptr, "Failed to create window", "Error", MB_OK | MB_ICONERROR);
        return 1;
    }

    ShowWindow(hwnd, nCmdShow);
    UpdateWindow(hwnd);

    // Message loop
    MSG msg = {};
    while (GetMessage(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    return static_cast<int>(msg.wParam);
}

} // namespace qp

#endif // _WIN32
