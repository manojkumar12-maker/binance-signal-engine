import axios from 'axios';
import { config } from '../../config/config.js';

export class FundingService {
  constructor() {
    this.cache = new Map();
    this.lastFetch = new Map();
    this.fetchInterval = 60000;
  }

  async fetch(symbol) {
    const now = Date.now();
    const lastFetch = this.lastFetch.get(symbol) || 0;
    
    if (now - lastFetch < this.fetchInterval) {
      return this.cache.get(symbol) || { rate: 0, nextFunding: null };
    }

    try {
      const res = await axios.get(
        `${config.binance.apiUrl}/fapi/v1/premiumIndex`,
        {
          params: { symbol },
          timeout: 5000
        }
      );

      const rate = parseFloat(res.data.lastFundingRate);
      const nextFunding = parseInt(res.data.nextFundingTime);

      if (isNaN(rate)) {
        return this.cache.get(symbol) || { rate: 0, nextFunding: null };
      }

      const data = { rate, nextFunding, timestamp: now };
      this.cache.set(symbol, data);
      this.lastFetch.set(symbol, now);

      return data;
    } catch (e) {
      return this.cache.get(symbol) || { rate: 0, nextFunding: null };
    }
  }

  async fetchBatch(symbols) {
    const results = [];
    for (const symbol of symbols) {
      const data = await this.fetch(symbol);
      results.push({ symbol, ...data });
    }
    return results;
  }

  getRate(symbol) {
    const data = this.cache.get(symbol);
    return data?.rate || 0;
  }

  getFundingData(symbol) {
    const data = this.cache.get(symbol);
    if (!data) {
      return { rate: 0, nextFunding: null, bias: 'NEUTRAL', signal: 'HOLD' };
    }

    const ratePercent = data.rate * 100;
    
    let bias = 'NEUTRAL';
    let signal = 'HOLD';

    if (ratePercent < -0.01) {
      bias = 'TOO_MANY_SHORTS';
      signal = 'SHORT_SQUEEZE';
    } else if (ratePercent < -0.005) {
      bias = 'MORE_SHORTS';
      signal = 'POTENTIAL_SQUEEZE';
    } else if (ratePercent > 0.01) {
      bias = 'TOO_MANY_LONGS';
      signal = 'RISKY_LONG';
    } else if (ratePercent > 0.005) {
      bias = 'MORE_LONGS';
      signal = 'CAUTION';
    }

    return {
      rate: data.rate,
      ratePercent,
      nextFunding: data.nextFunding,
      bias,
      signal
    };
  }

  isShortSqueeze(symbol, priceChange) {
    const data = this.getFundingData(symbol);
    return data.ratePercent < -0.01 && priceChange > 0;
  }

  isCrowdedLongs(symbol, priceChange) {
    const data = this.getFundingData(symbol);
    return data.ratePercent > 0.01 && priceChange > 0;
  }

  getStats() {
    let shortSqueezeCount = 0;
    let crowdedLongsCount = 0;
    let neutralCount = 0;

    for (const [symbol, data] of this.cache.entries()) {
      const ratePercent = data.rate * 100;
      if (ratePercent < -0.01) shortSqueezeCount++;
      else if (ratePercent > 0.01) crowdedLongsCount++;
      else neutralCount++;
    }

    return {
      tracked: this.cache.size,
      shortSqueeze: shortSqueezeCount,
      crowdedLongs: crowdedLongsCount,
      neutral: neutralCount
    };
  }
}

export const fundingService = new FundingService();
