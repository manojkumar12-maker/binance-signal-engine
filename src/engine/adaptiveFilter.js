export const adaptiveState = {
  scoreThreshold: 45,
  confluenceThreshold: 2,
  confidenceThreshold: 55,
  mode: 'STABLE',
  history: []
};

export function updateAdaptiveThresholds() {
  // STABLE MODE: thresholds are fixed, no aggressive switching
  // only log stats, don't adjust thresholds
  const signals = adaptiveState.history.length;
  if (signals > 0) {
    const lastSignals = adaptiveState.history[adaptiveState.history.length - 1];
    console.log(`🧠 Adaptive [STABLE] → Score≥${adaptiveState.scoreThreshold} | Conf≥${adaptiveState.confidenceThreshold} | Signals/min: ${lastSignals}`);
  }
  
  if (adaptiveState.history.length > 5) {
    adaptiveState.history.shift();
  }
}

export function getRejectionReason(data) {
  const reasons = [];
  const score = data.score || 0;
  const confidence = data.confidence || 0;
  const confluence = data.confluence || 0;
  const ofRatio = data.orderflow?.ratio || data.ofRatio || 1;
  const oiChange = data.oiChange || data.openInterest?.change || 0;
  const volSpike = data.volumeSpike || 0;

  if (score < adaptiveState.scoreThreshold) {
    reasons.push(`Score ${score.toFixed(1)} < ${adaptiveState.scoreThreshold}`);
  }
  if (confidence < adaptiveState.confidenceThreshold) {
    reasons.push(`Conf ${confidence.toFixed(1)} < ${adaptiveState.confidenceThreshold}`);
  }
  if (confluence < adaptiveState.confluenceThreshold) {
    reasons.push(`Confluence ${confluence} < ${adaptiveState.confluenceThreshold}`);
  }
  if (ofRatio < 1.0 && ofRatio > 0) {
    reasons.push(`OF ${ofRatio.toFixed(2)}`);
  }
  if (oiChange < 0.5 && oiChange >= 0) {
    reasons.push(`OI ${oiChange.toFixed(1)}%`);
  }
  if (volSpike < 1.5) {
    reasons.push(`Vol ${volSpike.toFixed(1)}x`);
  }

  return reasons;
}

export function passesAdaptiveFilter(data) {
  return true;
}

export function passesBasicFilter(data) {
  return true;
}

export function incrementSignalCount() {
  adaptiveState.history.push(adaptiveState.history.length + 1);
  if (adaptiveState.history.length > 100) {
    adaptiveState.history = [];
  }
}

export function getAdaptiveStats() {
  return {
    scoreThreshold: adaptiveState.scoreThreshold,
    confluenceThreshold: adaptiveState.confluenceThreshold,
    confidenceThreshold: adaptiveState.confidenceThreshold,
    currentSignals: adaptiveState.history.length,
    mode: adaptiveState.mode
  };
}
