from typing import Any, Dict, List

from loguru import logger

from docmirror.models.entities.parse_result import ParseResult


class AnomalyDetectorMiddleware:
    """
    Validation Layer Middleware for zero-LLM fast extraction.
    Intercepts the ParseResult and applies strict structural assertions.
    If the document fails validation (e.g. layout collapse), it is tagged for VLM fallback.
    """

    # Keys that absolutely must exist in a valid credit account section.
    CRITICAL_ACCOUNT_KEYS = {"开立日期", "借款金额", "管理机构"}

    def __init__(self):
        self.dlq_registry: list[dict[str, Any]] = []

    async def process(self, parse_result: ParseResult, **kwargs) -> ParseResult:
        """Evaluate the extracted entities and tag with metadata if anomalies detected."""
        if not parse_result.entities or not parse_result.entities.domain_specific:
            return parse_result

        domain_data = parse_result.entities.domain_specific

        # 1. Analyze Credit Account Sections
        credit_cards = domain_data.get("credit_accounts", [])
        if credit_cards:
            anomaly_count = 0
            for card in credit_cards:
                # If an account is missing 2 or more of the 3 fundamental keys, it's garbage text
                missing = [k for k in self.CRITICAL_ACCOUNT_KEYS if not card.get(k)]
                if len(missing) >= 2:
                    anomaly_count += 1

            failure_rate = anomaly_count / max(len(credit_cards), 1)

            # If > 30% of accounts are fundamentally broken, we assume a total layout shift failure
            if failure_rate > 0.3:
                logger.error(
                    f"AnomalyDetector: {failure_rate*100:.1f}% cards structurally collapsed. "
                    "Routing document to VLM Fallback DLQ."
                )

                # Flag the payload up to the Router
                if parse_result.errors is None:
                    parse_result.errors = []
                parse_result.errors.append("REQUIRES_VLM_FALLBACK")

                self._route_to_dlq(parse_result, f"Credit extraction collapse (failure rate {failure_rate})")

        return parse_result

    def _route_to_dlq(self, parse_result: ParseResult, reason: str):
        """
        Record the failure event so the asynchronous Orchestrator can pull this
        PDF to be processed by a heavyweight Vision Language Model.
        """
        self.dlq_registry.append({
            "page_count": len(parse_result.pages),
            "reason": reason
        })
