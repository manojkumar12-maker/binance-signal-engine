export const adaptiveState = {
  targetSignalsPerMinute: 10,
  currentSignals: 0,
  lastReset: Date.now(),
  scoreThreshold: 40,
  confluenceThreshold: 1,
  confidenceThreshold: 50,
  mode: 'NORMAL',
  history: []
};

export function updateAdaptiveThresholds() {
  const now = Date.now();

  if (now - adaptiveState.lastReset > 60000) {
    const signals = adaptiveState.currentSignals;
    adaptiveState.history.push(signals);
    if (adaptiveState.history.length > 5) {
      adaptiveState.history.shift();
    }
    const avgSignals = adaptiveState.history.reduce((a, b) => a + b, 0) / adaptiveState.history.length;
    
    if (signals === 0 && avgSignals < 5) {
      adaptiveState.mode = 'RELAXED';
      adaptiveState.scoreThreshold = Math.max(30, adaptiveState.scoreThreshold - 5);
      adaptiveState.confluenceThreshold = Math.max(1, adaptiveState.confluenceThreshold - 1);
      adaptiveState.confidenceThreshold = Math.max(40, adaptiveState.confidenceThreshold - 5);
    } else if (signals > adaptiveState.targetSignalsPerMinute * 3) {
      adaptiveState.mode = 'STRICT';
      adaptiveState.scoreThreshold = Math.min(55, adaptiveState.scoreThreshold + 3);
      adaptiveState.confluenceThreshold = Math.min(3, adaptiveState.confluenceThreshold + 1);
      adaptiveState.confidenceThreshold = Math.min(65, adaptiveState.confidenceThreshold + 5);
    } else {
      adaptiveState.mode = 'NORMAL';
    }

    adaptiveState.scoreThreshold = Math.min(Math.max(adaptiveState.scoreThreshold, 30), 55);
    adaptiveState.confluenceThreshold = Math.min(Math.max(adaptiveState.confluenceThreshold, 1), 3);
    adaptiveState.confidenceThreshold = Math.min(Math.max(adaptiveState.confidenceThreshold, 40), 65);

    console.log(`🧠 Adaptive [${adaptiveState.mode}] → Score≥${adaptiveState.scoreThreshold} | Conf≥${adaptiveState.confidenceThreshold} | Confluence≥${adaptiveState.confluenceThreshold} | Signals: ${signals}`);

    adaptiveState.currentSignals = 0;
    adaptiveState.lastReset = now;
  }
}

export function getRejectionReason(data) {
  const reasons = [];

  if (data.score < adaptiveState.scoreThreshold) {
    reasons.push(`Score ${(data.score || 0).toFixed(1)} < ${adaptiveState.scoreThreshold}`);
  }

  if (data.confidence < adaptiveState.confidenceThreshold) {
    reasons.push(`Conf ${(data.confidence || 0).toFixed(1)} < ${adaptiveState.confidenceThreshold}`);
  }

  if (data.confluence < adaptiveState.confluenceThreshold) {
    reasons.push(`Confluence ${data.confluence} < ${adaptiveState.confluenceThreshold}`);
  }

  const ofRatio = data.orderflow?.ratio || data.ofRatio || 1;
  if (ofRatio < 1.0 && ofRatio > 0) {
    reasons.push(`OF ${ofRatio.toFixed(2)}`);
  }

  const oiChange = data.oiChange || data.openInterest?.change || 0;
  if (oiChange < 1 && oiChange >= 0) {
    reasons.push(`OI ${oiChange.toFixed(1)}%`);
  }

  const volSpike = data.volumeSpike || 0;
  if (volSpike < 1.0) {
    reasons.push(`Vol ${volSpike.toFixed(1)}x`);
  }

  return reasons;
}

export function passesAdaptiveFilter(data) {
  const ofRatio = data.orderflow?.ratio || data.ofRatio || 1;
  const oiChange = data.oiChange || data.openInterest?.change || 0;

  if (data.score < adaptiveState.scoreThreshold) return false;
  if (data.confidence < adaptiveState.confidenceThreshold) return false;
  if (data.confluence < adaptiveState.confluenceThreshold) return false;
  if (ofRatio < 1.0) return false;
  if (oiChange < 1 && adaptiveState.mode === 'STRICT') return false;
  if ((data.volumeSpike || 0) < 1.0) return false;

  return true;
}

export function passesBasicFilter(data) {
  const ofRatio = data.orderflow?.ratio || data.ofRatio || 1;
  const oiChange = data.oiChange || data.openInterest?.change || 0;
  
  if (data.score < 25) return false;
  if ((data.volumeSpike || 0) < 0.8) return false;
  
  return true;
}

export function incrementSignalCount() {
  adaptiveState.currentSignals++;
}

export function getAdaptiveStats() {
  return {
    scoreThreshold: adaptiveState.scoreThreshold,
    confluenceThreshold: adaptiveState.confluenceThreshold,
    confidenceThreshold: adaptiveState.confidenceThreshold,
    currentSignals: adaptiveState.currentSignals,
    mode: adaptiveState.mode
  };
}
