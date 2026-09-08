"""
Smart order routing and execution engine.

Implements latency-adaptive execution with:
- TWAP scheduling augmented with stochastic noise
- Real-time venue scoring based on depth, fill rates, and fees
- Automatic buffer widening during network congestion
- Slippage control as a first-order risk constraint
"""

from typing import Dict, Any, Optional, List
import numpy as np

from ..config import Config


class ExecutionEngine:
    """
    Smart order routing and execution engine.
    
    Routes orders to optimal venues while minimizing market impact
    and adapting to network conditions.
    """
    
    def __init__(self, config: Config):
        """
        Initialize execution engine.
        
        Args:
            config: Configuration object with execution parameters
        """
        self.config = config
        
        # TWAP parameters
        self.twap_slices = config.execution.twap_slices
        self.stochastic_noise_std = config.execution.stochastic_noise_std
        
        # Latency monitoring
        self._latency_history: Dict[str, list] = {}
        self._venue_stats: Dict[str, dict] = {}
        
        # Initialize venue statistics
        self._initialize_venues()
        
    def _initialize_venues(self) -> None:
        """Initialize venue tracking."""
        # Simulated venues with different characteristics
        self._venues = [
            {"id": "VENUE_A", "type": "equity", "latency_ms": 0.5},
            {"id": "VENUE_B", "type": "crypto", "latency_ms": 2.0},
            {"id": "VENUE_C", "type": "futures", "latency_ms": 1.0},
        ]
        
        for venue in self._venues:
            vid = venue["id"]
            self._venue_stats[vid] = {
                "depth_score": 0.8,
                "fill_rate": 0.95,
                "fee_tier": 0.0002,
                "recent_latency": []
            }
            
    def route(
        self,
        portfolio: Dict[str, float],
        state: Any
    ) -> List[Dict[str, Any]]:
        """
        Route orders to venues.
        
        Args:
            portfolio: Target positions
            state: Current market state
            
        Returns:
            List of order dictionaries
        """
        if not portfolio:
            return []
            
        orders = []
        
        for inst_id, target_position in portfolio.items():
            current_position = state.positions.get(inst_id, 0.0)
            quantity = target_position - current_position
            
            if abs(quantity) < 1e-6:
                continue
                
            # Slice order using TWAP with stochastic noise
            slices = self._create_twap_slices(inst_id, quantity)
            
            # Route each slice to optimal venue
            for slice_qty in slices:
                best_venue = self._select_best_venue(inst_id, abs(slice_qty))
                
                order = {
                    "instrument_id": inst_id,
                    "action": "BUY" if slice_qty > 0 else "SELL",
                    "quantity": abs(slice_qty),
                    "order_type": "LIMIT",
                    "venue": best_venue,
                    "slice_id": len(orders),
                    "total_slices": len(slices)
                }
                orders.append(order)
                
        return orders
    
    def _create_twap_slices(
        self,
        instrument_id: str,
        total_quantity: float
    ) -> List[float]:
        """
        Create TWAP slices with stochastic noise.
        
        Args:
            instrument_id: Instrument identifier
            total_quantity: Total quantity to execute
            
        Returns:
            List of slice quantities
        """
        n_slices = self.twap_slices
        base_slice = total_quantity / n_slices
        
        slices = []
        remaining = total_quantity
        
        for i in range(n_slices - 1):
            # Add stochastic noise to slice size and timing
            noise = np.random.normal(0, self.stochastic_noise_std)
            slice_qty = base_slice * (1 + noise)
            
            # Ensure we don't exceed remaining
            slice_qty = np.sign(slice_qty) * min(abs(slice_qty), abs(remaining))
            
            slices.append(slice_qty)
            remaining -= slice_qty
            
        # Last slice takes remaining
        slices.append(remaining)
        
        return slices
    
    def _select_best_venue(
        self,
        instrument_id: str,
        quantity: float
    ) -> str:
        """
        Select best venue for order.
        
        Scores venues based on:
        - Top-of-book depth
        - Recent fill rates
        - Fee tiers
        
        Args:
            instrument_id: Instrument identifier
            quantity: Order quantity
            
        Returns:
            Best venue ID
        """
        weights = self.config.execution.venue_score_weights
        
        best_score = -np.inf
        best_venue = self._venues[0]["id"]
        
        for venue in self._venues:
            vid = venue["id"]
            stats = self._venue_stats[vid]
            
            # Calculate venue score
            depth_score = stats["depth_score"]
            fill_score = stats["fill_rate"]
            fee_score = 1.0 - stats["fee_tier"] * 1000  # Normalize fees
            
            score = (
                weights["depth"] * depth_score +
                weights["fill_rate"] * fill_score +
                weights["fees"] * fee_score
            )
            
            # Adjust for latency if above threshold
            if self._is_latency_elevated(vid):
                score *= 0.8  # Penalty for elevated latency
                
            if score > best_score:
                best_score = score
                best_venue = vid
                
        return best_venue
    
    def _is_latency_elevated(self, venue_id: str) -> bool:
        """
        Check if venue latency is elevated.
        
        Args:
            venue_id: Venue identifier
            
        Returns:
            True if latency exceeds 2 std from median
        """
        if venue_id not in self._venue_stats:
            return False
            
        latencies = self._venue_stats[venue_id]["recent_latency"]
        
        if len(latencies) < 10:
            return False
            
        median_lat = np.median(latencies)
        std_lat = np.std(latencies)
        
        threshold = median_lat + self.config.execution.latency_jitter_threshold_std * std_lat
        
        return latencies[-1] > threshold if latencies else False
    
    def update_venue_stats(
        self,
        venue_id: str,
        depth: float,
        fill_rate: float,
        latency_ms: float
    ) -> None:
        """
        Update venue statistics.
        
        Args:
            venue_id: Venue identifier
            depth: Current depth score
            fill_rate: Recent fill rate
            latency_ms: Measured latency in milliseconds
        """
        if venue_id not in self._venue_stats:
            return
            
        stats = self._venue_stats[venue_id]
        stats["depth_score"] = depth
        stats["fill_rate"] = fill_rate
        
        # Track latency history
        stats["recent_latency"].append(latency_ms)
        if len(stats["recent_latency"]) > 100:
            stats["recent_latency"].pop(0)
            
    def get_execution_quality_report(self) -> dict:
        """
        Generate execution quality report.
        
        Returns:
            Dictionary with execution metrics
        """
        report = {
            "venues": {},
            "average_latency_ms": 0.0,
            "elevated_latency_venues": []
        }
        
        all_latencies = []
        
        for vid, stats in self._venue_stats.items():
            latencies = stats["recent_latency"]
            avg_lat = np.mean(latencies) if latencies else 0.0
            all_latencies.extend(latencies)
            
            is_elevated = self._is_latency_elevated(vid)
            if is_elevated:
                report["elevated_latency_venues"].append(vid)
                
            report["venues"][vid] = {
                "avg_latency_ms": avg_lat,
                "fill_rate": stats["fill_rate"],
                "depth_score": stats["depth_score"],
                "fee_tier": stats["fee_tier"]
            }
            
        if all_latencies:
            report["average_latency_ms"] = np.mean(all_latencies)
            
        return report
    
    def widen_buffers(self, venue_id: str) -> float:
        """
        Widen limit order buffers during network congestion.
        
        Args:
            venue_id: Venue identifier
            
        Returns:
            Buffer width in basis points
        """
        # Base buffer
        buffer_bp = 5.0
        
        # Increase if latency elevated
        if self._is_latency_elevated(venue_id):
            buffer_bp *= 2.0
            
        return buffer_bp
