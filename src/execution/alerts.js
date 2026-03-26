const alerts = [];

export function sendAlert(message, type = 'INFO') {
  const alert = {
    message,
    type,
    timestamp: Date.now()
  };
  
  alerts.push(alert);
  
  if (alerts.length > 100) {
    alerts.shift();
  }
  
  console.log(`🔔 [${type}] ${message}`);
  
  return alert;
}

export function sendSignalAlert(signal) {
  const emoji = signal.type === 'SNIPER' ? '🔴' : signal.type === 'EARLY_PUMP' ? '🚀' : '🟣';
  
  return sendAlert(
    `${emoji} ${signal.type}: ${signal.symbol} | Entry: ${signal.entry} | Conf: ${signal.confidence}`,
    'SIGNAL'
  );
}

export function sendTradeAlert(position, event) {
  return sendAlert(
    `📊 ${event} ${position.symbol} | ${position.direction} | Entry: ${position.entry}`,
    'TRADE'
  );
}

export function sendErrorAlert(error) {
  return sendAlert(`❌ Error: ${error}`, 'ERROR');
}

export function sendWarningAlert(message) {
  return sendAlert(`⚠️ ${message}`, 'WARNING');
}

export function getAlerts(limit = 20) {
  return alerts.slice(-limit);
}

export function clearAlerts() {
  alerts.length = 0;
}
