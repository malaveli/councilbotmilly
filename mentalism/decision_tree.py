class MentalistDecisionTree:
    """Core logic for determining whether a trade setup qualifies"""
    def __init__(self, bias, liquidity_sweep, delta_confirmation, time_window_ok=True):
        self.bias = bias
        self.liquidity_sweep = liquidity_sweep
        self.delta_confirmation = delta_confirmation
        self.time_window_ok = time_window_ok

    def evaluate(self):
        if not self.bias:
            return {"valid_setup": False, "reason": "Bias not defined"}
        if not self.liquidity_sweep:
            return {"valid_setup": False, "reason": "No liquidity sweep detected"}
        if not self.delta_confirmation:
            return {"valid_setup": False, "reason": "No delta confirmation present"}
        if not self.time_window_ok:
            return {"valid_setup": False, "reason": "Invalid time window"}
        return {
            "valid_setup": True,
            "bias": self.bias,
            "confidence_score": 0.92,
            "reason": "All Mentalist filters aligned",
        }
