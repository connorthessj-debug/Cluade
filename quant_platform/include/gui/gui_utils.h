#pragma once

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <commctrl.h>
#include <string>

namespace qp {

HWND createLabel(HWND parent, const std::string& text, int x, int y, int w, int h, int id = 0);
HWND createButton(HWND parent, const std::string& text, int x, int y, int w, int h, int id);
HWND createEdit(HWND parent, const std::string& text, int x, int y, int w, int h, int id, bool multiline = false);
HWND createComboBox(HWND parent, int x, int y, int w, int h, int id);
void comboAddString(HWND combo, const std::string& text);
void setControlText(HWND ctrl, const std::string& text);
std::string getControlText(HWND ctrl);
void appendToReport(HWND editCtrl, const std::string& text);
void showError(HWND parent, const std::string& msg);
void showInfo(HWND parent, const std::string& msg);

} // namespace qp

#endif // _WIN32
