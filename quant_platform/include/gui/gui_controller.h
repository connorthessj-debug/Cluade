#pragma once

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <commdlg.h>
#include "gui/gui_panels.h"
#include "common/data_models.h"
#include <vector>
#include <string>

namespace qp {

class GuiController {
public:
    void init(GuiPanels* panels);
    void onLoadData(HWND parent);
    void onRunBacktest();
    void onRunOptimizer();
    void onRunTruthEngine();
    void onRunPaperTrading();

private:
    void setStatus(const std::string& text);
    void report(const std::string& text);
    StrategyParams getParamsFromUI() const;
    std::string getSelectedStrategy() const;

    GuiPanels*      m_panels = nullptr;
    AppConfig       m_config;
    std::vector<Bar> m_bars;
    BacktestSnapshot m_lastSnapshot;
    MetricsSummary   m_lastMetrics;
    bool             m_dataLoaded = false;
};

} // namespace qp

#endif // _WIN32
