//+------------------------------------------------------------------+
//|         profitable_connors_RSI_FTMO_compliant-V1.0.mq5           |
//|         Connors RSI2 Mean Reversion - FTMO Compliant             |
//|         Optimized params: maLen=250, rsiLen=2, rsiOS=19,         |
//|         rsiOB=89, exitMaLen=3, atrSlMult=0.5, rrRatio=1.8       |
//+------------------------------------------------------------------+
#property copyright "Connors RSI2 FTMO V1.0"
#property link      ""
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+

// --- Trend Filter ---
input int      InpMaLen         = 250;           // MA Length
input ENUM_MA_METHOD InpMaType  = MODE_SMA;      // MA Type (SMA/EMA)

// --- RSI ---
input int      InpRsiLen        = 2;             // RSI Length
input double   InpRsiOversold   = 19.0;          // RSI Oversold Threshold
input double   InpRsiOverbought = 89.0;          // RSI Overbought Threshold

// --- Exit ---
input int      InpExitMaLen     = 3;             // Exit MA Length

// --- Risk Management ---
input int      InpAtrPeriod     = 14;            // ATR Period
input double   InpAtrSlMult     = 0.5;           // ATR Stop Loss Multiplier
input double   InpRrRatio       = 1.8;           // Risk:Reward Ratio
input bool     InpUseTrailing   = true;          // Use Trailing Stop
input double   InpTrailAfterR   = 1.0;           // Trail After R-Multiple

// --- Session Filter ---
input bool     InpSessEnabled   = true;          // Enable Session Filter
input int      InpSessStartHour = 9;             // Session Start Hour
input int      InpSessStartMin  = 30;            // Session Start Minute
input int      InpSessEndHour   = 16;            // Session End Hour
input int      InpSessEndMin    = 0;             // Session End Minute
input int      InpMaxDailyTrades = 5;            // Max Daily Trades

// --- FTMO Rules ---
input double   InpAccountBalance    = 10000.0;   // Account Balance
input double   InpMaxDailyLossPct   = 5.0;       // Max Daily Loss %
input double   InpMaxTotalDDPct     = 10.0;      // Max Total Drawdown %

// --- Position Sizing ---
input double   InpLotSize       = 0.01;          // Fixed Lot Size
input int      InpMagicNumber   = 20240101;      // Magic Number

//+------------------------------------------------------------------+
//| Global Variables                                                  |
//+------------------------------------------------------------------+

// Indicator handles
int g_hMA;
int g_hRSI;
int g_hExitMA;
int g_hATR;

// Trade management
CTrade         g_trade;
CPositionInfo  g_position;

// State tracking
int      g_dailyTradeCount;
double   g_dailyPnL;
double   g_totalPnL;
double   g_peakEquity;
bool     g_ftmoBreached;
bool     g_dailyLossBreached;
datetime g_currentDate;

// Trailing stop state
bool     g_trailActivated;
double   g_trailStop;
double   g_entryPrice;
double   g_slDistance;
int      g_posDirection;  // 1 = long, -1 = short, 0 = flat

// Previous bar exit MA for crossover detection
double   g_prevExitMA;

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
   // Create indicator handles
   g_hMA = iMA(_Symbol, PERIOD_CURRENT, InpMaLen, 0, InpMaType, PRICE_CLOSE);
   if(g_hMA == INVALID_HANDLE)
   {
      Print("Error creating MA indicator: ", GetLastError());
      return INIT_FAILED;
   }

   g_hRSI = iRSI(_Symbol, PERIOD_CURRENT, InpRsiLen, PRICE_CLOSE);
   if(g_hRSI == INVALID_HANDLE)
   {
      Print("Error creating RSI indicator: ", GetLastError());
      return INIT_FAILED;
   }

   g_hExitMA = iMA(_Symbol, PERIOD_CURRENT, InpExitMaLen, 0, MODE_SMA, PRICE_CLOSE);
   if(g_hExitMA == INVALID_HANDLE)
   {
      Print("Error creating Exit MA indicator: ", GetLastError());
      return INIT_FAILED;
   }

   g_hATR = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   if(g_hATR == INVALID_HANDLE)
   {
      Print("Error creating ATR indicator: ", GetLastError());
      return INIT_FAILED;
   }

   // Initialize trade object
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(10);
   g_trade.SetTypeFilling(ORDER_FILLING_FOK);

   // Initialize state
   g_dailyTradeCount  = 0;
   g_dailyPnL         = 0.0;
   g_totalPnL         = 0.0;
   g_peakEquity       = InpAccountBalance;
   g_ftmoBreached     = false;
   g_dailyLossBreached = false;
   g_currentDate      = 0;
   g_trailActivated   = false;
   g_trailStop        = 0.0;
   g_entryPrice       = 0.0;
   g_slDistance        = 0.0;
   g_posDirection     = 0;
   g_prevExitMA       = 0.0;

   Print("Connors RSI2 FTMO V1.0 initialized");
   Print("Params: MA=", InpMaLen, " RSI=", InpRsiLen,
         " OS=", InpRsiOversold, " OB=", InpRsiOverbought,
         " ExitMA=", InpExitMaLen, " ATR_SL=", InpAtrSlMult,
         " RR=", InpRrRatio);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_hMA != INVALID_HANDLE)     IndicatorRelease(g_hMA);
   if(g_hRSI != INVALID_HANDLE)    IndicatorRelease(g_hRSI);
   if(g_hExitMA != INVALID_HANDLE) IndicatorRelease(g_hExitMA);
   if(g_hATR != INVALID_HANDLE)    IndicatorRelease(g_hATR);

   Print("Connors RSI2 FTMO V1.0 deinitialized. Total PnL: ", g_totalPnL);
}

//+------------------------------------------------------------------+
//| Check if current time is within trading session                   |
//+------------------------------------------------------------------+
bool IsInSession()
{
   if(!InpSessEnabled) return true;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int t = dt.hour * 60 + dt.min;
   int start = InpSessStartHour * 60 + InpSessStartMin;
   int end_t = InpSessEndHour * 60 + InpSessEndMin;

   return (t >= start && t < end_t);
}

//+------------------------------------------------------------------+
//| Get indicator value from buffer                                   |
//+------------------------------------------------------------------+
double GetIndicatorValue(int handle, int shift, int buffer = 0)
{
   double val[1];
   if(CopyBuffer(handle, buffer, shift, 1, val) != 1)
      return 0.0;
   return val[0];
}

//+------------------------------------------------------------------+
//| Check if we have an open position with our magic number           |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_position.SelectByIndex(i))
      {
         if(g_position.Symbol() == _Symbol && g_position.Magic() == InpMagicNumber)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Get current position type (1=long, -1=short, 0=none)             |
//+------------------------------------------------------------------+
int GetPositionDirection()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_position.SelectByIndex(i))
      {
         if(g_position.Symbol() == _Symbol && g_position.Magic() == InpMagicNumber)
         {
            if(g_position.PositionType() == POSITION_TYPE_BUY) return 1;
            if(g_position.PositionType() == POSITION_TYPE_SELL) return -1;
         }
      }
   }
   return 0;
}

//+------------------------------------------------------------------+
//| Close all positions for this EA                                   |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_position.SelectByIndex(i))
      {
         if(g_position.Symbol() == _Symbol && g_position.Magic() == InpMagicNumber)
         {
            g_trade.PositionClose(g_position.Ticket());
         }
      }
   }
   g_posDirection = 0;
   g_trailActivated = false;
   g_trailStop = 0.0;
}

//+------------------------------------------------------------------+
//| Update FTMO tracking after a trade closes                         |
//+------------------------------------------------------------------+
void UpdateFTMO(double pnl)
{
   g_dailyPnL += pnl;
   g_totalPnL += pnl;

   // Check daily loss limit
   double maxDailyLoss = InpAccountBalance * InpMaxDailyLossPct / 100.0;
   if(g_dailyPnL <= -maxDailyLoss)
   {
      g_dailyLossBreached = true;
      Print("FTMO WARNING: Daily loss limit breached! Daily PnL: ", g_dailyPnL);
   }

   // Check total drawdown
   double currentEquity = InpAccountBalance + g_totalPnL;
   if(currentEquity > g_peakEquity)
      g_peakEquity = currentEquity;

   double drawdown = g_peakEquity - currentEquity;
   double maxDD = InpAccountBalance * InpMaxTotalDDPct / 100.0;
   if(drawdown >= maxDD)
   {
      g_ftmoBreached = true;
      Print("FTMO CRITICAL: Max total drawdown breached! Drawdown: ", drawdown);
      CloseAllPositions();
   }
}

//+------------------------------------------------------------------+
//| Daily reset check                                                 |
//+------------------------------------------------------------------+
void CheckDailyReset()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   datetime today = StringToTime(IntegerToString(dt.year) + "." +
                                  IntegerToString(dt.mon) + "." +
                                  IntegerToString(dt.day));

   if(today != g_currentDate)
   {
      g_dailyTradeCount = 0;
      g_dailyPnL = 0.0;
      g_dailyLossBreached = false;
      g_currentDate = today;
   }
}

//+------------------------------------------------------------------+
//| Check and manage trailing stop                                    |
//+------------------------------------------------------------------+
void ManageTrailingStop()
{
   if(!InpUseTrailing || g_posDirection == 0 || g_slDistance <= 0)
      return;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if(g_posDirection == 1)  // Long
   {
      double rAchieved = (bid - g_entryPrice) / g_slDistance;
      if(rAchieved >= InpTrailAfterR)
         g_trailActivated = true;

      if(g_trailActivated)
      {
         double newTrail = bid - g_slDistance;
         if(g_trailStop == 0.0 || newTrail > g_trailStop)
            g_trailStop = newTrail;

         if(bid <= g_trailStop)
         {
            double closePnl = (bid - g_entryPrice) * InpLotSize * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
            CloseAllPositions();
            UpdateFTMO(closePnl);
            Print("Trailing stop hit (long). PnL: ", closePnl);
            return;
         }
      }
   }
   else if(g_posDirection == -1)  // Short
   {
      double rAchieved = (g_entryPrice - ask) / g_slDistance;
      if(rAchieved >= InpTrailAfterR)
         g_trailActivated = true;

      if(g_trailActivated)
      {
         double newTrail = ask + g_slDistance;
         if(g_trailStop == 0.0 || newTrail < g_trailStop)
            g_trailStop = newTrail;

         if(ask >= g_trailStop)
         {
            double closePnl = (g_entryPrice - ask) * InpLotSize * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
            CloseAllPositions();
            UpdateFTMO(closePnl);
            Print("Trailing stop hit (short). PnL: ", closePnl);
            return;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check SMA crossover exit                                          |
//+------------------------------------------------------------------+
void CheckSMACrossoverExit()
{
   if(g_posDirection == 0) return;

   double exitMA_curr = GetIndicatorValue(g_hExitMA, 0);
   double close_curr  = iClose(_Symbol, PERIOD_CURRENT, 0);
   double close_prev  = iClose(_Symbol, PERIOD_CURRENT, 1);

   if(exitMA_curr == 0.0 || g_prevExitMA == 0.0) return;

   if(g_posDirection == 1)  // Long: close crosses above exit MA
   {
      if(close_curr > exitMA_curr && close_prev <= g_prevExitMA)
      {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double closePnl = (bid - g_entryPrice) * InpLotSize * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
         CloseAllPositions();
         UpdateFTMO(closePnl);
         Print("SMA crossover exit (long). PnL: ", closePnl);
      }
   }
   else if(g_posDirection == -1)  // Short: close crosses below exit MA
   {
      if(close_curr < exitMA_curr && close_prev >= g_prevExitMA)
      {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double closePnl = (g_entryPrice - ask) * InpLotSize * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
         CloseAllPositions();
         UpdateFTMO(closePnl);
         Print("SMA crossover exit (short). PnL: ", closePnl);
      }
   }
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // Ensure we only act on new bars
   static datetime lastBarTime = 0;
   datetime currentBarTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(currentBarTime == lastBarTime) return;
   lastBarTime = currentBarTime;

   // Daily reset
   CheckDailyReset();

   // FTMO total drawdown check - stop everything
   if(g_ftmoBreached)
   {
      Comment("FTMO BREACHED - Trading stopped. Total PnL: ", g_totalPnL);
      return;
   }

   // Get indicator values (shift 1 = completed bar)
   double maVal      = GetIndicatorValue(g_hMA, 1);
   double rsiVal     = GetIndicatorValue(g_hRSI, 1);
   double exitMA_val = GetIndicatorValue(g_hExitMA, 1);
   double atrVal     = GetIndicatorValue(g_hATR, 1);
   double close_1    = iClose(_Symbol, PERIOD_CURRENT, 1);
   double high_1     = iHigh(_Symbol, PERIOD_CURRENT, 1);
   double low_1      = iLow(_Symbol, PERIOD_CURRENT, 1);

   // Validate indicator data
   if(maVal == 0.0 || atrVal == 0.0) return;

   // --- Manage existing position ---
   int currentPos = GetPositionDirection();

   // Sync internal state with broker
   if(currentPos == 0 && g_posDirection != 0)
   {
      // Position was closed by SL/TP - calculate PnL
      // (SL/TP exits are handled by the broker; we track PnL here)
      g_posDirection = 0;
      g_trailActivated = false;
      g_trailStop = 0.0;
   }
   g_posDirection = currentPos;

   if(g_posDirection != 0)
   {
      // Check SMA crossover exit
      CheckSMACrossoverExit();

      // Manage trailing stop
      ManageTrailingStop();
   }

   // Update previous exit MA for next bar's crossover detection
   g_prevExitMA = exitMA_val;

   // --- Entry logic ---
   bool canTrade = IsInSession()
                   && g_dailyTradeCount < InpMaxDailyTrades
                   && !g_dailyLossBreached
                   && !g_ftmoBreached
                   && g_posDirection == 0;

   if(!canTrade) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   // Long entry: close > MA AND RSI < oversold
   if(close_1 > maVal && rsiVal < InpRsiOversold)
   {
      double slDist = MathMax(atrVal * InpAtrSlMult, point);
      double sl = NormalizeDouble(ask - slDist, _Digits);
      double tp = NormalizeDouble(ask + slDist * InpRrRatio, _Digits);

      if(g_trade.Buy(InpLotSize, _Symbol, ask, sl, tp, "RSI2 Long"))
      {
         g_entryPrice = ask;
         g_slDistance = slDist;
         g_posDirection = 1;
         g_dailyTradeCount++;
         g_trailActivated = false;
         g_trailStop = 0.0;
         Print("Long entry at ", ask, " SL=", sl, " TP=", tp, " RSI=", rsiVal);
      }
      else
      {
         Print("Buy order failed: ", GetLastError());
      }
      return;
   }

   // Short entry: close < MA AND RSI > overbought
   if(close_1 < maVal && rsiVal > InpRsiOverbought)
   {
      double slDist = MathMax(atrVal * InpAtrSlMult, point);
      double sl = NormalizeDouble(bid + slDist, _Digits);
      double tp = NormalizeDouble(bid - slDist * InpRrRatio, _Digits);

      if(g_trade.Sell(InpLotSize, _Symbol, bid, sl, tp, "RSI2 Short"))
      {
         g_entryPrice = bid;
         g_slDistance = slDist;
         g_posDirection = -1;
         g_dailyTradeCount++;
         g_trailActivated = false;
         g_trailStop = 0.0;
         Print("Short entry at ", bid, " SL=", sl, " TP=", tp, " RSI=", rsiVal);
      }
      else
      {
         Print("Sell order failed: ", GetLastError());
      }
      return;
   }
}

//+------------------------------------------------------------------+
//| Trade event handler - track closed trade PnL for FTMO             |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   // Detect when a position is closed (by SL/TP)
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      ulong dealTicket = trans.deal;
      if(dealTicket == 0) return;

      // Check if this deal belongs to our EA
      if(HistoryDealSelect(dealTicket))
      {
         long dealMagic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);
         if(dealMagic != InpMagicNumber) return;

         long dealEntry = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
         if(dealEntry == DEAL_ENTRY_OUT || dealEntry == DEAL_ENTRY_OUT_BY)
         {
            double dealProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
            double dealComm   = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
            double dealSwap   = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
            double netPnl = dealProfit + dealComm + dealSwap;

            UpdateFTMO(netPnl);
            Print("Trade closed via SL/TP. Net PnL: ", netPnl,
                  " Daily PnL: ", g_dailyPnL, " Total PnL: ", g_totalPnL);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Chart comment with status                                         |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam,
                  const double &dparam, const string &sparam)
{
   // Update status display periodically
   string status = "=== Connors RSI2 FTMO V1.0 ===\n";
   status += "Daily Trades: " + IntegerToString(g_dailyTradeCount)
             + "/" + IntegerToString(InpMaxDailyTrades) + "\n";
   status += "Daily PnL: $" + DoubleToString(g_dailyPnL, 2) + "\n";
   status += "Total PnL: $" + DoubleToString(g_totalPnL, 2) + "\n";
   status += "Peak Equity: $" + DoubleToString(g_peakEquity, 2) + "\n";

   double currentEquity = InpAccountBalance + g_totalPnL;
   double dd = g_peakEquity - currentEquity;
   status += "Current DD: $" + DoubleToString(dd, 2)
             + " (" + DoubleToString(dd / InpAccountBalance * 100, 1) + "%)\n";

   if(g_ftmoBreached)
      status += "*** FTMO BREACHED - TRADING STOPPED ***\n";
   else if(g_dailyLossBreached)
      status += "*** DAILY LOSS LIMIT - NO MORE TRADES TODAY ***\n";

   Comment(status);
}
//+------------------------------------------------------------------+
