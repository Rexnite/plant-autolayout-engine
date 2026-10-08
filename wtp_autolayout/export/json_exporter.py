"""JSON export utilities."""

from pathlib import Path

from wtp_autolayout.utils.serialization import to_json


class JSONExporter:
    """Export layouts and optimization runtime results to JSON."""

    def export_layout(self, layout, output_path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_json(layout, indent=2), encoding="utf-8")
        return str(path)

    def export_optimization_result(self, result, output_path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = result
        if hasattr(result, "__dict__"):
            data = {
                "best_layout": result.best_layout.to_dict() if result.best_layout else None,
                "best_score_result": result.best_score_result.to_dict() if result.best_score_result else None,
                "candidate_results": [
                    {
                        "layout": candidate.layout.to_dict(),
                        "scoring_result": candidate.scoring_result.to_dict(),
                        "rank": candidate.rank,
                    }
                    for candidate in result.candidate_results
                ],
                "algorithm": result.algorithm,
                "iterations": result.iterations,
                "runtime_seconds": result.runtime_seconds,
                "status": result.status.value,
                "metadata": result.metadata,
            }
        path.write_text(to_json(data, indent=2), encoding="utf-8")
        return str(path)
