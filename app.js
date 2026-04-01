const API_BASE_URL = 'https://binance-signal-engine-production.up.railway.app/api';

let activeSignals = [];
let closedSignals = [];
let monitoringInterval = null;

const pairs = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'MATICUSDT',
    'LINKUSDT', 'ATOMUSDT', 'UNIUSDT', 'LTCUSDT', 'ETCUSDT'
];

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
            const existingIndex = activeSignals.findIndex(s => s.pair === signal.pair);
            const currentPrice = currentPrices[signal.pair] || signal.entry_primary;
            
            if (existingIndex < 0) {
                activeSignals.push({
                    ...signal,
                    currentPrice: currentPrice,
                    id: Date.now() + Math.random(),
                    createdAt: new Date().toISOString()
                });
            } else {
                activeSignals[existingIndex].currentPrice = currentPrice;
                activeSignals[existingIndex].confidence = signal.confidence;
            }
        }
    } catch (error) {
        console.error('Error fetching top signals:', error);
    }
    
    saveSignals();
    renderActiveSignals();
    updateStatus('connected');
    updateLastUpdate();
}

async function scanAllPairs() {
    updateStatus('scanning');
    
    for (const pair of pairs) {
        try {
            const response = await fetch(`${API_BASE_URL}/signal/${pair}?timeframe=1h`);
            const data = await response.json();
            
            if ((data.signal === 'BUY' || data.signal === 'SELL') && data.confidence >= 60) {
                const existingIndex = activeSignals.findIndex(s => s.pair === data.pair);
                if (existingIndex < 0) {
                    const newSignal = {
                        ...data,
                        currentPrice: data.entry_primary || data.entry,
                        id: Date.now() + Math.random(),
                        createdAt: new Date().toISOString()
                    };
                    activeSignals.push(newSignal);
                }
            }
        } catch (error) {
            console.error('Error scanning:', pair, error);
        }
    }
    
    saveSignals();
    renderActiveSignals();
    updateStatus('connected');
    updateLastUpdate();
}

function removeSignal(id) {
    activeSignals = activeSignals.filter(s => s.id !== id);
    saveSignals();
    renderActiveSignals();
}

function closeSignal(id, remarks, closedPrice) {
    const signal = activeSignals.find(s => s.id === id);
    if (!signal) return;
    
    const closedSignal = {
        ...signal,
        closedAt: new Date().toISOString(),
        closedPrice: closedPrice,
        remarks: remarks
    };
    
    closedSignals.unshift(closedSignal);
    activeSignals = activeSignals.filter(s => s.id !== id);
    
    saveSignals();
    renderActiveSignals();
    renderClosedSignals();
}

async function monitorSignals() {
    for (const signal of activeSignals) {
        try {
            const response = await fetch(`${API_BASE_URL}/signal/${signal.pair}?timeframe=1h`);
            const data = await response.json();
            
            const currentPrice = data.entry_primary || data.entry;
            let closed = false;
            let remarks = '';
            let closedPrice = currentPrice;
            
            if (signal.signal === 'BUY') {
                if (currentPrice <= signal.sl) {
                    closed = true;
                    remarks = 'SL Hit';
                    closedPrice = signal.sl;
                } else if (currentPrice >= signal.tp3) {
                    closed = true;
                    remarks = 'TP3 Hit';
                    closedPrice = signal.tp3;
                } else if (currentPrice >= signal.tp2) {
                    closed = true;
                    remarks = 'TP2 Hit';
                    closedPrice = signal.tp2;
                } else if (currentPrice >= signal.tp1) {
                    closed = true;
                    remarks = 'TP1 Hit';
                    closedPrice = signal.tp1;
                }
            } else if (signal.signal === 'SELL') {
                if (currentPrice >= signal.sl) {
                    closed = true;
                    remarks = 'SL Hit';
                    closedPrice = signal.sl;
                } else if (currentPrice <= signal.tp3) {
                    closed = true;
                    remarks = 'TP3 Hit';
                    closedPrice = signal.tp3;
                } else if (currentPrice <= signal.tp2) {
                    closed = true;
                    remarks = 'TP2 Hit';
                    closedPrice = signal.tp2;
                } else if (currentPrice <= signal.tp1) {
                    closed = true;
                    remarks = 'TP1 Hit';
                    closedPrice = signal.tp1;
                }
            }
            
            if (closed) {
                closeSignal(signal.id, remarks, closedPrice);
            }
        } catch (error) {
            console.error('Error monitoring signal:', signal.pair, error);
        }
    }
}

function renderActiveSignals() {
    const tbody = document.getElementById('activeSignalsBody');
    tbody.innerHTML = '';
    
    if (activeSignals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-secondary)">No active signals. Scanning...</td></tr>';
        return;
    }
    
    activeSignals.forEach(signal => {
        const entry = signal.entry_primary || signal.entry;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${signal.pair}</td>
            <td class="${signal.signal === 'BUY' ? 'signal-buy' : 'signal-sell'}">${signal.signal}</td>
            <td>${formatPrice(signal.currentPrice || entry)}</td>
            <td>${formatPrice(signal.entry_limit || '--')}</td>
            <td>${formatPrice(signal.tp1)}</td>
            <td>${formatPrice(signal.tp2)}</td>
            <td>${formatPrice(signal.tp3)}</td>
            <td>${formatPrice(signal.sl)}</td>
            <td>${signal.risk_pct || '--'}%</td>
            <td>${signal.confidence}%</td>
            <td>
                <button class="close-btn" onclick="closeSignalManual(${signal.id})">Close</button>
                <button class="action-btn" onclick="removeSignal(${signal.id})">Remove</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function renderClosedSignals() {
    const tbody = document.getElementById('closedSignalsBody');
    tbody.innerHTML = '';
    
    if (closedSignals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-secondary)">No closed signals yet</td></tr>';
        return;
    }
    
    closedSignals.forEach(signal => {
        const entry = signal.entry_primary || signal.entry;
        const pl = signal.signal === 'BUY' 
            ? ((signal.closedPrice - entry) / entry * 100).toFixed(2)
            : ((entry - signal.closedPrice) / entry * 100).toFixed(2);
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${signal.pair}</td>
            <td class="${signal.signal === 'BUY' ? 'signal-buy' : 'signal-sell'}">${signal.signal}</td>
            <td>${formatPrice(signal.entry)}</td>
            <td>${formatPrice(signal.closedPrice)}</td>
            <td>${signal.remarks}</td>
            <td class="${parseFloat(pl) >= 0 ? 'profit' : 'loss'}">${pl}%</td>
        `;
        tbody.appendChild(row);
    });
}

async function closeSignalManual(id) {
    const signal = activeSignals.find(s => s.id === id);
    if (!signal) return;
    
    const remarks = prompt('Enter closing remarks (e.g., Manual Close, TP Hit, SL Hit):', 'Manual Close');
    if (remarks === null) return;
    
    const entry = signal.entry_primary || signal.entry;
    
    try {
        const response = await fetch(`${API_BASE_URL}/signal/${signal.pair}?timeframe=1h`);
        const data = await response.json();
        closeSignal(id, remarks, data.entry_primary || data.entry);
    } catch (error) {
        closeSignal(id, remarks, signal.currentPrice || entry);
    }
}

function saveSignals() {
    localStorage.setItem('activeSignals', JSON.stringify(activeSignals));
    localStorage.setItem('closedSignals', JSON.stringify(closedSignals));
}

function loadSignals() {
    try {
        const active = localStorage.getItem('activeSignals');
        const closed = localStorage.getItem('closedSignals');
        
        if (active) activeSignals = JSON.parse(active);
        if (closed) closedSignals = JSON.parse(closed);
    } catch (e) {
        console.error('Error loading signals:', e);
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
    loadSignals();
    renderActiveSignals();
    renderClosedSignals();
    
    fetchTopSignals();
    
    monitoringInterval = setInterval(() => {
        fetchTopSignals();
        monitorSignals();
    }, 30000);
}

document.addEventListener('DOMContentLoaded', init);
