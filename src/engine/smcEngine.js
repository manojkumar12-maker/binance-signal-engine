/**
 * SMC Engine — D1 + H4 + M15 Multi-Timeframe Analysis
 *
 * Flow:
 *   D1  → Trend bias (bull / bear / neutral)
 *   H4  → Zone detection (demand / supply / OB / FVG)
 *   M15 → Entry trigger (BOS / CHoCH / strong candle)
 *
 * All data is fetched from Binance Futures Klines REST API
 * and cached with per-timeframe TTLs to avoid rate limiting.
 */

import axios from 'axios';

const BASE_URL = 'https://fapi.binance.com';

// Cache TTLs
const TTL = { '1d': 4 * 60 * 60_000, '4h': 30 * 60_000, '15m': 2 * 60_000 };

// ── Kline cache ──────────────────────────────────────────────
const klineCache = new Map();

async function fetchKlines(symbol, interval, limit = 100) {
  const key = `${symbol}:${interval}`;
  const cached = klineCache.get(key);
  const ttl = TTL[interval] || 60_000;

  if (cached && Date.now() - cached.ts < ttl) return cached.data;

  try {
    const { data } = await axios.get(`${BASE_URL}/fapi/v1/klines`, {
      params: { symbol, interval, limit },
      timeout: 8000
    });

    // [openTime, o, h, l, c, vol, closeTime, quoteVol, trades, tbBaseVol, tbQuoteVol, ignore]
    const candles = data.map(k => ({
      time:  k[0],
      open:  parseFloat(k[1]),
      high:  parseFloat(k[2]),
      low:   parseFloat(k[3]),
      close: parseFloat(k[4]),
      vol:   parseFloat(k[5]),
      qvol:  parseFloat(k[7])
    }));

    klineCache.set(key, { ts: Date.now(), data: candles });
    return candles;
  } catch {
    return cached?.data || [];
  }
}

// ── Indicator helpers ────────────────────────────────────────

function ema(candles, period) {
  if (candles.length < period) return null;
  const k = 2 / (period + 1);
  let val = candles.slice(0, period).reduce((s, c) => s + c.close, 0) / period;
  for (let i = period; i < candles.length; i++) {
    val = candles[i].close * k + val * (1 - k);
  }
  return val;
}

function atr(candles, period = 14) {
  if (candles.length < period + 1) return null;
  const trs = candles.slice(-period - 1).map((c, i, arr) => {
    if (i === 0) return c.high - c.low;
    const prev = arr[i - 1].close;
    return Math.max(c.high - c.low, Math.abs(c.high - prev), Math.abs(c.low - prev));
  }).slice(1);
  return trs.reduce((s, v) => s + v, 0) / period;
}

function rsi(candles, period = 14) {
  if (candles.length < period + 1) return 50;
  let gains = 0, losses = 0;
  const recent = candles.slice(-period - 1);
  for (let i = 1; i < recent.length; i++) {
    const d = recent[i].close - recent[i - 1].close;
    if (d > 0) gains += d; else losses -= d;
  }
  const ag = gains / period, al = losses / period;
  return al === 0 ? 100 : 100 - 100 / (1 + ag / al);
}

function macd(candles) {
  const fast = ema(candles, 12);
  const slow = ema(candles, 26);
  if (!fast || !slow) return { line: 0, signal: 0, hist: 0, bull: false };
  const line = fast - slow;
  // approximate signal line
  const recentLines = candles.slice(-9).map((_, i, arr) => {
    const slice = candles.slice(0, candles.length - 8 + i);
    const f = ema(slice, 12), s = ema(slice, 26);
    return f && s ? f - s : line;
  });
  const sigVal = recentLines.reduce((a, b) => a + b, 0) / recentLines.length;
  return { line, signal: sigVal, hist: line - sigVal, bull: line > sigVal };
}

// ── D1 Analysis ──────────────────────────────────────────────

function analyzeD1(candles) {
  if (candles.length < 50) return { bias: 'NEUTRAL', reason: 'Not enough D1 data' };

  const e200 = ema(candles, 200) || ema(candles, candles.length);
  const e50  = ema(candles, 50)  || ema(candles, candles.length);
  const close = candles[candles.length - 1].close;

  // Swing structure — last 20 D1 candles
  const recent = candles.slice(-20);
  let hh = 0, hl = 0, lh = 0, ll = 0;
  for (let i = 2; i < recent.length; i++) {
    const h = recent[i].high, ph = recent[i - 1].high;
    const l = recent[i].low,  pl = recent[i - 1].low;
    if (h > ph) hh++; else lh++;
    if (l > pl) hl++; else ll++;
  }

  const aboveEMA200 = e200 ? close > e200 : null;
  const aboveEMA50  = e50  ? close > e50  : null;

  const bullScore =
    (aboveEMA200 ? 2 : 0) +
    (aboveEMA50  ? 1 : 0) +
    (hh > lh ? 2 : 0) +
    (hl > ll ? 1 : 0);

  const bias =
    bullScore >= 4 ? 'BULL' :
    bullScore <= 2 ? 'BEAR' :
    'NEUTRAL';

  const keyLevels = findKeyLevels(candles, 30);

  return {
    bias,
    ema200:      e200,
    ema50:       e50,
    closePrice:  close,
    aboveEMA200,
    aboveEMA50,
    swingScore:  { hh, hl, lh, ll },
    bullScore,
    keyLevels,
    reason: `D1 bullScore=${bullScore} abv200=${aboveEMA200} HH=${hh} HL=${hl}`
  };
}

// ── H4 Analysis ──────────────────────────────────────────────

function findDemandSupplyZones(candles, lookback = 20) {
  const zones = [];
  const slice = candles.slice(-lookback - 1);

  for (let i = 1; i < slice.length - 1; i++) {
    const c = slice[i];
    const body = Math.abs(c.close - c.open);
    const range = c.high - c.low;
    const bodyRatio = range > 0 ? body / range : 0;

    // Demand zone: bearish candle followed by strong bullish move
    if (c.close < c.open && bodyRatio > 0.5) {
      const next = slice[i + 1];
      if (next && next.close > c.open * 1.003) {
        zones.push({ type: 'DEMAND', high: c.open, low: c.low, idx: i, time: c.time });
      }
    }
    // Supply zone: bullish candle followed by strong bearish move
    if (c.close > c.open && bodyRatio > 0.5) {
      const next = slice[i + 1];
      if (next && next.close < c.open * 0.997) {
        zones.push({ type: 'SUPPLY', high: c.high, low: c.close, idx: i, time: c.time });
      }
    }
  }
  return zones.slice(-10);
}

function findFVG(candles, lookback = 30) {
  const fvgs = [];
  const slice = candles.slice(-lookback);
  for (let i = 1; i < slice.length - 1; i++) {
    const prev = slice[i - 1], curr = slice[i], next = slice[i + 1];
    // Bullish FVG: gap between prev high and next low
    if (next.low > prev.high) {
      fvgs.push({ type: 'BULL_FVG', high: next.low, low: prev.high, time: curr.time });
    }
    // Bearish FVG: gap between prev low and next high
    if (next.high < prev.low) {
      fvgs.push({ type: 'BEAR_FVG', high: prev.low, low: next.high, time: curr.time });
    }
  }
  return fvgs.slice(-8);
}

function findOrderBlocks(candles, lookback = 30) {
  const obs = [];
  const slice = candles.slice(-lookback);
  for (let i = 1; i < slice.length - 2; i++) {
    const c = slice[i], next1 = slice[i + 1], next2 = slice[i + 2];
    const body = Math.abs(c.close - c.open);
    const range = c.high - c.low;
    if (range === 0) continue;

    // Bullish OB: last bearish candle before impulsive up move
    if (c.close < c.open && next1.close > c.high && next2.close > c.high) {
      obs.push({ type: 'BULL_OB', high: c.open, low: c.low, time: c.time });
    }
    // Bearish OB: last bullish candle before impulsive down move
    if (c.close > c.open && next1.close < c.low && next2.close < c.low) {
      obs.push({ type: 'BEAR_OB', high: c.high, low: c.close, time: c.time });
    }
  }
  return obs.slice(-8);
}

function findKeyLevels(candles, lookback = 30) {
  const slice = candles.slice(-lookback);
  const highs = slice.map(c => c.high).sort((a, b) => b - a);
  const lows  = slice.map(c => c.low).sort((a, b) => a - b);

  const resistance = highs.slice(0, 3);
  const support    = lows.slice(0, 3);

  // Equal highs/lows (liquidity)
  const eqTolerance = slice[slice.length - 1].close * 0.002;
  const eqHighs = highs.filter(h => Math.abs(h - highs[0]) < eqTolerance);
  const eqLows  = lows.filter(l => Math.abs(l - lows[0])   < eqTolerance);

  return { resistance, support, eqHighs, eqLows };
}

function analyzeH4(candles, d1Bias) {
  if (candles.length < 20) return { zone: 'NONE', inZone: false };

  const close = candles[candles.length - 1].close;
  const e21   = ema(candles, 21);
  const e50   = ema(candles, 50);
  const rsiVal = rsi(candles, 14);
  const atrVal = atr(candles, 14);

  const demandSupplyZones = findDemandSupplyZones(candles, 40);
  const fvgs              = findFVG(candles, 40);
  const orderBlocks       = findOrderBlocks(candles, 40);
  const keyLevels         = findKeyLevels(candles, 50);

  // Price at zone check
  const priceTolerance = atrVal ? atrVal * 1.5 : close * 0.005;

  const atDemand = demandSupplyZones.some(z =>
    z.type === 'DEMAND' && close >= z.low - priceTolerance && close <= z.high + priceTolerance
  );
  const atSupply = demandSupplyZones.some(z =>
    z.type === 'SUPPLY' && close >= z.low - priceTolerance && close <= z.high + priceTolerance
  );
  const atBullOB = orderBlocks.some(ob =>
    ob.type === 'BULL_OB' && close >= ob.low - priceTolerance && close <= ob.high + priceTolerance
  );
  const atBearOB = orderBlocks.some(ob =>
    ob.type === 'BEAR_OB' && close >= ob.low - priceTolerance && close <= ob.high + priceTolerance
  );
  const atBullFVG = fvgs.some(f =>
    f.type === 'BULL_FVG' && close >= f.low - priceTolerance && close <= f.high + priceTolerance
  );
  const atBearFVG = fvgs.some(f =>
    f.type === 'BEAR_FVG' && close >= f.low - priceTolerance && close <= f.high + priceTolerance
  );

  // Near EMA21 pullback
  const ema21Dist = e21 ? Math.abs(close - e21) / e21 : 1;
  const atEMA21   = ema21Dist < 0.005;

  // Zone alignment with D1 bias
  const bullZone = (atDemand || atBullOB || atBullFVG || atEMA21) && rsiVal < 55;
  const bearZone = (atSupply || atBearOB || atBearFVG || atEMA21) && rsiVal > 45;

  const zone =
    d1Bias === 'BULL' && bullZone ? 'DEMAND' :
    d1Bias === 'BEAR' && bearZone ? 'SUPPLY' :
    'NONE';

  return {
    zone,
    inZone:          zone !== 'NONE',
    close,
    ema21:           e21,
    ema50:           e50,
    rsi:             rsiVal,
    atr:             atrVal,
    demandSupplyZones,
    orderBlocks,
    fvgs,
    keyLevels,
    flags: {
      atDemand, atSupply, atBullOB, atBearOB,
      atBullFVG, atBearFVG, atEMA21, bullZone, bearZone
    },
    reason: `H4 zone=${zone} rsi=${rsiVal.toFixed(1)} ema21Dist=${(ema21Dist * 100).toFixed(2)}%`
  };
}

// ── M15 Entry Analysis ───────────────────────────────────────

function detectBOS(candles, lookback = 10) {
  if (candles.length < lookback + 2) return { bull: false, bear: false };
  const slice = candles.slice(-lookback - 2);
  const prev  = slice.slice(0, -2);
  const curr  = slice[slice.length - 1];

  const swingHigh = Math.max(...prev.map(c => c.high));
  const swingLow  = Math.min(...prev.map(c => c.low));

  return {
    bull: curr.close > swingHigh,
    bear: curr.close < swingLow,
    swingHigh,
    swingLow
  };
}

function detectCHoCH(candles, lookback = 15) {
  if (candles.length < lookback + 5) return { bull: false, bear: false };
  const slice = candles.slice(-lookback);

  // Find recent trend direction
  let downleg = 0, upleg = 0;
  for (let i = 1; i < slice.length - 3; i++) {
    if (slice[i].low < slice[i - 1].low) downleg++;
    if (slice[i].high > slice[i - 1].high) upleg++;
  }

  const last3 = slice.slice(-4);
  const bullFlip = downleg > upleg && last3[3].close > last3[1].high;
  const bearFlip = upleg > downleg && last3[3].close < last3[1].low;

  return { bull: bullFlip, bear: bearFlip, downleg, upleg };
}

function detectEQHL(candles, lookback = 20) {
  const slice = candles.slice(-lookback);
  const tolerance = slice[slice.length - 1].close * 0.002;

  const highs = slice.map(c => c.high);
  const lows  = slice.map(c => c.low);

  const maxHigh = Math.max(...highs);
  const minLow  = Math.min(...lows);

  const eqHighs = highs.filter(h => Math.abs(h - maxHigh) < tolerance).length;
  const eqLows  = lows.filter(l => Math.abs(l - minLow)   < tolerance).length;

  return {
    eqHighs:     eqHighs >= 2,
    eqLows:      eqLows  >= 2,
    eqHighLevel: maxHigh,
    eqLowLevel:  minLow,
    bslAbove:    maxHigh,   // Buy-side liquidity resting above EQH
    sslBelow:    minLow     // Sell-side liquidity resting below EQL
  };
}

function detectLiquiditySweep(candles) {
  if (candles.length < 5) return { swept: false };
  const slice = candles.slice(-5);
  const last  = slice[slice.length - 1];
  const prev  = slice.slice(0, -1);

  const prevHigh = Math.max(...prev.map(c => c.high));
  const prevLow  = Math.min(...prev.map(c => c.low));

  // Wick swept above prevHigh and closed back below
  const highSweep = last.high > prevHigh && last.close < prevHigh;
  // Wick swept below prevLow and closed back above
  const lowSweep  = last.low  < prevLow  && last.close > prevLow;

  return {
    swept:     highSweep || lowSweep,
    highSweep,
    lowSweep,
    prevHigh,
    prevLow
  };
}

function checkSession() {
  const now   = new Date();
  const utcH  = now.getUTCHours();
  const utcM  = now.getUTCMinutes();
  const utcMin = utcH * 60 + utcM;

  const LO_START  = 7  * 60;     // 07:00 UTC
  const LO_END    = 12 * 60;     // 12:00 UTC
  const NYO_START = 12 * 60;     // 12:00 UTC
  const NYO_END   = 20 * 60;     // 20:00 UTC

  const inLO  = utcMin >= LO_START  && utcMin < LO_END;
  const inNYO = utcMin >= NYO_START && utcMin < NYO_END;

  return {
    session:  inLO ? 'LONDON' : inNYO ? 'NEW_YORK' : 'ASIAN',
    isActive: inLO || inNYO,
    inLO,
    inNYO
  };
}

function analyzeM15(candles, d1Bias, h4Zone) {
  if (candles.length < 20) return { signal: null };

  const close   = candles[candles.length - 1].close;
  const last    = candles[candles.length - 1];
  const e9      = ema(candles, 9);
  const e21     = ema(candles, 21);
  const e50     = ema(candles, 50);
  const rsiVal  = rsi(candles, 14);
  const atrVal  = atr(candles, 14) || close * 0.005;
  const macdVal = macd(candles);
  const bos     = detectBOS(candles, 8);
  const choch   = detectCHoCH(candles, 15);
  const eqhl    = detectEQHL(candles, 20);
  const sweep   = detectLiquiditySweep(candles);
  const session = checkSession();

  const body     = Math.abs(last.close - last.open);
  const range    = last.high - last.low;
  const bodyRatio = range > 0 ? body / range : 0;
  const strongBullCandle = last.close > last.open && bodyRatio > 0.55 && body > atrVal * 0.4;
  const strongBearCandle = last.close < last.open && bodyRatio > 0.55 && body > atrVal * 0.4;

  // EMA stack
  const bullEMAStack = e9 && e21 && e9 > e21;
  const bearEMAStack = e9 && e21 && e9 < e21;

  // ── BUY conditions ──
  const buyTrigger =
    d1Bias === 'BULL' &&
    h4Zone === 'DEMAND' &&
    (bos.bull || choch.bull || strongBullCandle) &&
    macdVal.bull &&
    rsiVal > 40 && rsiVal < 75 &&
    (bullEMAStack || strongBullCandle);

  // ── SELL conditions ──
  const sellTrigger =
    d1Bias === 'BEAR' &&
    h4Zone === 'SUPPLY' &&
    (bos.bear || choch.bear || strongBearCandle) &&
    !macdVal.bull &&
    rsiVal > 25 && rsiVal < 60 &&
    (bearEMAStack || strongBearCandle);

  // Session bonus
  const sessionBoost = session.isActive ? 10 : 0;

  // Confidence scoring
  let confidence = 50;
  if (bos.bull || bos.bear)     confidence += 15;
  if (choch.bull || choch.bear) confidence += 20;
  if (strongBullCandle || strongBearCandle) confidence += 10;
  if (macdVal.bull && buyTrigger)  confidence += 10;
  if (!macdVal.bull && sellTrigger) confidence += 10;
  if (sweep.swept)              confidence += 8;
  if (eqhl.eqHighs || eqhl.eqLows) confidence += 5;
  confidence += sessionBoost;
  confidence = Math.min(confidence, 98);

  const signal = buyTrigger ? 'BUY' : sellTrigger ? 'SELL' : null;

  return {
    signal,
    confidence,
    close,
    atr:   atrVal,
    rsi:   rsiVal,
    macd:  macdVal,
    ema9:  e9,
    ema21: e21,
    ema50: e50,
    bos,
    choch,
    eqhl,
    sweep,
    session,
    strongBullCandle,
    strongBearCandle,
    reason: signal
      ? `M15 ${signal}: BOS=${bos.bull || bos.bear} CHoCH=${choch.bull || choch.bear} MACD=${macdVal.bull} RSI=${rsiVal.toFixed(1)} Session=${session.session}`
      : `No M15 trigger (rsi=${rsiVal.toFixed(1)} bos=${JSON.stringify(bos)} choch=${JSON.stringify(choch)})`
  };
}

// ── TP / SL Calculator ───────────────────────────────────────

function calcTPSL(entry, direction, atrVal, h4Analysis, m15Analysis) {
  const slMultiplier = 1.5;
  const risk = atrVal * slMultiplier;

  const sl  = direction === 'BUY' ? entry - risk : entry + risk;

  // TP levels using R:R multiples, refined with H4 structure
  const keyLevels = h4Analysis.keyLevels;
  const baseRisk  = Math.abs(entry - sl);

  const tp = (r) => direction === 'BUY'
    ? entry + baseRisk * r
    : entry - baseRisk * r;

  // Snap TPs to nearby H4 structure if within 20% of R:R target
  const snap = (target, levels, dir) => {
    const candidates = dir === 'BUY'
      ? levels.filter(l => l > entry && l > target * 0.9 && l < target * 1.15)
      : levels.filter(l => l < entry && l < target * 1.1 && l > target * 0.85);
    return candidates.length > 0 ? candidates[0] : target;
  };

  const resistanceLevels = keyLevels?.resistance || [];
  const supportLevels    = keyLevels?.support    || [];
  const structureLevels  = direction === 'BUY' ? resistanceLevels : supportLevels;

  const tp1 = snap(tp(1.0), structureLevels, direction);
  const tp2 = snap(tp(2.0), structureLevels, direction);
  const tp3 = snap(tp(3.0), structureLevels, direction);
  const tp4 = tp(4.0);
  const tp5 = tp(5.0);

  const rr1 = Math.abs(tp1 - entry) / baseRisk;
  const rr2 = Math.abs(tp2 - entry) / baseRisk;
  const rr3 = Math.abs(tp3 - entry) / baseRisk;

  return {
    entry,
    sl,
    tp1, tp2, tp3, tp4, tp5,
    rr1, rr2, rr3,
    risk:        baseRisk,
    slPercent:   (Math.abs(entry - sl) / entry * 100).toFixed(3),
    partialExit: {
      tp1: '30% — move SL to breakeven',
      tp2: '30% — trail SL to TP1',
      tp3: '20% — trail SL to TP2',
      tp4: '10% — trail SL to TP3',
      tp5: '10% — let run'
    }
  };
}

// ── Main SMC Analysis ────────────────────────────────────────

const analysisCache = new Map();
const ANALYSIS_TTL = 60_000; // 1 min full analysis cache

export async function analyzeSMC(symbol) {
  const cached = analysisCache.get(symbol);
  if (cached && Date.now() - cached.ts < ANALYSIS_TTL) return cached.result;

  try {
    const [d1Candles, h4Candles, m15Candles] = await Promise.all([
      fetchKlines(symbol, '1d',  200),
      fetchKlines(symbol, '4h',  100),
      fetchKlines(symbol, '15m', 80)
    ]);

    if (!d1Candles.length || !h4Candles.length || !m15Candles.length) {
      return { symbol, signal: null, error: 'Insufficient kline data' };
    }

    const d1 = analyzeD1(d1Candles);
    const h4 = analyzeH4(h4Candles, d1.bias);
    const m15 = analyzeM15(m15Candles, d1.bias, h4.zone);

    const tpsl = m15.signal
      ? calcTPSL(m15.close, m15.signal, m15.atr, h4, m15)
      : null;

    const confluence =
      (d1.bias !== 'NEUTRAL' ? 1 : 0) +
      (h4.inZone ? 1 : 0) +
      (m15.bos.bull || m15.bos.bear ? 1 : 0) +
      (m15.choch.bull || m15.choch.bear ? 1 : 0) +
      (m15.session.isActive ? 1 : 0);

    const result = {
      symbol,
      timestamp:  Date.now(),
      signal:     m15.signal,
      confidence: m15.signal ? m15.confidence : 0,
      confluence,
      direction:  m15.signal,
      tpsl,
      d1,
      h4,
      m15,
      summary: m15.signal
        ? `${m15.signal} | D1=${d1.bias} H4=${h4.zone} BOS=${m15.bos.bull || m15.bos.bear} CHoCH=${m15.choch.bull || m15.choch.bear} Conf=${m15.confidence} Sess=${m15.session.session}`
        : `No signal | D1=${d1.bias} H4=${h4.zone || 'NONE'}`
    };

    analysisCache.set(symbol, { ts: Date.now(), result });
    return result;
  } catch (err) {
    return { symbol, signal: null, error: err.message };
  }
}

export function clearSMCCache(symbol) {
  if (symbol) {
    klineCache.delete(`${symbol}:1d`);
    klineCache.delete(`${symbol}:4h`);
    klineCache.delete(`${symbol}:15m`);
    analysisCache.delete(symbol);
  } else {
    klineCache.clear();
    analysisCache.clear();
  }
}

export { analyzeD1, analyzeH4, analyzeM15, calcTPSL, detectBOS, detectCHoCH, checkSession };
