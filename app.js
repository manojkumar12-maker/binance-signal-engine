const API_BASE_URL = 'https://binance-signal-engine-production.up.railway.app/api';

let activeSignals = [];
let closedSignals = [];
let monitoringInterval = null;

async function fetchSignal() {
    const pair = document.getElementById('pairSelect').value;
    const timeframe = document.getElementById('timeframeSelect').value;
    const refreshBtn = document.getElementById('refreshBtn');
    
    refreshBtn.classList.add('loading');
    refreshBtn.disabled = true;
    
    try {
        updateStatus('connecting');
        
        const response = await fetch(`${API_BASE_URL}/signal/${pair}?timeframe=${timeframe}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        displaySignal(data);
        updateStatus('connected');
        updateLastUpdate();
        
    } catch (error) {
        console.error('Error fetching signal:', error);
        updateStatus('error');
    } finally {
        refreshBtn.classList.remove('loading');
        refreshBtn.disabled = false;
    }
}

function displaySignal(signal) {
    const signalCard = document.getElementById('signalCard');
    const signalPair = document.getElementById('signalPair');
    const signalType = document.getElementById('signalType');
    const signalEntry = document.getElementById('signalEntry');
    const slValue = document.getElementById('slValue');
    const tp1Value = document.getElementById('tp1Value');
    const tp2Value = document.getElementById('tp2Value');
    const tp3Value = document.getElementById('tp3Value');
    const confidenceValue = document.getElementById('confidenceValue');
    const confidenceCircle = document.getElementById('confidenceCircle');
    const trendValue = document.getElementById('trendValue');
    const liquidityValue = document.getElementById('liquidityValue');
    const volumeValue = document.getElementById('volumeValue');
    const reasonBox = document.getElementById('reasonBox');
    const reasonText = document.getElementById('reasonText');
    const addSignalBtn = document.getElementById('addSignalBtn');
    
    signalCard.classList.remove('buy', 'sell', 'no-trade');
    
    signalPair.textContent = signal.pair;
    signalType.textContent = signal.signal;
    signalType.classList.remove('buy', 'sell');
    addSignalBtn.style.display = 'none';
    
    if (signal.signal === 'BUY' || signal.signal === 'SELL') {
        signalCard.classList.add(signal.signal.toLowerCase());
        signalType.classList.add(signal.signal.toLowerCase());
        signalEntry.textContent = formatPrice(signal.entry);
        slValue.textContent = formatPrice(signal.sl);
        tp1Value.textContent = formatPrice(signal.tp1);
        tp2Value.textContent = formatPrice(signal.tp2);
        tp3Value.textContent = formatPrice(signal.tp3);
        addSignalBtn.style.display = 'block';
        
        addSignalBtn.onclick = () => addSignal(signal);
    } else {
        signalCard.classList.add('no-trade');
        signalEntry.textContent = signal.entry > 0 ? formatPrice(signal.entry) : '--';
        slValue.textContent = '--';
        tp1Value.textContent = '--';
        tp2Value.textContent = '--';
        tp3Value.textContent = '--';
    }
    
    const confidence = signal.confidence || 0;
    confidenceValue.textContent = confidence;
    
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (confidence / 100) * circumference;
    confidenceCircle.style.strokeDashoffset = offset;
    
    trendValue.textContent = signal.trend || '--';
    trendValue.classList.remove('uptrend', 'downtrend');
    if (signal.trend === 'UPTREND') trendValue.classList.add('uptrend');
    else if (signal.trend === 'DOWNTREND') trendValue.classList.add('downtrend');
    
    liquidityValue.textContent = signal.liquidity || '--';
    liquidityValue.classList.remove('sweep');
    if (signal.liquidity) liquidityValue.classList.add('sweep');
    
    volumeValue.textContent = signal.volume ? 'Confirmed' : 'Weak';
    volumeValue.classList.remove('confirmed');
    if (signal.volume) volumeValue.classList.add('confirmed');
    
    if (signal.reason) {
        reasonBox.style.display = 'block';
        reasonText.textContent = signal.reason;
    } else {
        reasonBox.style.display = 'none';
    }
}

function addSignal(signal) {
    const existingIndex = activeSignals.findIndex(s => s.pair === signal.pair);
    if (existingIndex >= 0) {
        alert('Signal for this pair already exists!');
        return;
    }
    
    const newSignal = {
        ...signal,
        id: Date.now(),
        createdAt: new Date().toISOString()
    };
    
    activeSignals.push(newSignal);
    saveSignals();
    renderActiveSignals();
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
            
            const currentPrice = data.entry;
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
    
    activeSignals.forEach(signal => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${signal.pair}</td>
            <td class="${signal.signal === 'BUY' ? 'signal-buy' : 'signal-sell'}">${signal.signal}</td>
            <td>${formatPrice(signal.entry)}</td>
            <td>${formatPrice(signal.tp1)}</td>
            <td>${formatPrice(signal.tp2)}</td>
            <td>${formatPrice(signal.tp3)}</td>
            <td>${formatPrice(signal.sl)}</td>
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
    
    closedSignals.forEach(signal => {
        const pl = signal.signal === 'BUY' 
            ? ((signal.closedPrice - signal.entry) / signal.entry * 100).toFixed(2)
            : ((signal.entry - signal.closedPrice) / signal.entry * 100).toFixed(2);
        
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
    
    try {
        const response = await fetch(`${API_BASE_URL}/signal/${signal.pair}?timeframe=1h`);
        const data = await response.json();
        closeSignal(id, remarks, data.entry);
    } catch (error) {
        closeSignal(id, remarks, signal.entry);
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
    
    const refreshBtn = document.getElementById('refreshBtn');
    refreshBtn.addEventListener('click', fetchSignal);
    
    const pairSelect = document.getElementById('pairSelect');
    const timeframeSelect = document.getElementById('timeframeSelect');
    
    pairSelect.addEventListener('change', fetchSignal);
    timeframeSelect.addEventListener('change', fetchSignal);
    
    fetchSignal();
    
    monitoringInterval = setInterval(monitorSignals, 30000);
}

document.addEventListener('DOMContentLoaded', init);
