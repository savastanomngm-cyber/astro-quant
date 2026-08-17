#!/usr/bin/env python3
"""
Historical backtest framework — avoid re-computing ephemeris.
Use pre-cached signals or simple rules to test against Yahoo data.
"""

import sys
sys.path.insert(0, '.')

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

def quick_backtest(ticker='NQ=F', days=365, signal_type='simple'):
    """
    Quick backtest: fetch Yahoo data + apply simple signal logic.
    Avoid ephemeris computation — focus on P&L framework.
    """
    
    end = datetime.now()
    start = end - timedelta(days=days)
    
    print(f"Fetching {ticker} history ({days} days)...")
    data = yf.download(ticker, start=start, end=end, progress=False)
    
    if data.empty:
        print(f"No data for {ticker}")
        return None
    
    # Simple signal: 20/50 EMA crossover (proxy for trend)
    data['ema20'] = data['Close'].ewm(span=20).mean()
    data['ema50'] = data['Close'].ewm(span=50).mean()
    data['signal'] = (data['ema20'] > data['ema50']).astype(int)  # 1=LONG, 0=SHORT/NONE
    data['signal_change'] = data['signal'].diff()
    
    # Daily returns
    data['ret_pct'] = data['Close'].pct_change() * 100
    
    # Backtest: enter on signal change, exit next day
    trades = []
    in_trade = False
    entry_price = None
    entry_date = None
    
    for idx in range(1, len(data)):
        date = data.index[idx]
        ret = data['ret_pct'].iloc[idx]
        
        # Entry signal
        if data['signal_change'].iloc[idx] != 0 and not in_trade:
            in_trade = True
            entry_price = data['Close'].iloc[idx]
            entry_date = date
        
        # Exit (next bar)
        elif in_trade:
            exit_price = data['Close'].iloc[idx]
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            trades.append({
                'entry_date': entry_date,
                'exit_date': date,
                'entry_price': float(entry_price),
                'exit_price': float(exit_price),
                'pnl_pct': float(pnl_pct),
                'win': 1 if float(pnl_pct) > 0 else 0,
            })
            in_trade = False
    
    df_trades = pd.DataFrame(trades)
    
    if len(df_trades) == 0:
        print("No trades generated")
        return data
    
    # Summary stats
    total_trades = len(df_trades)
    wins = df_trades['win'].sum()
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
    avg_pnl = df_trades['pnl_pct'].mean()
    pf = df_trades[df_trades['pnl_pct'] > 0]['pnl_pct'].sum() / abs(df_trades[df_trades['pnl_pct'] < 0]['pnl_pct'].sum()) if (df_trades['pnl_pct'] < 0).any() else 0
    
    print(f"\n{'='*60}")
    print(f"BACKTEST RESULTS: {ticker} ({days} days)")
    print(f"{'='*60}")
    print(f"Total trades: {total_trades}")
    print(f"Wins: {wins} ({win_rate:.1f}%)")
    print(f"Avg P&L: {avg_pnl:+.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Best trade: {df_trades['pnl_pct'].max():+.2f}%")
    print(f"Worst trade: {df_trades['pnl_pct'].min():+.2f}%")
    
    return df_trades, data

if __name__ == '__main__':
    trades, data = quick_backtest('NQ=F', days=365)
    trades.to_csv('/home/user/outputs/backtest_trades_1y.csv', index=False)
    print("\nSaved: /home/user/outputs/backtest_trades_1y.csv")
