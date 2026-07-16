"""
Jessie — backend/agents/code_reviewer/scorer.py
Calculates weighted scores for each review layer and overall project grade.
"""

FRONTEND_WEIGHTS = {
    "security":          0.20,
    "performance":       0.15,
    "accessibility":     0.10,
    "structure":         0.15,
    "hardcoded_config":  0.15,
    "dead_code":         0.10,
    "advanced_flows":    0.15,
}

BACKEND_WEIGHTS = {
    "security":          0.20,
    "performance":       0.10,
    "error_handling":    0.10,
    "api_design":        0.10,
    "structure":         0.15,
    "hardcoded_config":  0.15,
    "dead_code":         0.10,
    "advanced_flows":    0.10,
}

DB_WEIGHTS = {
    "security":          0.20,
    "performance":       0.15,
    "schema_design":     0.15,
    "migrations":        0.10,
    "transactions":      0.10,
    "hardcoded_config":  0.10,
    "dead_code":         0.10,
    "advanced_flows":    0.10,
}

# sort key for get_priority_fixes — lower = run first
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_DOMAIN_RANK = {
    "security": 0,
    "advanced_flows": 1,
    "hardcoded_config": 1,
    "performance": 2,
    "error_handling": 2,
    "structure": 2,
    "schema_design": 2,
    "api_design": 3,
    "accessibility": 3,
    "dead_code": 3,
    "migrations": 3,
    "transactions": 3,
    # legacy category names (older reports)
    "architecture": 2,
    "typescript_quality": 3,
    "code_quality": 3,
}


def _grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


class ReviewScorer:

    def calculate_scores(
        self,
        frontend_results: dict,
        backend_results:  dict,
        db_results:       dict,
    ) -> dict:
        """
        Compute per-layer and overall weighted scores.
        Returns a single dict used by MarkdownReporter.
        """
        fe_score = self._layer_score(frontend_results, FRONTEND_WEIGHTS)
        be_score = self._layer_score(backend_results,  BACKEND_WEIGHTS)
        db_score = self._layer_score(db_results,       DB_WEIGHTS)

        has_fe = bool(frontend_results.get("categories"))
        has_be = bool(backend_results.get("categories"))
        has_db = bool(db_results.get("categories"))

        # Overall: weighted by layer presence
        if has_fe and has_be and has_db:
            overall = round(fe_score * 0.35 + be_score * 0.40 + db_score * 0.25)
        elif has_fe and has_be:
            overall = round(fe_score * 0.45 + be_score * 0.55)
        elif has_be and has_db:
            overall = round(be_score * 0.60 + db_score * 0.40)
        elif has_be:
            overall = be_score
        elif has_fe:
            overall = fe_score
        elif has_db:
            overall = db_score
        else:
            overall = 0

        all_issues = self._flatten_issues(frontend_results, backend_results, db_results)
        fe_issues  = self._flatten_issues(frontend_results)
        be_issues  = self._flatten_issues(backend_results)
        db_issues  = self._flatten_issues(db_results)

        return {
            "overall": overall,
            "grade":   _grade(overall),
            "frontend": {
                "score":           fe_score,
                "grade":           _grade(fe_score),
                "issue_count":     len(fe_issues),
                "severity_counts": self._sev_counts(fe_issues),
                "categories":      self._cat_breakdown(frontend_results),
            },
            "backend": {
                "score":           be_score,
                "grade":           _grade(be_score),
                "issue_count":     len(be_issues),
                "severity_counts": self._sev_counts(be_issues),
                "categories":      self._cat_breakdown(backend_results),
            },
            "database": {
                "score":           db_score,
                "grade":           _grade(db_score),
                "issue_count":     len(db_issues),
                "severity_counts": self._sev_counts(db_issues),
                "categories":      self._cat_breakdown(db_results),
            },
            "total_issues":    len(all_issues),
            "severity_counts": self._sev_counts(all_issues),
            "priority_fixes":  self.get_priority_fixes(all_issues),
            "has_frontend":    has_fe,
            "has_backend":     has_be,
            "has_database":    has_db,
        }

    def get_priority_fixes(self, all_issues: list) -> list:
        """Top 5 issues: critical first, then by domain (security before others)."""
        def _key(issue):
            return (
                _SEVERITY_RANK.get(issue.get("severity", "low"), 3),
                _DOMAIN_RANK.get(issue.get("_category", ""), 9),
            )
        return sorted(all_issues, key=_key)[:5]

    # ── Private ────────────────────────────────────────────────────────────

    def _layer_score(self, results: dict, weights: dict) -> int:
        cats = results.get("categories", {})
        if not cats:
            return 0
        total_w, total_s = 0.0, 0.0
        for cat, w in weights.items():
            data = cats.get(cat)
            if data:
                total_s += data.get("score", 50) * w
                total_w += w
        return round(total_s / total_w) if total_w else 0

    def _cat_breakdown(self, results: dict) -> dict:
        breakdown = {}
        for cat, data in results.get("categories", {}).items():
            issues = data.get("issues", [])
            breakdown[cat] = {
                "score":       data.get("score", 0),
                "grade":       _grade(data.get("score", 0)),
                "issues":      issues,
                "issue_count": len(issues),
            }
        return breakdown

    def _flatten_issues(self, *results_dicts) -> list:
        issues = []
        for r in results_dicts:
            for cat, data in r.get("categories", {}).items():
                for iss in data.get("issues", []):
                    issues.append({**iss, "_category": cat})
        return issues

    def _sev_counts(self, issues: list) -> dict:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for iss in issues:
            sev = iss.get("severity", "low")
            if sev in counts:
                counts[sev] += 1
        return counts
