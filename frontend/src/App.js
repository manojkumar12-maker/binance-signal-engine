import React, { useEffect, useState } from 'react';

const API_URL = process.env.REACT_APP_API_URL || 'https://binance-signal-engine-production.up.railway.app/api';

const formatPrice = (price) => {
  if (!price || price === 0) return '--';
  return price.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: price < 1 ? 6 : 2
  });
};

const renderState = (state) => {
  switch (state) {
    case 'PENDING': return { emoji: '🟡', text: 'PENDING', color: '#f0b90b' };
    case 'CONFIRMED': return { emoji: '🟢', text: 'CONFIRMED', color: '#00c087' };
    case 'EXECUTED': return { emoji: '🔵', text: 'EXECUTED', color: '#1e90ff' };
    case 'REJECTED': return { emoji: '🔴', text: 'REJECTED', color: '#f6465d' };
    case 'CLOSED': return { emoji: '⚫', text: 'CLOSED', color: '#6c7280' };
    default: return { emoji: '⚪', text: state || 'NEW', color: '#6c7280' };
  }
};

function App() {
  const [signals, setSignals] = useState([]);
  const [trades, setTrades] = useState([]);
  const [closedTrades, setClosedTrades] = useState([]);
  const [analytics, setAnalytics] = useState({ wins: 0, losses: 0, win_rate: 0, total_pnl: 0, total_trades: 0 });
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [signalsRes, tradesRes, closedRes, analyticsRes] = await Promise.all([
          fetch(`${API_URL}/signal-states`),
          fetch(`${API_URL}/trades?status=open`),
          fetch(`${API_URL}/trades?status=closed`),
          fetch(`${API_URL}/analytics`)
        ]);
        
        if (signalsRes.ok && tradesRes.ok && closedRes.ok && analyticsRes.ok) {
          const signalsData = await signalsRes.json();
          const tradesData = await tradesRes.json();
          const closedData = await closedRes.json();
          const analyticsData = await analyticsRes.json();
          
          setSignals(signalsData.signals || []);
          setTrades(tradesData.trades || []);
          setClosedTrades(closedData.trades || []);
          setAnalytics({
            wins: analyticsData.wins || 0,
            losses: analyticsData.losses || 0,
            win_rate: analyticsData.win_rate || 0,
            total_pnl: analyticsData.total_pnl || 0,
            total_trades: analyticsData.total_trades || 0
          });
          setLastUpdate(new Date());
        }
      } catch (error) {
        console.error('Fetch error:', error);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);

    return () => clearInterval(interval);
  }, []);

  const pendingSignals = signals.filter(s => s.signal_state === 'PENDING');
  const confirmedSignals = signals.filter(s => s.signal_state === 'CONFIRMED');
  const executedSignals = signals.filter(s => s.signal_state === 'EXECUTED');
  const rejectedSignals = signals.filter(s => s.signal_state === 'REJECTED');

  return (
    <div className="dashboard">
      <header className="header">
        <div className="logo">
          <span className="logo-icon">⚡</span>
          <h1>BINANCE SIGNAL ENGINE</h1>
        </div>
        <div className="header-controls">
          {lastUpdate && (
            <span className="last-update">
              Last update: {lastUpdate.toLocaleTimeString()}
            </span>
          )}
        </div>
      </header>

      <main className="main-content">
        <section className="stats-section">
          <div className="stats-card wins">
            <span className="stats-label">WINS</span>
            <span className="stats-value">{analytics.wins}</span>
          </div>
          <div className="stats-card losses">
            <span className="stats-label">LOSSES</span>
            <span className="stats-value">{analytics.losses}</span>
          </div>
          <div className="stats-card win-rate">
            <span className="stats-label">WIN RATE</span>
            <span className="stats-value">{analytics.win_rate}%</span>
          </div>
          <div className={`stats-card pnl ${analytics.total_pnl >= 0 ? 'profit' : 'loss'}`}>
            <span className="stats-label">TOTAL P&L</span>
            <span className="stats-value">{analytics.total_pnl >= 0 ? '+' : ''}{analytics.total_pnl}%</span>
          </div>
        </section>

        <section className="pipeline-section">
          <div className="pipeline-card">
            <span className="pipeline-label">PENDING</span>
            <span className="pipeline-value pending">{pendingSignals.length}</span>
          </div>
          <div className="pipeline-card">
            <span className="pipeline-label">CONFIRMED</span>
            <span className="pipeline-value confirmed">{confirmedSignals.length}</span>
          </div>
          <div className="pipeline-card">
            <span className="pipeline-label">EXECUTED</span>
            <span className="pipeline-value executed">{executedSignals.length}</span>
          </div>
          <div className="pipeline-card">
            <span className="pipeline-label">REJECTED</span>
            <span className="pipeline-value rejected">{rejectedSignals.length}</span>
          </div>
        </section>

        <section className="signals-section">
          <h2>🎯 Signals Pipeline</h2>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Signal</th>
                  <th>Entry</th>
                  <th>SL</th>
                  <th>TP1</th>
                  <th>Conf%</th>
                  <th>Risk%</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan="8" style={{textAlign: 'center', color: '#6c7280'}}>
                      Waiting for signals...
                    </td>
                  </tr>
                ) : (
                  signals.slice(0, 15).map((signal, idx) => {
                    const stateInfo = renderState(signal.signal_state);
                    return (
                      <tr key={idx} className={signal.signal_state?.toLowerCase()}>
                        <td className="pair">{signal.pair}</td>
                        <td className={`signal ${signal.signal?.toLowerCase()}`}>
                          {signal.signal}
                        </td>
                        <td>{formatPrice(signal.entry_primary)}</td>
                        <td>{formatPrice(signal.sl)}</td>
                        <td>{formatPrice(signal.tp1)}</td>
                        <td>{signal.confidence}%</td>
                        <td>{signal.risk_pct}%</td>
                        <td>
                          <span className="state-badge" style={{backgroundColor: stateInfo.color + '20', color: stateInfo.color}}>
                            {stateInfo.emoji} {stateInfo.text}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="trades-section">
          <h2>📊 Active Trades</h2>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Type</th>
                  <th>Entry</th>
                  <th>Current</th>
                  <th>SL</th>
                  <th>TP1</th>
                  <th>TP2</th>
                  <th>TP3</th>
                  <th>P/L</th>
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan="9" style={{textAlign: 'center', color: '#6c7280'}}>
                      No active trades
                    </td>
                  </tr>
                ) : (
                  trades.map((trade, idx) => {
                    const pnl = trade.pnl || 0;
                    const isProfit = pnl >= 0;
                    return (
                      <tr key={idx}>
                        <td className="pair">{trade.pair}</td>
                        <td className={`signal ${trade.type?.toLowerCase()}`}>
                          {trade.type}
                        </td>
                        <td>{formatPrice(trade.entry)}</td>
                        <td className="current">{formatPrice(trade.current_price)}</td>
                        <td>{formatPrice(trade.sl)}</td>
                        <td>{formatPrice(trade.tp1)}</td>
                        <td>{formatPrice(trade.tp2)}</td>
                        <td>{formatPrice(trade.tp3)}</td>
                        <td className={`pnl ${isProfit ? 'profit' : 'loss'}`}>
                          {pnl >= 0 ? '+' : ''}{pnl}%
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="trades-section">
          <h2>🔒 Closed Trades</h2>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Type</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>Status</th>
                  <th>P/L</th>
                </tr>
              </thead>
              <tbody>
                {closedTrades.length === 0 ? (
                  <tr>
                    <td colSpan="6" style={{textAlign: 'center', color: '#6c7280'}}>
                      No closed trades
                    </td>
                  </tr>
                ) : (
                  closedTrades.map((trade, idx) => {
                    const pnl = trade.pnl_pct || 0;
                    const isProfit = pnl >= 0;
                    return (
                      <tr key={idx}>
                        <td className="pair">{trade.pair}</td>
                        <td className={`signal ${trade.type?.toLowerCase()}`}>
                          {trade.type}
                        </td>
                        <td>{formatPrice(trade.entry)}</td>
                        <td>{formatPrice(trade.current_price)}</td>
                        <td>{trade.status}</td>
                        <td className={`pnl ${isProfit ? 'profit' : 'loss'}`}>
                          {pnl >= 0 ? '+' : ''}{pnl}%
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
