from typing import Optional, Tuple
from app.services.billing.plan_definitions import get_plan_entitlements, PlanEntitlements


class EntitlementService:
    """
    Backend Feature Gating & Entitlement Enforcer (Phase U23).
    Ensures users cannot bypass feature tier limits directly through API requests.
    """

    @classmethod
    def check_feature_access(
        cls,
        plan_tier: str,
        feature_key: str,
        current_count: int = 0
    ) -> Tuple[bool, Optional[str]]:
        plan = get_plan_entitlements(plan_tier)

        if feature_key == "deep_research":
            if current_count >= plan.deep_research_limit:
                return (False, f"Đã sử dụng hết {plan.deep_research_limit} lượt Deep Research tháng này của gói {plan.name}.")

        elif feature_key == "premium_models":
            if not plan.premium_models:
                return (False, "Các mô hình AI nâng cao (Claude 3.5 Sonnet / Gemini Pro) yêu cầu gói Pro trở lên.")

        elif feature_key == "export_format":
            # format checked separately
            pass

        elif feature_key == "projects":
            if current_count >= plan.projects_limit:
                return (False, f"Đã đạt giới hạn tối đa {plan.projects_limit} dự án của gói {plan.name}.")

        return (True, None)

    @classmethod
    def is_export_format_allowed(cls, plan_tier: str, format_ext: str) -> bool:
        plan = get_plan_entitlements(plan_tier)
        return format_ext.lower().lstrip(".") in plan.allowed_export_formats


entitlement_service = EntitlementService()
