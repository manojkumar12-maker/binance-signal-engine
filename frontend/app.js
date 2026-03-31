const API_BASE_URL = 'https://your-backend.up.railway.app/api';

let currentSignal = null;
let autoRefreshInterval = null;

async function fetchSignal() {
    const pair = document.getElementById('pairSelect').value;
    const timeframe = document.getElementById('timeframeSelect').value;
    const refreshBtn = document.getElementById('refreshBtn');
    
    refreshBtn.classList.add('loading');
    refreshBtn.disabled = true;
    
    try {
        updateStatus('connecting');
        
        const response = await fetch(`${API_BASE_URL}/signal/${pair}?timeframe=${timeframe}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        currentSignal = data;
        
        displaySignal(data);
        updateStatus('connected');
        updateLastUpdate();
        
    } catch (error) {
        console.error('Error fetching signal:', error);
        updateStatus('error');
        
        if (currentSignal) {
            displaySignal(currentSignal);
        }
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
    
    signalCard.classList.remove('buy', 'sell', 'no-trade');
    
    signalPair.textContent = signal.pair;
    signalType.textContent = signal.signal;
    signalType.classList.remove('buy', 'sell');
    
    if (signal.signal === 'BUY') {
        signalCard.classList.add('buy');
        signalType.classList.add('buy');
        signalEntry.textContent = formatPrice(signal.entry);
        slValue.textContent = formatPrice(signal.sl);
        tp1Value.textContent = formatPrice(signal.tp1);
        tp2Value.textContent = formatPrice(signal.tp2);
        tp3Value.textContent = formatPrice(signal.tp3);
    } else if (signal.signal === 'SELL') {
        signalCard.classList.add('sell');
        signalType.classList.add('sell');
        signalEntry.textContent = formatPrice(signal.entry);
        slValue.textContent = formatPrice(signal.sl);
        tp1Value.textContent = formatPrice(signal.tp1);
        tp2Value.textContent = formatPrice(signal.tp2);
        tp3Value.textContent = formatPrice(signal.tp3);
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
    if (signal.trend === 'UPTREND') {
        trendValue.classList.add('uptrend');
    } else if (signal.trend === 'DOWNTREND') {
        trendValue.classList.add('downtrend');
    }
    
    liquidityValue.textContent = signal.liquidity || '--';
    liquidityValue.classList.remove('sweep');
    if (signal.liquidity) {
        liquidityValue.classList.add('sweep');
    }
    
    volumeValue.textContent = signal.volume ? 'Confirmed' : 'Weak';
    volumeValue.classList.remove('confirmed');
    if (signal.volume) {
        volumeValue.classList.add('confirmed');
    }
    
    if (signal.reason) {
        reasonBox.style.display = 'block';
        reasonText.textContent = signal.reason;
    } else {
        reasonBox.style.display = 'none';
    }
}

function formatPrice(price) {
    if (!price || price === 0) return '--';
    return price.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
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

function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    
    autoRefreshInterval = setInterval(() => {
        fetchSignal();
    }, 5 * 60 * 1000);
}

function init() {
    const refreshBtn = document.getElementById('refreshBtn');
    refreshBtn.addEventListener('click', fetchSignal);
    
    const pairSelect = document.getElementById('pairSelect');
    const timeframeSelect = document.getElementById('timeframeSelect');
    
    pairSelect.addEventListener('change', fetchSignal);
    timeframeSelect.addEventListener('change', fetchSignal);
    
    fetchSignal();
    
    startAutoRefresh();
}

document.addEventListener('DOMContentLoaded', init);
