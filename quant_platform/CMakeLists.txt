cmake_minimum_required(VERSION 3.16)
project(quant_platform VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Include directory for all targets
set(QP_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include)

# ============================================================
# Common library (logger, config)
# ============================================================
add_library(qp_common STATIC
    src/common/logger.cpp
    src/common/config_loader.cpp
)
target_include_directories(qp_common PUBLIC ${QP_INCLUDE_DIR})

# ============================================================
# IO library (CSV reader, report writer)
# ============================================================
add_library(qp_io STATIC
    src/io/csv_reader.cpp
    src/io/report_writer.cpp
)
target_include_directories(qp_io PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_io PUBLIC qp_common)

# ============================================================
# Core library (backtest engine, order simulator, position tracker)
# ============================================================
add_library(qp_core STATIC
    src/core/backtest_engine.cpp
    src/core/order_simulator.cpp
    src/core/position_tracker.cpp
)
target_include_directories(qp_core PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_core PUBLIC qp_common)

# ============================================================
# Strategy library
# ============================================================
add_library(qp_strategy STATIC
    src/strategy/momentum_strategy.cpp
    src/strategy/mean_reversion_strategy.cpp
    src/strategy/strategy_factory.cpp
)
target_include_directories(qp_strategy PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_strategy PUBLIC qp_common)

# ============================================================
# Metrics library
# ============================================================
add_library(qp_metrics STATIC
    src/metrics/metrics_engine.cpp
    src/metrics/metric_utils.cpp
)
target_include_directories(qp_metrics PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_metrics PUBLIC qp_common)

# ============================================================
# Monte Carlo library
# ============================================================
add_library(qp_montecarlo STATIC
    src/montecarlo/monte_carlo_engine.cpp
)
target_include_directories(qp_montecarlo PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_montecarlo PUBLIC qp_common qp_metrics)

# ============================================================
# Optimization library
# ============================================================
add_library(qp_optimization STATIC
    src/optimization/grid_optimizer.cpp
    src/optimization/random_optimizer.cpp
)
target_include_directories(qp_optimization PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_optimization PUBLIC qp_common qp_core qp_strategy qp_metrics)

# ============================================================
# Walk-Forward library
# ============================================================
add_library(qp_walkforward STATIC
    src/walkforward/walk_forward_engine.cpp
)
target_include_directories(qp_walkforward PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_walkforward PUBLIC qp_common qp_core qp_strategy qp_metrics qp_optimization)

# ============================================================
# Truth Engine library
# ============================================================
add_library(qp_truth STATIC
    src/truth/truth_engine.cpp
    src/truth/truth_checks.cpp
)
target_include_directories(qp_truth PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_truth PUBLIC qp_common qp_core qp_strategy qp_metrics qp_montecarlo)

# ============================================================
# Execution library
# ============================================================
add_library(qp_execution STATIC
    src/execution/paper_broker.cpp
    src/execution/order_manager.cpp
    src/execution/risk_manager.cpp
    src/execution/execution_engine.cpp
)
target_include_directories(qp_execution PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_execution PUBLIC qp_common qp_core qp_strategy)

# ============================================================
# GUI library (Win32 only, stubs on other platforms)
# ============================================================
add_library(qp_gui STATIC
    src/gui/main_window.cpp
    src/gui/gui_panels.cpp
    src/gui/gui_controller.cpp
    src/gui/gui_utils.cpp
)
target_include_directories(qp_gui PUBLIC ${QP_INCLUDE_DIR})
target_link_libraries(qp_gui PUBLIC
    qp_common qp_io qp_core qp_strategy qp_metrics
    qp_montecarlo qp_optimization qp_walkforward
    qp_truth qp_execution
)
if(WIN32)
    target_link_libraries(qp_gui PUBLIC comctl32 comdlg32)
endif()

# ============================================================
# Main executable
# ============================================================
if(WIN32)
    add_executable(quant_platform WIN32 app/main.cpp)
else()
    add_executable(quant_platform app/main.cpp)
endif()

target_include_directories(quant_platform PRIVATE ${QP_INCLUDE_DIR})
target_link_libraries(quant_platform PRIVATE
    qp_gui qp_execution qp_truth qp_walkforward
    qp_optimization qp_montecarlo qp_metrics
    qp_core qp_strategy qp_io qp_common
)

if(WIN32)
    target_link_libraries(quant_platform PRIVATE comctl32 comdlg32)
endif()

# ============================================================
# Install rules
# ============================================================
install(TARGETS quant_platform RUNTIME DESTINATION bin)
install(DIRECTORY config/ DESTINATION bin/config)
install(DIRECTORY data/ DESTINATION bin/data)
