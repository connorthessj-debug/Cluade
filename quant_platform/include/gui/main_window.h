#pragma once

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace qp {

class MainWindow {
public:
    static int run(HINSTANCE hInstance, int nCmdShow);

private:
    static LRESULT CALLBACK windowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam);
};

} // namespace qp

#endif // _WIN32
