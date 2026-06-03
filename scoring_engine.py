class ScoringEngine:

    def edge_score(self, score, rr, rs_score, volume_spike, breakout, regime):
        if score < 60:
            return 0

        edge = 0

        if score >= 80:
            edge += 5
        elif score >= 70:
            edge += 3

        if rr >= 3:
            edge += 2

        if rs_score >= 50:
            edge += 2

        if volume_spike >= 1.5 and breakout == "YES":
            edge += 2

        return min(edge * 10, 100)

    def rating(self, edge_score):
        return min(edge_score // 10, 9)

    def action(self, rating):
        if rating >= 8:
            return "STRONG_BUY"
        elif rating >= 7:
            return "BUY"
        elif rating >= 6:
            return "WATCH"
        elif rating >= 4:
            return "IGNORE_WATCH"
        return "IGNORE"
