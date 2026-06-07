from flask import Flask, jsonify, render_template
import yfinance as yf
import pandas as pd

app = Flask(__name__)

def get_high_short_interest_tickers():
    return list(set([
        # Meme / retail favorites
        "GME", "AMC", "KOSS", "EXPR", "CLOV", "WISH", "MVIS", "BBBY",
        # EV / clean energy
        "RIVN", "LCID", "NKLA", "WKHS", "SPCE", "BLNK", "CHPT", "FSR",
        "GOEV", "HYLN", "HYZN", "XPEV", "LI", "PSNY", "FFIE",
        # Crypto adjacent
        "MARA", "RIOT", "HUT", "CLSK", "COIN", "BTBT", "CIFR", "MSTR",
        "CORZ", "IREN", "WULF", "SMLR",
        # Fintech / BNPL
        "SOFI", "HOOD", "UPST", "AFRM", "OPEN", "LMND", "ROOT", "METC",
        "DAVE", "MQ", "PAYC", "PAYO", "LPRO",
        # AI / tech speculative
        "AI", "SOUN", "BBAI", "GFAI", "AEYE", "PRCT", "AMBA",
        "POET", "KOPN", "ADTX", "INPX", "TPVG",
        # Biotech
        "SAVA", "FLGT", "OCGN", "ATOS", "NUVB", "PRGO",
        "ARDX", "ACRS", "TRVN", "FGEN", "SUPN",
        "NVAX", "SRNE", "CRVS", "INMB", "ALDX", "AVDL",
        "FREQ", "HOOK", "IMVT",
        # Retail / consumer
        "BYND", "REAL", "BBWI", "PRTY", "SKIN",
        "BIRD", "LOVE", "GOED", "COOK", "HIMS",
        # Energy speculative
        "TELL", "GEVO", "REI", "INDO",
        "AMPY", "SPWR", "FCEL", "PLUG", "BE",
        # Squeeze watchlist regulars
        "PLTR", "NIO", "DKNG", "PENN", "CHWY", "W", "CVNA", "PTON",
        "SNAP", "RBLX", "BROS", "RENT", "MAPS", "OPAD",
        "PUBM", "MGNI", "TTD", "APPS", "DV",
        # Biotech continued
        "PSFE", "VERV", "DAWN", "APLS", "INSM", "ALNY",
        "BEAM", "EDIT", "CRSP", "NTLA", "BLUE", "FATE",
        "RXRX", "TNGX", "TWST", "XNCR",
        # Small cap speculative
        "CXAI", "BKSY", "SPIR", "RCAT", "PXLW",
    ]))


def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def get_squeeze_score(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="3mo")

        if hist.empty or len(hist) < 30:
            return None

        short_float = info.get("shortPercentOfFloat", None)
        short_ratio = info.get("shortRatio", None)
        avg_volume = info.get("averageVolume", 1)
        current_volume = info.get("volume", 0)
        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        shares_short = info.get("sharesShort", 0)
        shares_short_prior = info.get("sharesShortPriorMonth", 0)
        sector = info.get("sector", "Unknown")
        market_cap = info.get("marketCap", 0)

        if not short_float or not short_ratio or not price:
            return None

        closes = hist["Close"]
        volumes = hist["Volume"]

        # 20 day moving average
        ma20 = closes.rolling(window=20).mean().iloc[-1]
        above_ma20 = bool(price > ma20)

        # 50 day moving average
        ma50 = closes.rolling(window=50).mean().iloc[-1] if len(closes) >= 50 else None
        above_ma50 = bool(price > ma50) if ma50 else False

        # Higher highs structure
        higher_highs = bool(
            closes.iloc[-1] > closes.iloc[-3] and
            closes.iloc[-3] > closes.iloc[-5]
        )

        # Volume increasing 3 consecutive days
        vol_increasing = bool(
            volumes.iloc[-1] > volumes.iloc[-2] and
            volumes.iloc[-2] > volumes.iloc[-3]
        )

        # Volume spike vs average
        volume_ratio = round(float(current_volume / avg_volume), 2) if avg_volume else 0

        # Short interest declining
        if shares_short and shares_short_prior and shares_short_prior > 0:
            short_change = float(((shares_short - shares_short_prior) / shares_short_prior) * 100)
            shorts_covering = bool(short_change < -2)
        else:
            short_change = 0.0
            shorts_covering = False

        # RSI
        rsi_series = calculate_rsi(closes)
        rsi = round(float(rsi_series.iloc[-1]), 2)
        rsi_prev = round(float(rsi_series.iloc[-3]), 2)
        rsi_rising = bool(rsi > rsi_prev)
        rsi_in_zone = bool(50 <= rsi <= 75)

        # Momentum
        momentum_5d = round(float(((price - closes.iloc[-5]) / closes.iloc[-5]) * 100), 2)
        momentum_1m = round(float(((price - closes.iloc[-21]) / closes.iloc[-21]) * 100), 2)

        # 52 week position
        fifty_two_week_low = info.get("fiftyTwoWeekLow", None)
        fifty_two_week_high = info.get("fiftyTwoWeekHigh", None)
        if fifty_two_week_low and fifty_two_week_high and fifty_two_week_high != fifty_two_week_low:
            week52_position = round(float((price - fifty_two_week_low) / (fifty_two_week_high - fifty_two_week_low) * 100), 1)
        else:
            week52_position = 50.0

        # -----------------------------------------------
        # ACTIVE SQUEEZE SCORE
        # -----------------------------------------------
        score = 0
        flags = []

        # 1. Price above 20MA (25 pts)
        if above_ma20:
            score += 25
            flags.append("Above 20MA")

        # 2. Volume increasing 3 consecutive days (20 pts)
        if vol_increasing:
            score += 20
            flags.append("Vol 3-Day Surge")

        # 3. Higher highs (20 pts)
        if higher_highs:
            score += 20
            flags.append("Higher Highs")

        # 4. Shorts covering (15 pts)
        if shorts_covering:
            score += 15
            flags.append("Shorts Covering")

        # 5. RSI rising and in zone (10 pts)
        if rsi_in_zone and rsi_rising:
            score += 10
            flags.append("RSI Confirming")

        # 6. Volume spike today (5 pts)
        if volume_ratio > 1.5:
            score += 5
            flags.append("Vol Spike Today")

        # 7. Above 50MA bonus (5 pts)
        if above_ma50:
            score += 5
            flags.append("Above 50MA")

        # Penalize low short interest
        short_float_pct = round(float(short_float * 100), 2)
        if short_float_pct < 10:
            score = score * 0.5

        score = round(min(max(score, 0), 100), 1)

        if score >= 70:
            signal = "🔥 Squeezing"
        elif score >= 45:
            signal = "⚡ Starting"
        elif score >= 20:
            signal = "👀 Watch"
        else:
            signal = "💤 No Signal"

        return {
            "ticker": ticker,
            "price": round(float(price), 2),
            "short_float": short_float_pct,
            "days_to_cover": round(float(short_ratio), 2),
            "volume_ratio": volume_ratio,
            "momentum_5d": momentum_5d,
            "momentum_1m": momentum_1m,
            "rsi": rsi,
            "week52_position": week52_position,
            "above_ma20": above_ma20,
            "above_ma50": above_ma50,
            "higher_highs": higher_highs,
            "vol_increasing": vol_increasing,
            "shorts_covering": shorts_covering,
            "rsi_confirming": bool(rsi_in_zone and rsi_rising),
            "short_change": round(float(short_change), 2),
            "squeeze_score": score,
            "signal": signal,
            "flags": flags,
            "sector": sector,
            "market_cap": int(market_cap) if market_cap else 0,
            "score_breakdown": {
                "above_ma20": 25 if above_ma20 else 0,
                "vol_surge": 20 if vol_increasing else 0,
                "higher_highs": 20 if higher_highs else 0,
                "shorts_covering": 15 if shorts_covering else 0,
                "rsi_confirming": 10 if (rsi_in_zone and rsi_rising) else 0,
                "vol_spike": 5 if volume_ratio > 1.5 else 0,
                "above_ma50": 5 if above_ma50 else 0,
            }
        }

    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan")
def scan():
    tickers = get_high_short_interest_tickers()
    results = []
    for ticker in tickers:
        data = get_squeeze_score(ticker)
        if data:
            results.append(data)
    results.sort(key=lambda x: x["squeeze_score"], reverse=True)
    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True)