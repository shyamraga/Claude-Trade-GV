"""
Market Hours and Holiday Calendar Manager.

Enforces real-world trading sessions across global timezones:
- US Equities (NYSE / NASDAQ): 09:30 - 16:00 ET (Mon-Fri), closed weekends and official holidays.
  Early close at 13:00 ET on Black Friday, Christmas Eve, and July 3rd.
- Indian Equities (NSE / BSE): 09:15 - 15:30 IST (Mon-Fri), closed weekends and NSE holidays.
- Crypto: Runs 24/7/365 with continuous trading and zero holiday shutdowns.
"""

import logging
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Optional, List, Dict, Tuple, Set, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Timezones
TZ_US = ZoneInfo("America/New_York")
TZ_INDIA = ZoneInfo("Asia/Kolkata")
TZ_UTC = ZoneInfo("UTC")


class MarketType(str, Enum):
    US_EQUITY = "US_EQUITY"
    INDIA_EQUITY = "INDIA_EQUITY"
    CRYPTO = "CRYPTO"
    METALS = "METALS"
    UNKNOWN = "UNKNOWN"


def get_easter_date(year: int) -> date:
    """Meeus/Jones/Butcher Gregorian Easter calculation."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    Find nth occurrence of weekday (0=Mon, ..., 6=Sun) in given month.
    If n == -1, returns the last occurrence in the month.
    """
    if n > 0:
        d = date(year, month, 1)
        day_shift = (weekday - d.weekday()) % 7
        target_day = 1 + day_shift + (n - 1) * 7
        return date(year, month, target_day)
    else:  # Last occurrence
        # Start at end of month
        if month == 12:
            next_m = date(year + 1, 1, 1)
        else:
            next_m = date(year, month + 1, 1)
        last_d = next_m - timedelta(days=1)
        day_shift = (last_d.weekday() - weekday) % 7
        return last_d - timedelta(days=day_shift)


class MarketHoursManager:
    """
    Comprehensive multi-asset session and holiday manager.
    Arbitrates symbol routing based on real-time market open/close status.
    """

    # Known floating Indian holidays for 2024-2027
    KNOWN_INDIAN_HOLIDAYS: Set[date] = {
        # 2024
        date(2024, 3, 8),   # Mahashivratri
        date(2024, 3, 25),  # Holi
        date(2024, 3, 29),  # Good Friday
        date(2024, 4, 11),  # Id-Ul-Fitr
        date(2024, 4, 17),  # Ram Navami
        date(2024, 6, 17),  # Bakri Id
        date(2024, 7, 17),  # Muharram
        date(2024, 11, 1),  # Diwali Laxmi Pujan
        date(2024, 11, 15), # Gurunanak Jayanti
        # 2025
        date(2025, 2, 26),  # Mahashivratri
        date(2025, 3, 14),  # Holi
        date(2025, 3, 31),  # Id-Ul-Fitr
        date(2025, 4, 18),  # Good Friday
        date(2025, 6, 7),   # Bakri Id
        date(2025, 10, 2),  # Dussehra / Gandhi Jayanti
        date(2025, 10, 22), # Diwali Balipratipada
        date(2025, 11, 5),  # Gurunanak Jayanti
        # 2026
        date(2026, 2, 15),  # Mahashivratri
        date(2026, 3, 4),   # Holi
        date(2026, 3, 20),  # Id-Ul-Fitr
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 27),  # Bakri Id
        date(2026, 6, 26),  # Muharram
        date(2026, 10, 20), # Dussehra
        date(2026, 11, 8),  # Diwali
        date(2026, 11, 24), # Gurunanak Jayanti
        # 2027
        date(2027, 3, 6),   # Mahashivratri
        date(2027, 3, 23),  # Holi
        date(2027, 3, 26),  # Good Friday
        date(2027, 10, 9),  # Dussehra
        date(2027, 10, 29), # Diwali
    }

    @classmethod
    def get_market_type(cls, symbol: str) -> MarketType:
        """Classify symbol into its corresponding financial market."""
        sym = symbol.upper().strip()
        # Precious Metals (Gold / Silver)
        if (
            sym in ("XAU/USD", "XAG/USD", "XAU-USD", "XAG-USD", "XAUUSD", "XAGUSD", "XAU", "XAG", "GC=F", "SI=F", "GOLD", "SILVER")
            or sym.startswith("XAU")
            or sym.startswith("XAG")
            or "=F" in sym
        ):
            return MarketType.METALS
        if "-USD" in sym or "/USD" in sym or sym.endswith("USDT") or sym in (
            "BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "DOGE-USD", "BNB-USD", "XRP-USD", "ADA-USD"
        ):
            return MarketType.CRYPTO
        if sym.endswith(".NS") or sym.endswith(".BO") or ".NS" in sym or ".BO" in sym:
            return MarketType.INDIA_EQUITY
        return MarketType.US_EQUITY

    @classmethod
    def get_us_holidays(cls, year: int) -> Dict[date, str]:
        """Compute all official NYSE holiday closures for a given year."""
        holidays: Dict[date, str] = {}

        # 1. New Year's Day (Jan 1)
        nyd = date(year, 1, 1)
        if nyd.weekday() == 6:  # Sunday -> observed Monday Jan 2
            holidays[date(year, 1, 2)] = "New Year's Day (Observed)"
        elif nyd.weekday() != 5:  # If Saturday, not observed by NYSE on Friday
            holidays[nyd] = "New Year's Day"

        # 2. Martin Luther King Jr. Day (3rd Monday in January)
        holidays[get_nth_weekday_of_month(year, 1, 0, 3)] = "Martin Luther King Jr. Day"

        # 3. Washington's Birthday / Presidents' Day (3rd Monday in February)
        holidays[get_nth_weekday_of_month(year, 2, 0, 3)] = "Presidents' Day"

        # 4. Good Friday (Friday before Easter Sunday)
        easter = get_easter_date(year)
        good_friday = easter - timedelta(days=2)
        holidays[good_friday] = "Good Friday"

        # 5. Memorial Day (Last Monday in May)
        holidays[get_nth_weekday_of_month(year, 5, 0, -1)] = "Memorial Day"

        # 6. Juneteenth National Independence Day (June 19)
        june19 = date(year, 6, 19)
        if june19.weekday() == 6:
            holidays[date(year, 6, 20)] = "Juneteenth (Observed)"
        elif june19.weekday() == 5:
            holidays[date(year, 6, 18)] = "Juneteenth (Observed)"
        else:
            holidays[june19] = "Juneteenth"

        # 7. Independence Day (July 4)
        july4 = date(year, 7, 4)
        if july4.weekday() == 6:
            holidays[date(year, 7, 5)] = "Independence Day (Observed)"
        elif july4.weekday() == 5:
            holidays[date(year, 7, 3)] = "Independence Day (Observed)"
        else:
            holidays[july4] = "Independence Day"

        # 8. Labor Day (1st Monday in September)
        holidays[get_nth_weekday_of_month(year, 9, 0, 1)] = "Labor Day"

        # 9. Thanksgiving Day (4th Thursday in November)
        thanksgiving = get_nth_weekday_of_month(year, 11, 3, 4)
        holidays[thanksgiving] = "Thanksgiving Day"

        # 10. Christmas Day (Dec 25)
        xmas = date(year, 12, 25)
        if xmas.weekday() == 6:
            holidays[date(year, 12, 26)] = "Christmas Day (Observed)"
        elif xmas.weekday() == 5:
            holidays[date(year, 12, 24)] = "Christmas Day (Observed)"
        else:
            holidays[xmas] = "Christmas Day"

        return holidays

    @classmethod
    def get_us_early_close(cls, d: date) -> Optional[Tuple[time, str]]:
        """
        Check if the date is an official NYSE early close day (closes at 13:00 ET):
        - Black Friday (Day after Thanksgiving)
        - Christmas Eve (Dec 24, if weekday)
        - Day before Independence Day (July 3, if weekday)
        """
        year = d.year

        # Black Friday: day after 4th Thursday in November
        thanksgiving = get_nth_weekday_of_month(year, 11, 3, 4)
        black_friday = thanksgiving + timedelta(days=1)
        if d == black_friday:
            return (time(13, 0), "Black Friday (Early Close at 13:00 ET)")

        # July 3rd (if weekday)
        if d.month == 7 and d.day == 3 and d.weekday() < 5:
            return (time(13, 0), "Day before Independence Day (Early Close at 13:00 ET)")

        # Christmas Eve (Dec 24, if weekday)
        if d.month == 12 and d.day == 24 and d.weekday() < 5:
            return (time(13, 0), "Christmas Eve (Early Close at 13:00 ET)")

        return None

    @classmethod
    def get_indian_holidays(cls, year: int) -> Dict[date, str]:
        """Compute all official Indian NSE/BSE holiday closures for a given year."""
        holidays: Dict[date, str] = {}

        # Fixed National Holidays
        fixed = [
            (1, 26, "Republic Day"),
            (4, 14, "Dr. Ambedkar Jayanti"),
            (5, 1, "Maharashtra Day"),
            (8, 15, "Independence Day"),
            (10, 2, "Mahatma Gandhi Jayanti"),
            (12, 25, "Christmas"),
        ]
        for m, day_num, name in fixed:
            holidays[date(year, m, day_num)] = name

        # Add Good Friday dynamically
        easter = get_easter_date(year)
        good_friday = easter - timedelta(days=2)
        holidays[good_friday] = "Good Friday"

        # Merge with known religious/cultural holiday dates for that year
        for d in cls.KNOWN_INDIAN_HOLIDAYS:
            if d.year == year and d not in holidays:
                holidays[d] = "Indian Market Holiday"

        return holidays

    @classmethod
    def is_us_market_open(cls, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if the US stock market (NYSE/NASDAQ) is currently open for regular trading.
        Regular hours: Mon-Fri 09:30 - 16:00 ET (or 13:00 ET on early close days like Black Friday).
        """
        now_utc = dt or datetime.now(TZ_UTC)
        now_us = now_utc.astimezone(TZ_US)
        today = now_us.date()
        current_time = now_us.time()

        # 1. Weekend check
        if now_us.weekday() in (5, 6):  # Saturday or Sunday
            day_name = "Saturday" if now_us.weekday() == 5 else "Sunday"
            return (
                False,
                f"US Market is CLOSED for weekend ({day_name}, {now_us.strftime('%H:%M')} ET). Opens Monday 09:30 ET.",
            )

        # 2. Holiday closure check
        us_holidays = cls.get_us_holidays(today.year)
        if today in us_holidays:
            holiday_name = us_holidays[today]
            return (
                False,
                f"US Market is CLOSED for {holiday_name} ({today.strftime('%Y-%m-%d')}).",
            )

        # 3. Early close check (Black Friday, Christmas Eve, etc.)
        early_close_info = cls.get_us_early_close(today)
        market_open_time = time(9, 30)
        market_close_time = early_close_info[0] if early_close_info else time(16, 0)
        session_label = f"Special session: 09:30 - {market_close_time.strftime('%H:%M')} ET ({early_close_info[1]})" if early_close_info else "Regular session: 09:30 - 16:00 ET"

        if current_time < market_open_time:
            return (
                False,
                f"US Market is PRE-MARKET / CLOSED (Current: {now_us.strftime('%H:%M:%S')} ET). {session_label}.",
            )
        elif current_time >= market_close_time:
            reason = f"US Market is CLOSED ({early_close_info[1]} ended at {market_close_time.strftime('%H:%M')} ET)" if early_close_info else f"US Market is AFTER-HOURS / CLOSED (Closed at 16:00 ET, current: {now_us.strftime('%H:%M:%S')} ET)"
            return (False, reason)

        return (
            True,
            f"US Market is OPEN ({now_us.strftime('%H:%M:%S')} ET). Closes at {market_close_time.strftime('%H:%M')} ET.",
        )

    @classmethod
    def is_indian_market_open(cls, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if the Indian stock market (NSE/BSE) is currently open for regular trading.
        Regular hours: Mon-Fri 09:15 - 15:30 IST.
        """
        now_utc = dt or datetime.now(TZ_UTC)
        now_in = now_utc.astimezone(TZ_INDIA)
        today = now_in.date()
        current_time = now_in.time()

        # 1. Weekend check
        if now_in.weekday() in (5, 6):  # Saturday or Sunday
            day_name = "Saturday" if now_in.weekday() == 5 else "Sunday"
            return (
                False,
                f"Indian Market (NSE/BSE) is CLOSED for weekend ({day_name}, {now_in.strftime('%H:%M')} IST). Opens Monday 09:15 IST.",
            )

        # 2. Holiday check
        in_holidays = cls.get_indian_holidays(today.year)
        if today in in_holidays:
            holiday_name = in_holidays[today]
            return (
                False,
                f"Indian Market (NSE/BSE) is CLOSED for {holiday_name} ({today.strftime('%Y-%m-%d')}).",
            )

        # 3. Regular hours check (09:15 - 15:30 IST)
        market_open_time = time(9, 15)
        market_close_time = time(15, 30)

        if current_time < market_open_time:
            return (
                False,
                f"Indian Market is PRE-MARKET / CLOSED (Current: {now_in.strftime('%H:%M:%S')} IST). Opens at 09:15 IST.",
            )
        elif current_time >= market_close_time:
            return (
                False,
                f"Indian Market is POST-MARKET / CLOSED (Current: {now_in.strftime('%H:%M:%S')} IST). Closed at 15:30 IST.",
            )

        return (
            True,
            f"Indian Market is OPEN ({now_in.strftime('%H:%M:%S')} IST). Closes at 15:30 IST.",
        )

    @classmethod
    def is_crypto_market_open(cls) -> Tuple[bool, str]:
        """Crypto runs 24/7/365 with zero downtime."""
        return (True, "Crypto market operates 24/7 continuously.")

    @classmethod
    def is_metals_market_open(cls, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if CME Globex Precious Metals (Gold GC=F / Silver SI=F) is open.
        Trading Hours:
        - Sunday 18:00 ET to Friday 17:00 ET.
        - Daily 60-min maintenance pause from 17:00 to 18:00 ET (Mon-Thu).
        - Closed Friday 17:00 ET through Sunday 18:00 ET.
        """
        now_utc = dt or datetime.now(TZ_UTC)
        now_us = now_utc.astimezone(TZ_US)
        weekday = now_us.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        t = now_us.time()

        # Saturday: completely closed
        if weekday == 5:
            return (False, f"Metals market (CME/Globex Gold & Silver) is CLOSED on Saturdays ({now_us.strftime('%H:%M')} ET). Opens Sunday 18:00 ET.")

        # Sunday: closed before 18:00 ET, opens at 18:00 ET
        if weekday == 6:
            if t < time(18, 0):
                return (False, f"Metals market is CLOSED on Sundays until 18:00 ET (Current: {now_us.strftime('%H:%M:%S')} ET).")
            return (True, f"Metals market is OPEN (Sunday evening session, {now_us.strftime('%H:%M:%S')} ET).")

        # Friday: closes at 17:00 ET
        if weekday == 4:
            if t >= time(17, 0):
                return (False, f"Metals market CLOSED for the weekend at 17:00 ET (Current: {now_us.strftime('%H:%M:%S')} ET). Opens Sunday 18:00 ET.")
            return (True, f"Metals market is OPEN (Friday session, {now_us.strftime('%H:%M:%S')} ET). Closes at 17:00 ET.")

        # Mon-Thu: daily maintenance break 17:00 to 18:00 ET
        if time(17, 0) <= t < time(18, 0):
            return (False, f"Metals market daily maintenance pause (17:00-18:00 ET). Reopens at 18:00 ET (Current: {now_us.strftime('%H:%M:%S')} ET).")

        return (True, f"Metals market is OPEN (CME/Globex Gold & Silver: {now_us.strftime('%H:%M:%S')} ET).")

    @classmethod
    def is_market_open(cls, symbol: str, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """Determine whether the market for a specific symbol is open right now."""
        mtype = cls.get_market_type(symbol)
        if mtype == MarketType.CRYPTO:
            return cls.is_crypto_market_open()
        elif mtype == MarketType.METALS:
            return cls.is_metals_market_open(dt)
        elif mtype == MarketType.INDIA_EQUITY:
            return cls.is_indian_market_open(dt)
        else:
            return cls.is_us_market_open(dt)

    @classmethod
    def filter_open_symbols(cls, symbols: List[str], dt: Optional[datetime] = None) -> List[str]:
        """
        Filter a list of multi-market symbols, returning ONLY those whose market is currently open.
        Guarantees that during Indian hours, Indian stocks trade; during US hours, US stocks trade;
        Metals trade 23h/day Mon-Fri; and Crypto trades 24/7.
        """
        open_symbols: List[str] = []
        for sym in symbols:
            is_open, _ = cls.is_market_open(sym, dt=dt)
            if is_open:
                open_symbols.append(sym)
        return open_symbols

    @classmethod
    def get_open_markets_summary(cls, dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Provide a real-time status summary across all market domains."""
        now_utc = dt or datetime.now(TZ_UTC)
        us_open, us_msg = cls.is_us_market_open(now_utc)
        in_open, in_msg = cls.is_indian_market_open(now_utc)
        crypto_open, crypto_msg = cls.is_crypto_market_open()
        metals_open, metals_msg = cls.is_metals_market_open(now_utc)

        now_us = now_utc.astimezone(TZ_US)
        now_in = now_utc.astimezone(TZ_INDIA)

        return {
            "timestamp_utc": now_utc.isoformat(),
            "us_market": {
                "open": us_open,
                "current_time": now_us.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "status": us_msg,
            },
            "indian_market": {
                "open": in_open,
                "current_time": now_in.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "status": in_msg,
            },
            "crypto_market": {
                "open": crypto_open,
                "status": crypto_msg,
            },
            "metals_market": {
                "open": metals_open,
                "current_time": now_us.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "status": metals_msg,
            },
        }
