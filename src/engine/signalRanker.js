export function rankSignals(signals) {
  return signals
    .map(signal => {
      const rankScore = calculateRankScore(signal);
      return {
        ...signal,
        rankScore,
        rank: 0
      };
    })
    .sort((a, b) => b.rankScore - a.rankScore)
    .map((signal, index) => ({
      ...signal,
      rank: index + 1
    }));
}

function calculateRankScore(signal) {
  let score = 0;
  
  score += (signal.confidence || 0) * 0.5;
  
  score += Math.min((signal.volumeSpike || 0) * 12, 30);
  
  score += Math.max((signal.momentum || 0) * 40, -10);
  
  if (signal.hasConfluence) score += 15;
  
  if (signal.isTrendingMarket) score += 10;
  
  if (signal.entryQuality === 'EXCELLENT') score += 20;
  else if (signal.entryQuality === 'GOOD') score += 12;
  else if (signal.entryQuality === 'LATE') score += 5;
  else score -= 15;
  
  if (signal.tier === 'SNIPER') score += 25;
  else if (signal.tier === 'CONFIRMED') score += 15;
  else if (signal.tier === 'EARLY') score += 5;
  
  if (signal.imbalance && signal.imbalance > 1.5) score += 10;
  
  if (!signal.isFakePump) score += 10;
  else score -= 25;
  
  return Math.round(score * 100) / 100;
}

export function getTopSignals(signals, limit = 5) {
  return rankSignals(signals).slice(0, limit);
}

export function getSignalSummary(signals) {
  const ranked = rankSignals(signals);
  const top = ranked.slice(0, 5);
  
  return {
    totalSignals: signals.length,
    topSignals: top.map(s => ({
      rank: s.rank,
      symbol: s.symbol,
      tier: s.tier,
      confidence: s.confidence,
      score: s.score,
      entryQuality: s.entryQuality,
      rankScore: s.rankScore
    })),
    averageConfidence: signals.length > 0 
      ? Math.round(signals.reduce((sum, s) => sum + (s.confidence || 0), 0) / signals.length)
      : 0,
    qualityDistribution: {
      sniper: signals.filter(s => s.tier === 'SNIPER').length,
      confirmed: signals.filter(s => s.tier === 'CONFIRMED').length,
      early: signals.filter(s => s.tier === 'EARLY').length
    }
  };
}

export function filterHighQualitySignals(signals, minConfidence = 50) {
  return rankSignals(signals).filter(s => 
    s.confidence >= minConfidence && 
    !s.isFakePump &&
    (s.entryQuality === 'EXCELLENT' || s.entryQuality === 'GOOD')
  );
}
