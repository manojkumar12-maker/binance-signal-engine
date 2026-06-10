export default function SignalCard({ signal }: { signal: any }) {
  const isBuy = signal.signal === 'BUY'
  const isSniper = signal.tier === 'SNIPER'
  
  return (
    <div className={`border rounded-lg p-4 mb-4 ${isBuy ? 'border-green-300' : 'border-red-300'}`}>
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold">{signal.pair}</span>
          <span className={`px-2 py-1 rounded text-sm font-semibold ${
            isBuy ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            {signal.signal}
          </span>
          {isSniper && (
            <span className="px-2 py-1 rounded text-sm bg-purple-100 text-purple-800">
              🎯 SNIPER
            </span>
          )}
        </div>
        <span className="text-sm text-gray-500">
          {new Date(signal.created_at).toLocaleTimeString()}
        </span>
      </div>
      
      <div className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <span className="text-gray-600">Entry:</span>
          <span className="ml-1 font-mono">${signal.entry}</span>
        </div>
        <div>
          <span className="text-gray-600">SL:</span>
          <span className="ml-1 font-mono">${signal.sl}</span>
        </div>
        <div>
          <span className="text-gray-600">TP1:</span>
          <span className="ml-1 font-mono">${signal.tp1}</span>
        </div>
      </div>
      
      <div className="mt-3 flex justify-between items-center">
        <div className="flex items-center gap-4">
          <span className="text-sm">
            <span className="text-gray-600">Confidence:</span>
            <span className={`ml-1 font-bold ${signal.confidence >= 90 ? 'text-purple-600' : signal.confidence >= 80 ? 'text-blue-600' : 'text-yellow-600'}`}>
              {signal.confidence}%
            </span>
          </span>
          <span className="text-sm">
            <span className="text-gray-600">Regime:</span>
            <span className="ml-1">{signal.regime}</span>
          </span>
        </div>
        <span className={`text-xs px-2 py-1 rounded ${
          signal.confidence >= 90 ? 'bg-purple-100 text-purple-800' : 
          signal.confidence >= 80 ? 'bg-blue-100 text-blue-800' : 
          'bg-gray-100 text-gray-800'
        }`}>
          {signal.tier}
        </span>
      </div>
    </div>
  )
}
