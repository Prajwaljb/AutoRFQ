"""Part B, the RFQ Quality Agent: runs inside the flow after the lookups.

1. units.py   puts every measurement in one standard unit (deterministic).
2. rules.py   flags missing or odd values; rule flags alone decide the status.
3. llm.py     optional Azure OpenAI review: advisory suggestions, never changes a value or the status.
4. summary.py the Summary sheet (fill rate, request lines, alerts, flags, AI suggestions).
"""
from rfq.models import RunStatus
from rfq.quality import llm, rules, units


def run(result, logger=None, events=None, use_llm=True):
    """Normalises units, flags values and sets result.status (ready / needs_review)."""
    for item in result.items:
        if item.found:
            result.units_converted += units.normalise(item, result)
    result.flags = rules.check(result)
    if events is not None:
        for flag in (f for f in result.flags if f.severity != "low"):
            events.emit("quality_flag", product_id=flag.product_id, column=flag.column, rule=flag.rule,
                        severity=flag.severity)
    if use_llm:
        result.ai_suggestions, result.ai_status = llm.review(result, logger)
    else:
        result.ai_suggestions, result.ai_status = [], "LLM check turned off"
    result.quality_ran = True
    result.status = status_of(result)
    return result


def status_of(result):
    """Needs human review while any high-severity rule flag is open. AI suggestions never count."""
    if any(f.severity == "high" and not f.resolved for f in result.flags):
        return RunStatus.NEEDS_REVIEW
    return RunStatus.READY
