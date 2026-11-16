"""Conservative cost model for Binance USDT-M BTCUSDT perpetual (VIP0, no BNB discount).

All numbers are fractions of notional per side.
  taker fee   5.0 bps  (Binance VIP0 taker 0.05%)
  maker fee   2.0 bps  (Binance VIP0 maker 0.02%)
  market-order slippage 1.0 bp per side (BTCUSDT perp spread is 1 tick = $0.10, i.e. <0.05 bp at
      2020+ prices; 1 bp covers half-spread, latency and small impact for retail size)
  stop-order slippage 2.0 bps beyond the stop price, in addition to gap-through (fill at the bar
      open if the bar opens beyond the stop)
  limit orders: maker fee, zero slippage, but only filled when price trades THROUGH the level
Funding: realised funding rates at their real timestamps, applied to notional while a position is open.
`mult` scales fees and slippage (1.5 = stress test). Funding is real data and is not scaled.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Costs:
    taker: float = 5.0e-4
    maker: float = 2.0e-4
    slip_mkt: float = 1.0e-4
    slip_stop: float = 2.0e-4
    mult: float = 1.0

    def scaled(self, mult: float) -> "Costs":
        return Costs(self.taker, self.maker, self.slip_mkt, self.slip_stop, mult)

    @property
    def rt_market(self) -> float:
        """Round-trip cost of market-in / market-out (fraction of notional)."""
        return 2 * (self.taker + self.slip_mkt) * self.mult


BASE = Costs()
TICK = 0.1  # BTCUSDT perp tick size in USDT
MAX_LEVERAGE = 5.0
RISK_PER_TRADE = 0.01
