#ifdef _WIN32

#include "gui/gui_panels.h"
#include "gui/gui_utils.h"

namespace qp {

void createPanels(HWND parent, GuiPanels& panels) {
    int y = 10;
    int leftCol = 10;
    int lblW = 120;
    int editW = 180;
    int btnW = 140;
    int h = 24;
    int gap = 30;

    // Data section
    panels.hLoadBtn = createButton(parent, "Load Data...", leftCol, y, btnW, h, ID_BTN_LOAD_DATA);
    panels.hDataLabel = createLabel(parent, "(no data loaded)", leftCol + btnW + 10, y + 4, 400, h, ID_LABEL_DATAFILE);
    y += gap + 10;

    // Strategy selection
    createLabel(parent, "Strategy:", leftCol, y + 4, lblW, h);
    panels.hStrategyCombo = createComboBox(parent, leftCol + lblW, y, editW, 200, ID_COMBO_STRATEGY);
    comboAddString(panels.hStrategyCombo, "momentum");
    comboAddString(panels.hStrategyCombo, "mean_reversion");
    SendMessageA(panels.hStrategyCombo, CB_SETCURSEL, 0, 0);
    y += gap;

    // Parameters
    panels.hParam1Label = createLabel(parent, "Param 1:", leftCol, y + 4, lblW, h);
    panels.hParam1Edit = createEdit(parent, "10", leftCol + lblW, y, editW, h, ID_EDIT_PARAM1);
    y += gap;

    panels.hParam2Label = createLabel(parent, "Param 2:", leftCol, y + 4, lblW, h);
    panels.hParam2Edit = createEdit(parent, "0.02", leftCol + lblW, y, editW, h, ID_EDIT_PARAM2);
    y += gap;

    panels.hParam3Label = createLabel(parent, "Param 3:", leftCol, y + 4, lblW, h);
    panels.hParam3Edit = createEdit(parent, "-0.01", leftCol + lblW, y, editW, h, ID_EDIT_PARAM3);
    y += gap;

    panels.hParam4Label = createLabel(parent, "Param 4:", leftCol, y + 4, lblW, h);
    panels.hParam4Edit = createEdit(parent, "0.10", leftCol + lblW, y, editW, h, ID_EDIT_PARAM4);
    y += gap + 10;

    // Action buttons
    panels.hRunBtBtn = createButton(parent, "Run Backtest", leftCol, y, btnW, h + 4, ID_BTN_RUN_BACKTEST);
    panels.hRunOptBtn = createButton(parent, "Run Optimizer", leftCol + btnW + 10, y, btnW, h + 4, ID_BTN_RUN_OPTIMIZE);
    panels.hRunTruthBtn = createButton(parent, "Run Truth Engine", leftCol + (btnW + 10) * 2, y, btnW + 20, h + 4, ID_BTN_RUN_TRUTH);
    panels.hRunPaperBtn = createButton(parent, "Paper Trade", leftCol + (btnW + 10) * 3 + 20, y, btnW, h + 4, ID_BTN_RUN_PAPER);
    y += gap + 10;

    // Report panel
    panels.hReportEdit = createEdit(parent, "", leftCol, y, 760, 300, ID_EDIT_REPORT, true);
    y += 310;

    // Status bar
    panels.hStatusLabel = createLabel(parent, "Ready", leftCol, y, 760, h, ID_LABEL_STATUS);
}

void layoutPanels(HWND /*parent*/, GuiPanels& panels, int width, int height) {
    // Resize the report edit to fill available space
    if (panels.hReportEdit) {
        RECT rc;
        GetWindowRect(panels.hReportEdit, &rc);
        POINT pt = {rc.left, rc.top};
        ScreenToClient(GetParent(panels.hReportEdit), &pt);

        int reportH = height - pt.y - 40;
        if (reportH < 100) reportH = 100;
        int reportW = width - 20;
        MoveWindow(panels.hReportEdit, pt.x, pt.y, reportW, reportH, TRUE);

        // Move status label below report
        if (panels.hStatusLabel) {
            MoveWindow(panels.hStatusLabel, 10, pt.y + reportH + 5, reportW, 20, TRUE);
        }
    }
}

} // namespace qp

#endif // _WIN32
