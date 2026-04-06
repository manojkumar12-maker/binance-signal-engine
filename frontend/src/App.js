import React, { useEffect, useState } from 'react';
import socket from './socket';

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
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));
    
    socket.on('update', (data) => {
      setSignals(data.signals || []);
      setTrades(data.trades || []);
      setLastUpdate(new Date());
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('update');
    };
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
          <div className={`status-indicator ${connected ? 'connected' : ''}`}>
            <span className="status-dot"></span>
            <span className="status-text">{connected ? 'Connected' : 'Disconnected'}</span>
          </div>
          {lastUpdate && (
            <span className="last-update">
              Last update: {lastUpdate.toLocaleTimeString()}
            </span>
          )}
        </div>
      </header>

      <main className="main-content">
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
      </main>
    </div>
  );
}

export default App;
