# Binance Signal Engine - Specification Document

## Project Overview

**Project Name:** Binance Signal Engine  
**Type:** Trading Signal Web Application  
**Core Functionality:** Real-time trading signal generation based on Smart Money Concepts (Market Structure + Liquidity Sweeps + Volume Confirmation)  
**Target Users:** Crypto traders seeking institutional-style trade signals

---

## Architecture

```
┌─────────────────────┐
│  Frontend (GitHub   │
│  Pages)             │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Backend (Railway)  │
│  Python FastAPI     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Data Layer         │
│  Binance API        │
└─────────────────────┘
```

---

## UI/UX Specification

### Layout Structure

**Header (80px)**
- Logo/App name: "BINANCE SIGNAL ENGINE"
- Status indicator (API connected/disconnected)

**Main Content**
- Trading pair selector (dropdown)
- Signal display card (centered, prominent)
- Signal details panel (Entry, SL, TP1, TP2, TP3)
- Confidence score display
- Market structure indicators

**Footer (40px)**
- Last update timestamp
- Refresh button

### Visual Design

**Color Palette:**
- Background: `#0a0e17` (dark navy)
- Card Background: `#151c28` (slate)
- Primary Accent: `#f0b90b` (Binance Yellow)
- Buy Signal: `#00c087` (green)
- Sell Signal: `#f6465d` (red)
- Neutral/No Trade: `#6c7280` (gray)
- Text Primary: `#eaecef`
- Text Secondary: `#848e9c`
- Border: `#2b3139`

**Typography:**
- Title Font: "Orbitron" (Google Fonts) - 28px
- Headings: "Orbitron" - 18px
- Body: "IBM Plex Mono" - 14px
- Signal Numbers: "IBM Plex Mono" - 24px bold

**Spacing:**
- Base unit: 8px
- Card padding: 24px
- Section margins: 16px

**Visual Effects:**
- Cards: 1px border, subtle glow on hover
- Signal cards: Colored border based on direction (green/red)
- Pulse animation on new signal
- Smooth transitions (0.3s)

### Components

**1. Pair Selector**
- Dropdown with popular pairs (BTCUSDT, ETHUSDT, etc.)
- Timeframe selector (15m, 1H, 4H)

**2. Signal Card**
- Large directional indicator (BUY/SELL/NO TRADE)
- Entry price prominently displayed
- Color-coded border

**3. Trade Details Panel**
- Entry price
- Stop Loss (SL)
- Take Profit 1 (TP1) - 1% risk:reward
- Take Profit 2 (TP2) - 2% risk:reward
- Take Profit 3 (TP3) - 3% risk:reward

**4. Confidence Meter**
- Circular progress indicator
- Percentage display
- Color gradient (red → yellow → green)

**5. Strategy Indicators**
- Trend: UPTREND / DOWNTREND / RANGE
- Liquidity Sweep: detected / not detected
- Volume: Confirmed / Weak

---

## Functionality Specification

### Core Features

**1. Market Structure Analysis**
- Detect Higher Highs (HH) + Higher Lows (HL) = UPTREND
- Detect Lower Highs (LH) + Lower Lows (LL) = DOWNTREND
- Otherwise = RANGE (no trade)
- Timeframe: Configurable (default 1H)

**2. Liquidity Sweep Detection**
- Track recent swing highs/lows
- Detect when price sweeps equal highs (stop hunt)
- Detect when price sweeps equal lows
- Return: SWEEP_HIGH, SWEEP_LOW, or None

**3. Volume Confirmation**
- Use Binance Open Interest data (for futures)
- Detect OI spike (>40% above 5-period average)
- Return: True/False

**4. Signal Generation**
- Combine all filters
- Only generate signal if ALL criteria met:
  - ✅ Clear trend (not RANGE)
  - ✅ Liquidity sweep occurred
  - ✅ Volume confirms
- Otherwise return NO TRADE

**5. Trade Execution Levels**
- Entry: Current price
- SL: 0.5% below/above entry (for BUY/SELL)
- TP1: 1% above/below (1:2 R:R)
- TP2: 2% above/below (1:4 R:R)
- TP3: 3% above/below (1:6 R:R)

**6. Confidence Scoring**
- Trend identified: 30 points
- Liquidity sweep: 30 points
- Volume confirmed: 40 points
- Total: 100 points

### API Endpoints

```
GET /api/signal/{pair}?timeframe=1h
```

Response:
```json
{
  "pair": "BTCUSDT",
  "signal": "BUY",
  "entry": 65000.00,
  "sl": 64675.00,
  "tp1": 65650.00,
  "tp2": 66300.00,
  "tp3": 66950.00,
  "confidence": 85,
  "trend": "UPTREND",
  "liquidity": "SWEEP_LOW",
  "volume": true,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### User Interactions

- Select trading pair from dropdown
- Select timeframe (15m, 1H, 4H)
- Click refresh to get new signal
- Auto-refresh every 5 minutes

### Edge Cases

- API rate limiting: Implement caching
- Network error: Show last cached signal
- Invalid pair: Return error message
- No trade condition: Show "NO TRADE" with reason

---

## Acceptance Criteria

### Visual Checkpoints
- [ ] Dark theme with Binance yellow accents visible
- [ ] Signal card displays with correct color coding
- [ ] All fonts load (Orbitron, IBM Plex Mono)
- [ ] Confidence meter shows percentage correctly
- [ ] Responsive on mobile devices

### Functional Checkpoints
- [ ] Signal API returns correct format
- [ ] Trend detection works (HH+HL, LH+LL)
- [ ] Liquidity sweep detection works
- [ ] OI/volume check works
- [ ] Trade levels calculated correctly
- [ ] Frontend fetches and displays signals
- [ ] Auto-refresh works

### Performance
- [ ] API response under 2 seconds
- [ ] No console errors
- [ ] Smooth UI interactions

---

## File Structure

```
binance-signal-engine/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   └── signal.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── market.py
│   │   │   ├── structure.py
│   │   │   ├── liquidity.py
│   │   │   ├── volume.py
│   │   │   ├── strategy.py
│   │   │   └── scoring.py
│   │   └── models/
│   │       ├── __init__.py
│   │       └── signal_model.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.json
│
├── frontend/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── README.md
│
└── SPEC.md
```
