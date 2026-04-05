#pragma once

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <string>

namespace qp {

// Control IDs
enum GuiControlId {
    ID_BTN_LOAD_DATA    = 101,
    ID_BTN_RUN_BACKTEST = 102,
    ID_BTN_RUN_OPTIMIZE = 103,
    ID_BTN_RUN_TRUTH    = 104,
    ID_BTN_RUN_PAPER    = 105,
    ID_COMBO_STRATEGY   = 201,
    ID_EDIT_PARAM1      = 301,
    ID_EDIT_PARAM2      = 302,
    ID_EDIT_PARAM3      = 303,
    ID_EDIT_PARAM4      = 304,
    ID_EDIT_REPORT      = 401,
    ID_LABEL_STATUS     = 501,
    ID_LABEL_DATAFILE   = 502,
};

struct GuiPanels {
    HWND hLoadBtn       = nullptr;
    HWND hDataLabel     = nullptr;
    HWND hStrategyCombo = nullptr;
    HWND hParam1Label   = nullptr;
    HWND hParam1Edit    = nullptr;
    HWND hParam2Label   = nullptr;
    HWND hParam2Edit    = nullptr;
    HWND hParam3Label   = nullptr;
    HWND hParam3Edit    = nullptr;
    HWND hParam4Label   = nullptr;
    HWND hParam4Edit    = nullptr;
    HWND hRunBtBtn      = nullptr;
    HWND hRunOptBtn     = nullptr;
    HWND hRunTruthBtn   = nullptr;
    HWND hRunPaperBtn   = nullptr;
    HWND hReportEdit    = nullptr;
    HWND hStatusLabel   = nullptr;
};

void createPanels(HWND parent, GuiPanels& panels);
void layoutPanels(HWND parent, GuiPanels& panels, int width, int height);

} // namespace qp

#endif // _WIN32
