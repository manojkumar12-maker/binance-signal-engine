import axios from 'axios';
import { config } from '../../config/config.js';

class MarketDataTracker {
  constructor() {
    this.buyVolume = 0;
    this.sellVolume = 0;
    this.orderflowHistory = new Map();
    this.openInterest = new Map();
    this.openInterestHistory = new Map();
    this.fundingRates = new Map();
    this.liquidationZones = new Map();
    this.symbols = [];
    this.lastOIUpdate = new Map();
    this.lastFundingUpdate = new Map();
  }

  initialize(symbols) {
    this.symbols = symbols;
    console.log('📊 Market Data Tracker initialized');
  }

  handleTrade(trade) {
    const symbol = trade.s;
    const qty = parseFloat(trade.q);
    const isBuyerMaker = trade.m;

    if (!this.orderflowHistory.has(symbol)) {
      this.orderflowHistory.set(symbol, { buy: 0, sell: 0, trades: [] });
    }

    const data = this.orderflowHistory.get(symbol);
    
    if (isBuyerMaker) {
      data.sell += qty;
    } else {
      data.buy += qty;
    }
    
    data.trades.push({ qty, isBuyerMaker, time: Date.now() });
    
    if (data.trades.length > 100) {
      data.trades = data.trades.slice(-100);
      const windowStart = Date.now() - 60000;
      data.buy = 0;
      data.sell = 0;
      data.trades.forEach(t => {
        if (t.time > windowStart) {
          if (t.isBuyerMaker) data.sell += t.qty;
          else data.buy += t.qty;
        }
      });
    }
  }

  getOrderflowRatio(symbol) {
    const data = this.orderflowHistory.get(symbol);
    if (!data) return 1;
    return data.buy / (data.sell || 1);
  }

  getOrderflowData(symbol) {
    const data = this.orderflowHistory.get(symbol);
    if (!data) return { ratio: 1, buyVolume: 0, sellVolume: 0, pressure: 'NEUTRAL' };
    
    const ratio = data.buy / (data.sell || 1);
    let pressure = 'NEUTRAL';
    
    if (ratio > 1.6) pressure = 'EXTREME_BUY';
    else if (ratio > 1.3) pressure = 'STRONG_BUY';
    else if (ratio > 1.1) pressure = 'BUY';
    else if (ratio < 0.7) pressure = 'EXTREME_SELL';
    else if (ratio < 0.8) pressure = 'SELL';
    
    return {
      ratio,
      buyVolume: data.buy,
      sellVolume: data.sell,
      pressure
    };
  }

  async updateOpenInterest(symbol) {
    const lastUpdate = this.lastOIUpdate.get(symbol) || 0;
    if (Date.now() - lastUpdate < 60000) return;

    try {
      const response = await axios.get(
        `${config.binance.apiUrl}/futures/data/openInterestHist`,
        {
          params: {
            symbol,
            period: '5m',
            limit: 2
          }
        }
      );

      if (response.data && response.data.length >= 2) {
        const current = parseFloat(response.data[1].sumOpenInterest);
        const previous = parseFloat(response.data[0].sumOpenInterest);
        
        const change = ((current - previous) / previous) * 100;
        
        this.openInterest.set(symbol, {
          current,
          previous,
          change,
          timestamp: Date.now()
        });
        
        if (!this.openInterestHistory.has(symbol)) {
          this.openInterestHistory.set(symbol, []);
        }
        
        const history = this.openInterestHistory.get(symbol);
        history.push({ oi: current, change, timestamp: Date.now() });
        
        if (history.length > 100) history.shift();
        
        this.lastOIUpdate.set(symbol, Date.now());
      }
    } catch (error) {
      // Silent fail - OI API may have rate limits
    }
  }

  getOpenInterestData(symbol) {
    const data = this.openInterest.get(symbol);
    if (!data) return { change: 0, trend: 'NEUTRAL' };
    
    let trend = 'NEUTRAL';
    if (data.change > 5) trend = 'STRONG_INCREASE';
    else if (data.change > 2) trend = 'INCREASE';
    else if (data.change < -5) trend = 'STRONG_DECREASE';
    else if (data.change < -2) trend = 'DECREASE';
    
    return {
      current: data.current,
      previous: data.previous,
      change: data.change,
      trend
    };
  }

  async updateFundingRate(symbol) {
    const lastUpdate = this.lastFundingUpdate.get(symbol) || 0;
    if (Date.now() - lastUpdate < 3600000) return;

    try {
      const response = await axios.get(
        `${config.binance.apiUrl}/fapi/v1/fundingRate`,
        {
          params: {
            symbol,
            limit: 1
          }
        }
      );

      if (response.data && response.data.length > 0) {
        const fundingRate = parseFloat(response.data[0].fundingRate);
        const nextFundingTime = parseInt(response.data[0].nextFundingTime);
        
        this.fundingRates.set(symbol, {
          rate: fundingRate,
          nextFundingTime,
          timestamp: Date.now()
        });
        
        this.lastFundingUpdate.set(symbol, Date.now());
      }
    } catch (error) {
      // Silent fail
    }
  }

  getFundingRateData(symbol) {
    const data = this.fundingRates.get(symbol);
    if (!data) return { rate: 0, bias: 'NEUTRAL', signal: 'HOLD' };
    
    const rate = data.rate * 100;
    let bias = 'NEUTRAL';
    let signal = 'HOLD';
    
    if (rate > 0.01) {
      bias = 'TOO_MANY_LONGS';
      signal = 'RISKY_LONG';
    } else if (rate < -0.01) {
      bias = 'TOO_MANY_SHORTS';
      signal = 'SHORT_SQUEEZE';
    }
    
    return {
      rate,
      nextFundingTime: data.nextFundingTime,
      bias,
      signal
    };
  }

  calculateLiquidationZones(candles) {
    if (!candles || candles.length < 20) {
      return { shortLiqZone: null, longLiqZone: null };
    }

    const recentHighs = candles.slice(-50).map(c => c.high);
    const recentLows = candles.slice(-50).map(c => c.low);
    
    const highestHigh = Math.max(...recentHighs);
    const lowestLow = Math.min(...recentLows);
    
    const shortLiqZone = highestHigh * 1.002;
    const longLiqZone = lowestLow * 0.998;
    
    return {
      shortLiqZone,
      longLiqZone,
      highestHigh,
      lowestLow
    };
  }

  getMarketRegime(symbol) {
    const oi = this.getOpenInterestData(symbol);
    const funding = this.getFundingRateData(symbol);
    
    if (oi.change > 2 && funding.rate > 0) {
      return 'STRONG_TREND';
    }
    if (oi.change > 2 && funding.rate < 0) {
      return 'SHORT_SQUEEZE';
    }
    if (oi.change < -2 && funding.rate > 0) {
      return 'LONG_SQUEEZE';
    }
    if (oi.change < -2 && funding.rate < 0) {
      return 'WEAK_MARKET';
    }
    
    return 'BALANCED';
  }

  getEnhancedConfidence(baseConfidence, symbol, priceChange) {
    let confidence = baseConfidence;
    const bonuses = [];
    const penalties = [];

    const orderflow = this.getOrderflowData(symbol);
    const oi = this.getOpenInterestData(symbol);
    const funding = this.getFundingRateData(symbol);
    const regime = this.getMarketRegime(symbol);

    if (orderflow.ratio > 1.5 && oi.change > 3) {
      confidence += 20;
      bonuses.push(`OF+OI Combo: ${orderflow.ratio.toFixed(2)}x + ${oi.change.toFixed(1)}% (+20)`);
    } else {
      if (orderflow.ratio > 1.6) {
        confidence += 10;
        bonuses.push(`Orderflow: ${orderflow.ratio.toFixed(2)}x (+10)`);
      } else if (orderflow.ratio > 1.3) {
        confidence += 5;
        bonuses.push(`Orderflow: ${orderflow.ratio.toFixed(2)}x (+5)`);
      }
      
      if (oi.change > 5) {
        confidence += 10;
        bonuses.push(`OI: +${oi.change.toFixed(1)}% (+10)`);
      } else if (oi.change > 2) {
        confidence += 5;
        bonuses.push(`OI: +${oi.change.toFixed(1)}% (+5)`);
      }
    }

    if (funding.rate < -0.01 && oi.change > 2) {
      confidence += 20;
      bonuses.push('Funding+OI Squeeze (+20)');
    } else if (funding.signal === 'SHORT_SQUEEZE' && priceChange > 0) {
      confidence += 15;
      bonuses.push('Funding Short Squeeze (+15)');
    } else if (funding.signal === 'RISKY_LONG' && priceChange > 0) {
      confidence -= 10;
      penalties.push('Crowded Longs (-10)');
    }

    if (oi.change < -2) {
      confidence -= 10;
      penalties.push(`OI Decrease: ${oi.change.toFixed(1)}% (-10)`);
    }

    if (orderflow.ratio < 0.8) {
      confidence -= 15;
      penalties.push(`Weak Orderflow: ${orderflow.ratio.toFixed(2)}x (-15)`);
    }

    if (regime === 'WEAK_MARKET' || regime === 'BALANCED') {
      confidence -= 5;
      penalties.push(`Regime: ${regime} (-5)`);
    }

    return {
      confidence: Math.min(Math.max(confidence, 0), 100),
      bonuses,
      penalties,
      orderflow,
      openInterest: oi,
      funding,
      regime
    };
  }

  getSummary() {
    return {
      trackedSymbols: this.symbols.length,
      symbolsWithOrderflow: this.orderflowHistory.size,
      symbolsWithOI: this.openInterest.size,
      symbolsWithFunding: this.fundingRates.size
    };
  }
}

export const marketDataTracker = new MarketDataTracker();
