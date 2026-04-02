const API_BASE_URL = 'https://binance-signal-engine-production.up.railway.app/api';

let activeTrades = [];
let closedTrades = [];
let signalsData = [];
let monitoringInterval = null;
let analyticsData = null;
let sniperMode = false;

async function fetchConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/config`);
        const data = await response.json();
        sniperMode = data.sniper_mode || false;
        updateToggleUI();
    } catch (error) {
        console.error('Error fetching config:', error);
    }
}

async function toggleSniperMode() {
    sniperMode = !sniperMode;
    try {
        await fetch(`${API_BASE_URL}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sniper_mode: sniperMode })
        });
        updateToggleUI();
    } catch (error) {
        console.error('Error toggling sniper mode:', error);
    }
}

function updateToggleUI() {
    const toggle = document.getElementById('sniperToggle');
    const label = document.getElementById('modeLabel');
    if (toggle) {
        toggle.checked = sniperMode;
    }
    if (label) {
        label.textContent = sniperMode ? '🎯 SNIPER MODE' : 'NORMAL MODE';
        label.style.color = sniperMode ? '#ff6b6b' : 'var(--text-primary)';
    }
}

async function fetchAnalytics() {
    try {
        const response = await fetch(`${API_BASE_URL}/analytics`);
        analyticsData = await response.json();
        renderAnalytics();
    } catch (error) {
        console.error('Error fetching analytics:', error);
    }
}

async function fetchSignals() {
    try {
        const response = await fetch(`${API_BASE_URL}/top-signals?limit=10&min_confidence=60`);
        const data = await response.json();
        signalsData = data.signals || [];
        renderSignals();
    } catch (error) {
        console.error('Error fetching signals:', error);
    }
}

function renderSignals() {
    const tbody = document.getElementById('signalsBody');
    tbody.innerHTML = '';
    
    if (signalsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-secondary)">No signals. Market scanning...</td></tr>';
        return;
    }
    
    signalsData.forEach(signal => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${signal.pair}</td>
            <td class="${signal.signal === 'BUY' ? 'signal-buy' : 'signal-sell'}">${signal.signal}</td>
            <td>${formatPrice(signal.entry_primary)}</td>
            <td>${formatPrice(signal.sl)}</td>
            <td>${formatPrice(signal.tp1)}</td>
            <td>${formatPrice(signal.tp2)}</td>
            <td>${formatPrice(signal.tp3)}</td>
            <td>${signal.confidence}%</td>
            <td>${signal.risk_pct}%</td>
        `;
        tbody.appendChild(row);
    });
}

function renderAnalytics() {
    if (!analyticsData) return;
    
    const container = document.getElementById('analyticsPanel');
    if (container) {
        const { total_trades, wins, losses, win_rate, avg_win, avg_loss, total_pnl } = analyticsData;
        
        container.innerHTML = `
            <div class="analytics-grid">
                <div class="stat-card">
                    <span class="stat-label">Total Trades</span>
                    <span class="stat-value">${total_trades}</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Win Rate</span>
                    <span class="stat-value ${win_rate >= 50 ? 'profit' : 'loss'}">${win_rate}%</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Wins / Losses</span>
                    <span class="stat-value">${wins} / ${losses}</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Avg Win</span>
                    <span class="stat-value profit">+${avg_win}%</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Avg Loss</span>
                    <span class="stat-value loss">-${avg_loss}%</span>
                </div>
                <div class="stat-card wide">
                    <span class="stat-label">Total P&L</span>
                    <span class="stat-value ${total_pnl >= 0 ? 'profit' : 'loss'}">${total_pnl >= 0 ? '+' : ''}${total_pnl}%</span>
                </div>
            </div>
        `;
    }
}

async function openTrade(signal) {
    try {
        const response = await fetch(`${API_BASE_URL}/trade/open`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pair: signal.pair,
                type: signal.signal,
                entry: signal.entry_primary,
                entry_limit: signal.entry_limit,
                sl: signal.sl,
                tp1: signal.tp1,
                tp2: signal.tp2,
                tp3: signal.tp3,
                confidence: signal.confidence
            })
        });
        const data = await response.json();
        if (data.success) {
            activeTrades.push(data.trade);
            renderActiveTrades();
            fetchAnalytics();
        }
    } catch (error) {
        console.error('Error opening trade:', error);
    }
}

async function closeTrade(tradeId, remarks, closePrice) {
    try {
        const response = await fetch(`${API_BASE_URL}/trade/${tradeId}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ remarks, close_price: closePrice })
        });
        const data = await response.json();
        if (data.success) {
            const index = activeTrades.findIndex(t => t.id === tradeId);
            if (index >= 0) {
                const trade = activeTrades.splice(index, 1)[0];
                trade.status = data.trade.status;
                trade.pnl_pct = data.trade.pnl_pct;
                trade.closed_at = data.trade.closed_at;
                trade.remarks = remarks;
                closedTrades.unshift(trade);
            }
            renderActiveTrades();
            renderClosedTrades();
            fetchAnalytics();
        }
    } catch (error) {
        console.error('Error closing trade:', error);
    }
}

async function removeTrade(tradeId) {
    try {
        await fetch(`${API_BASE_URL}/trade/${tradeId}`, { method: 'DELETE' });
        activeTrades = activeTrades.filter(t => t.id !== tradeId);
        renderActiveTrades();
        fetchAnalytics();
    } catch (error) {
        console.error('Error removing trade:', error);
    }
}

async function syncWithBackend() {
    try {
        const response = await fetch(`${API_BASE_URL}/trades?status=open`);
        const data = await response.json();
        activeTrades = data.trades || [];
        
        const closedResponse = await fetch(`${API_BASE_URL}/trades?status=closed`);
        const closedData = await closedResponse.json();
        closedTrades = closedData.trades || [];
        
        renderActiveTrades();
        renderClosedTrades();
    } catch (error) {
        console.error('Error syncing with backend:', error);
    }
}

async function fetchTopSignals() {
    updateStatus('scanning');
    
    try {
        const response = await fetch(`${API_BASE_URL}/top-signals?limit=10&min_confidence=60&timeframe=1h`);
        const data = await response.json();
        
        const newSignals = data.signals || [];
        
        const currentPrices = {};
        for (const signal of newSignals) {
            try {
                const priceRes = await fetch(`${API_BASE_URL}/signal/${signal.pair}?timeframe=1h`);
                const priceData = await priceRes.json();
                currentPrices[signal.pair] = priceData.entry_primary || priceData.entry;
            } catch (e) {
                currentPrices[signal.pair] = signal.entry_primary;
            }
        }
        
        for (const signal of newSignals) {
            const existingIndex = activeTrades.findIndex(t => t.pair === signal.pair && t.status === 'OPEN');
            const currentPrice = currentPrices[signal.pair] || signal.entry_primary;
            
            if (existingIndex < 0) {
                signal.currentPrice = currentPrice;
                signal.entry = signal.entry_primary;
                signal.signal_type = signal.signal;
            } else {
                activeTrades[existingIndex].currentPrice = currentPrice;
                activeTrades[existingIndex].confidence = signal.confidence;
            }
        }
    } catch (error) {
        console.error('Error fetching top signals:', error);
    }
    
    renderActiveTrades();
    updateStatus('connected');
    updateLastUpdate();
}

async function monitorTrades() {
    for (const trade of activeTrades) {
        try {
            const response = await fetch(`${API_BASE_URL}/signal/${trade.pair}?timeframe=1h`);
            const data = await response.json();
            
            const currentPrice = data.entry_primary || data.entry;
            
            const result = await fetch(`${API_BASE_URL}/trade/${trade.id}?price=${currentPrice}`, {
                method: 'PUT'
            });
            const updateResult = await result.json();
            
            if (updateResult.trade && updateResult.trade.status !== 'OPEN') {
                const index = activeTrades.findIndex(t => t.id === trade.id);
                if (index >= 0) {
                    const closedTrade = activeTrades.splice(index, 1)[0];
                    closedTrade.status = updateResult.trade.status;
                    closedTrade.pnl_pct = updateResult.trade.pnl_pct;
                    closedTrade.closed_at = updateResult.trade.closed_at;
                    closedTrade.remarks = updateResult.trade.remarks;
                    closedTrades.unshift(closedTrade);
                }
                renderActiveTrades();
                renderClosedTrades();
                fetchAnalytics();
            } else {
                trade.currentPrice = currentPrice;
                trade.confidence = data.confidence;
            }
        } catch (error) {
            console.error('Error monitoring trade:', trade.pair, error);
        }
    }
    
    renderActiveTrades();
}

function renderActiveTrades() {
    const tbody = document.getElementById('activeSignalsBody');
    tbody.innerHTML = '';
    
    if (activeTrades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-secondary)">No active trades. Click a signal to open trade.</td></tr>';
        return;
    }
    
    activeTrades.forEach(trade => {
        const currentPrice = trade.currentPrice || trade.entry;
        const entry = trade.entry;
        const type = trade.type;
        
        let pnlPct = 0;
        let pnlClass = '';
        
        if (type === 'BUY') {
            pnlPct = ((currentPrice - entry) / entry) * 100;
        } else {
            pnlPct = ((entry - currentPrice) / entry) * 100;
        }
        
        pnlPct = pnlPct.toFixed(2);
        pnlClass = pnlPct >= 0 ? 'profit' : 'loss';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${trade.pair}</td>
            <td class="${type === 'BUY' ? 'signal-buy' : 'signal-sell'}">${type}</td>
            <td>${formatPrice(currentPrice)}</td>
            <td>${formatPrice(trade.tp1)}</td>
            <td>${formatPrice(trade.tp2)}</td>
            <td>${formatPrice(trade.tp3)}</td>
            <td>${formatPrice(trade.sl)}</td>
            <td class="${pnlClass}">${pnlPct}%</td>
        `;
        tbody.appendChild(row);
    });
}

function renderClosedTrades() {
    const tbody = document.getElementById('closedSignalsBody');
    tbody.innerHTML = '';
    
    if (closedTrades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-secondary)">No closed trades yet</td></tr>';
        return;
    }
    
    closedTrades.forEach(trade => {
        const pl = trade.pnl_pct || 0;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${trade.pair}</td>
            <td class="${trade.type === 'BUY' ? 'signal-buy' : 'signal-sell'}">${trade.type}</td>
            <td>${formatPrice(trade.entry)}</td>
            <td>${trade.status}</td>
            <td>${trade.remarks || '-'}</td>
            <td class="${pl >= 0 ? 'profit' : 'loss'}">${pl >= 0 ? '+' : ''}${pl}%</td>
        `;
        tbody.appendChild(row);
    });
}

async function openTradeFromSignal(pair) {
    const confirmed = confirm(`Open trade for ${pair}?`);
    if (!confirmed) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/signal/${pair}?timeframe=1h`);
        const data = await response.json();
        
        if (data.signal === 'BUY' || data.signal === 'SELL') {
            await openTrade({
                pair: data.pair,
                signal: data.signal,
                entry_primary: data.entry_primary,
                entry_limit: data.entry_limit,
                sl: data.sl,
                tp1: data.tp1,
                tp2: data.tp2,
                tp3: data.tp3,
                confidence: data.confidence
            });
        }
    } catch (error) {
        console.error('Error opening trade from signal:', error);
    }
}

async function closeTradeManual(tradeId) {
    const trade = activeTrades.find(t => t.id === tradeId);
    if (!trade) return;
    
    const remarks = prompt('Enter closing remarks (e.g., Manual Close, TP Hit, SL Hit):', 'Manual Close');
    if (remarks === null) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/signal/${trade.pair}?timeframe=1h`);
        const data = await response.json();
        const closePrice = data.entry_primary || data.entry;
        await closeTrade(tradeId, remarks, closePrice);
    } catch (error) {
        const closePrice = trade.currentPrice || trade.entry;
        await closeTrade(tradeId, remarks, closePrice);
    }
}

function formatPrice(price) {
    if (!price || price === 0) return '--';
    return price.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: price < 1 ? 6 : 2
    });
}

function updateStatus(status) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    
    statusDot.classList.remove('connected', 'error');
    
    if (status === 'connected') {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else if (status === 'scanning') {
        statusText.textContent = 'Scanning...';
    } else if (status === 'error') {
        statusDot.classList.add('error');
        statusText.textContent = 'Error';
    } else {
        statusText.textContent = 'Connecting...';
    }
}

function updateLastUpdate() {
    const lastUpdate = document.getElementById('lastUpdate');
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    lastUpdate.textContent = `Last update: ${timeString}`;
}

function init() {
    fetchConfig();
    
    const toggle = document.getElementById('sniperToggle');
    if (toggle) {
        toggle.addEventListener('change', toggleSniperMode);
    }
    
    syncWithBackend();
    fetchAnalytics();
    fetchSignals();
    
    setInterval(() => {
        fetchSignals();
        fetchConfig();
    }, 15000);
    
    setInterval(() => {
        monitorTrades();
    }, 15000);
}

document.addEventListener('DOMContentLoaded', init);