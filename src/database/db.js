import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function initDatabase() {
  try {
    await prisma.$connect();
    console.log('✅ Database connected');
  } catch (error) {
    console.error('❌ Database connection failed:', error);
    throw error;
  }
}

export async function createSignal(data) {
  return prisma.signal.create({
    data: {
      symbol: data.symbol,
      type: data.type,
      tier: data.tier,
      entryPrice: data.entryPrice,
      atr: data.atr,
      tp1: data.targets.tp1,
      tp2: data.targets.tp2,
      tp3: data.targets.tp3,
      tp4: data.targets.tp4,
      tp5: data.targets.tp5,
      stopLoss: data.stopLoss,
      tp1RR: data.riskReward?.tp1 ? parseFloat(data.riskReward.tp1) : null,
      tp2RR: data.riskReward?.tp2 ? parseFloat(data.riskReward.tp2) : null,
      tp3RR: data.riskReward?.tp3 ? parseFloat(data.riskReward.tp3) : null,
      priceChange: parseFloat(data.metrics.priceChange),
      volumeSpike: parseFloat(data.metrics.volumeSpike),
      momentum: data.metrics.momentum ? parseFloat(data.metrics.momentum) : null,
      score: data.metrics.score,
      factors: JSON.stringify(data.factors || []),
      metadata: JSON.stringify(data.metadata || {}),
      status: data.status,
    }
  });
}

export async function getSignals(limit = 100, status = null) {
  const where = status ? { status } : {};
  return prisma.signal.findMany({
    where,
    orderBy: { timestamp: 'desc' },
    take: limit
  });
}

export async function getSignalBySymbol(symbol) {
  return prisma.signal.findFirst({
    where: { symbol, status: 'ACTIVE' },
    orderBy: { timestamp: 'desc' }
  });
}

export async function updateSignalStatus(id, status, closedPrice = null) {
  return prisma.signal.update({
    where: { id },
    data: {
      status,
      closedAt: closedPrice ? new Date() : null,
      closedPrice
    }
  });
}

export async function updateSignal(id, data) {
  return prisma.signal.update({
    where: { id },
    data
  });
}

export async function getSignalStats() {
  const [total, active, tpHits, stoppedOut] = await Promise.all([
    prisma.signal.count(),
    prisma.signal.count({ where: { status: 'ACTIVE' } }),
    prisma.signal.count({ where: { status: { startsWith: 'TP' } } }),
    prisma.signal.count({ where: { status: 'STOPPED_OUT' } })
  ]);

  const byTier = await prisma.signal.groupBy({
    by: ['tier'],
    _count: true
  });

  const tierCounts = { SNIPER: 0, CONFIRMED: 0, EARLY: 0 };
  byTier.forEach(t => {
    if (tierCounts.hasOwnProperty(t.tier)) {
      tierCounts[t.tier] = t._count;
    }
  });

  return {
    total,
    active,
    tpHits,
    stoppedOut,
    tierCounts
  };
}

export async function closeDatabase() {
  await prisma.$disconnect();
}

export { prisma };
