export const adaptiveState = {
  targetSignalsPerMinute: 5,
  currentSignals: 0,
  lastReset: Date.now(),
  scoreThreshold: 55,
  confluenceThreshold: 3,
  confidenceThreshold: 65
};

export function updateAdaptiveThresholds() {
  const now = Date.now();

  if (now - adaptiveState.lastReset > 60000) {
    const signals = adaptiveState.currentSignals;

    if (signals === 0) {
      adaptiveState.scoreThreshold = Math.max(45, adaptiveState.scoreThreshold - 2);
      adaptiveState.confluenceThreshold = Math.max(2, adaptiveState.confluenceThreshold - 1);
      adaptiveState.confidenceThreshold = Math.max(55, adaptiveState.confidenceThreshold - 3);
    }

    if (signals > adaptiveState.targetSignalsPerMinute) {
      adaptiveState.scoreThreshold = Math.min(70, adaptiveState.scoreThreshold + 2);
      adaptiveState.confluenceThreshold = Math.min(5, adaptiveState.confluenceThreshold + 1);
      adaptiveState.confidenceThreshold = Math.min(85, adaptiveState.confidenceThreshold + 3);
    }

    console.log(`🧠 Adaptive Update → Score≥${adaptiveState.scoreThreshold} | Conf≥${adaptiveState.confidenceThreshold} | Confluence≥${adaptiveState.confluenceThreshold} | Signals: ${signals}`);

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
  if (ofRatio < 1.2) {
    reasons.push(`Weak OF ${ofRatio.toFixed(2)}`);
  }

  const oiChange = data.oiChange || data.openInterest?.change || 0;
  if (oiChange < 1) {
    reasons.push(`Weak OI ${oiChange.toFixed(2)}%`);
  }

  const volSpike = data.volumeSpike || 0;
  if (volSpike < 2) {
    reasons.push(`Weak Vol ${volSpike.toFixed(1)}x`);
  }

  return reasons;
}

export function passesAdaptiveFilter(data) {
  const ofRatio = data.orderflow?.ratio || data.ofRatio || 1;
  const oiChange = data.oiChange || data.openInterest?.change || 0;

  if (data.score < adaptiveState.scoreThreshold) return false;
  if (data.confidence < adaptiveState.confidenceThreshold) return false;
  if (data.confluence < adaptiveState.confluenceThreshold) return false;
  if (ofRatio < 1.2) return false;
  if (oiChange < 2) return false;
  if ((data.volumeSpike || 0) < 2) return false;

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
    currentSignals: adaptiveState.currentSignals
  };
}
