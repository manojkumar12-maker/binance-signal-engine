import Redis from 'ioredis';

let redis = null;
let isConnected = false;

const CACHE_TTL = {
  signals: 300,      // 5 minutes
  stats: 10,         // 10 seconds
  recentSignals: 30  // 30 seconds
};

export async function initRedis() {
  const redisUrl = process.env.REDIS_URL;
  
  if (!redisUrl) {
    console.log('⚠️ REDIS_URL not set — Redis caching disabled');
    return false;
  }

  try {
    redis = new Redis(redisUrl, {
      maxRetriesPerRequest: 3,
      retryStrategy(times) {
        if (times > 5) return null;
        return Math.min(times * 200, 2000);
      },
      lazyConnect: true
    });

    redis.on('connect', () => {
      isConnected = true;
      console.log('✅ Redis connected');
    });

    redis.on('error', (err) => {
      console.error('⚠️ Redis error:', err.message);
      isConnected = false;
    });

    redis.on('close', () => {
      isConnected = false;
    });

    await redis.connect();
    return true;
  } catch (error) {
    console.error('⚠️ Redis connection failed:', error.message);
    isConnected = false;
    return false;
  }
}

export async function cacheGet(key) {
  if (!isConnected || !redis) return null;
  try {
    const data = await redis.get(key);
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

export async function cacheSet(key, value, ttlSeconds) {
  if (!isConnected || !redis) return;
  try {
    await redis.set(key, JSON.stringify(value), 'EX', ttlSeconds || CACHE_TTL.signals);
  } catch {
    // silent fail
  }
}

export async function cacheDelete(key) {
  if (!isConnected || !redis) return;
  try {
    await redis.del(key);
  } catch {
    // silent fail
  }
}

export async function invalidateSignalCache() {
  await cacheDelete('signals:recent');
  await cacheDelete('signals:stats');
}

export async function closeRedis() {
  if (redis) {
    try {
      await redis.quit();
    } catch {
      // silent fail
    }
  }
}

export { CACHE_TTL, isConnected as redisConnected };
