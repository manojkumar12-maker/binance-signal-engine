'use client'

import { useEffect, useState } from 'react'
import { getActiveSignals, getRecentTrades, subscribeToSignals } from '../lib/supabase'
import SignalCard from '../components/SignalCard'

export default function Dashboard() {
  const [signals, setSignals] = useState<any[]>([])
  const [trades, setTrades] = useState<any[]>([])
  const [stats, setStats] = useState({
    totalSignals: 0,
    winRate: 0,
    avgConfidence: 0,
    activeTrades: 0
  })

  useEffect(() => {
    loadData()

    // Subscribe to realtime signals
    const unsubscribe = subscribeToSignals((newSignal) => {
      setSignals(prev => [newSignal, ...prev])
    })

    return () => unsubscribe()
  }, [])

  async function loadData() {
    const [signalsData, tradesData] = await Promise.all([
      getActiveSignals(),
      getRecentTrades()
    ])

    setSignals(signalsData)
    setTrades(tradesData)

    // Calculate stats
    const winTrades = tradesData.filter((t: any) => (t.pnl || 0) > 0)
    const winRate = tradesData.length > 0 ? (winTrades.length / tradesData.length) * 100 : 0
    const avgConfidence = signalsData.length > 0 
      ? signalsData.reduce((sum: number, s: any) => sum + (s.confidence || 0), 0) / signalsData.length 
      : 0

    setStats({
      totalSignals: signalsData.length,
      winRate: Math.round(winRate * 10) / 10,
      avgConfidence: Math.round(avgConfidence * 10) / 10,
      activeTrades: tradesData.filter((t: any) => t.status === 'OPEN').length
    })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Binance Signal Engine</h1>
              <p className="text-sm text-gray-500">Institutional-grade signal platform</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              <span className="text-sm text-gray-600">Live</span>
            </div>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-600">Active Signals</div>
            <div className="text-2xl font-bold text-blue-600">{stats.totalSignals}</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-600">Win Rate</div>
            <div className="text-2xl font-bold text-green-600">{stats.winRate}%</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-600">Avg Confidence</div>
            <div className="text-2xl font-bold text-purple-600">{stats.avgConfidence}%</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-600">Active Trades</div>
            <div className="text-2xl font-bold text-orange-600">{stats.activeTrades}</div>
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-2 gap-8">
          {/* Signals */}
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">Active Signals</h2>
              <span className="text-sm text-gray-500">{signals.length} signals</span>
            </div>
            <div className="space-y-4">
              {signals.length === 0 ? (
                <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                  No active signals
                </div>
              ) : (
                signals.map((signal) => (
                  <SignalCard key={signal.id} signal={signal} />
                ))
              )}
            </div>
          </div>

          {/* Trades */}
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">Recent Trades</h2>
              <span className="text-sm text-gray-500">{trades.length} trades</span>
            </div>
            <div className="space-y-4">
              {trades.length === 0 ? (
                <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                  No trades yet
                </div>
              ) : (
                trades.map((trade) => (
                  <div key={trade.id} className="bg-white rounded-lg shadow p-4">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-bold">{trade.pair}</span>
                      <span className={`px-2 py-1 rounded text-sm ${
                        trade.status === 'OPEN' ? 'bg-blue-100 text-blue-800' :
                        trade.status === 'SL' ? 'bg-red-100 text-red-800' :
                        'bg-green-100 text-green-800'
                      }`}>
                        {trade.status}
                      </span>
                    </div>
                    <div className="text-sm text-gray-600">
                      Entry: ${trade.entry} | PnL: 
                      <span className={trade.pnl > 0 ? 'text-green-600' : 'text-red-600'}>
                        {trade.pnl > 0 ? '+' : ''}{trade.pnl}%
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
