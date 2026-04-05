#ifdef _WIN32

#include "gui/gui_utils.h"

namespace qp {

HWND createLabel(HWND parent, const std::string& text, int x, int y, int w, int h, int id) {
    return CreateWindowExA(0, "STATIC", text.c_str(),
        WS_CHILD | WS_VISIBLE | SS_LEFT,
        x, y, w, h, parent, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),
        GetModuleHandle(nullptr), nullptr);
}

HWND createButton(HWND parent, const std::string& text, int x, int y, int w, int h, int id) {
    return CreateWindowExA(0, "BUTTON", text.c_str(),
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        x, y, w, h, parent, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),
        GetModuleHandle(nullptr), nullptr);
}

HWND createEdit(HWND parent, const std::string& text, int x, int y, int w, int h, int id, bool multiline) {
    DWORD style = WS_CHILD | WS_VISIBLE | WS_BORDER;
    if (multiline) {
        style |= ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL | ES_READONLY;
    }
    HWND hw = CreateWindowExA(0, "EDIT", text.c_str(),
        style, x, y, w, h, parent,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),
        GetModuleHandle(nullptr), nullptr);
    return hw;
}

HWND createComboBox(HWND parent, int x, int y, int w, int h, int id) {
    return CreateWindowExA(0, "COMBOBOX", "",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        x, y, w, h, parent, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),
        GetModuleHandle(nullptr), nullptr);
}

void comboAddString(HWND combo, const std::string& text) {
    SendMessageA(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(text.c_str()));
}

void setControlText(HWND ctrl, const std::string& text) {
    SetWindowTextA(ctrl, text.c_str());
}

std::string getControlText(HWND ctrl) {
    int len = GetWindowTextLengthA(ctrl);
    if (len <= 0) return "";
    std::string buf(static_cast<size_t>(len + 1), '\0');
    GetWindowTextA(ctrl, &buf[0], len + 1);
    buf.resize(static_cast<size_t>(len));
    return buf;
}

void appendToReport(HWND editCtrl, const std::string& text) {
    int len = GetWindowTextLengthA(editCtrl);
    SendMessageA(editCtrl, EM_SETSEL, static_cast<WPARAM>(len), static_cast<LPARAM>(len));
    SendMessageA(editCtrl, EM_REPLACESEL, FALSE, reinterpret_cast<LPARAM>(text.c_str()));
    SendMessageA(editCtrl, EM_REPLACESEL, FALSE, reinterpret_cast<LPARAM>("\r\n"));
    SendMessageA(editCtrl, EM_SCROLLCARET, 0, 0);
}

void showError(HWND parent, const std::string& msg) {
    MessageBoxA(parent, msg.c_str(), "Error", MB_OK | MB_ICONERROR);
}

void showInfo(HWND parent, const std::string& msg) {
    MessageBoxA(parent, msg.c_str(), "Info", MB_OK | MB_ICONINFORMATION);
}

} // namespace qp

#endif // _WIN32
