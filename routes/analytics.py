from datetime import date
from flask import Blueprint, jsonify, render_template, request

from services.analytics import (
    cash_flow_waterfall,
    category_comparison_and_pareto,
    generate_ai_review,
    generate_smart_insights,
    goals_analytics,
    health_metrics,
    six_months_trends,
)
from services.dates import period_bounds, period_caption
from services.debts import get_friends_money_card

bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@bp.route("/")
def index():
    ref = date.today()
    start_m, end_m = period_bounds("month", ref)

    # J7: Переключатель «Моя доля / Всего списано»
    mode = request.args.get("mode", "own")
    is_net = (mode != "gross")

    hm = health_metrics(start_m, end_m, ref)
    cf = cash_flow_waterfall(start_m, end_m)
    trends = six_months_trends(ref)
    shifts = category_comparison_and_pareto(ref, net=is_net)
    goals = goals_analytics(ref)
    insights = generate_smart_insights(ref)
    ai_rev = generate_ai_review(ref)
    friends_card = get_friends_money_card()

    return render_template(
        "analytics.html",
        ref_date=ref,
        period_caption=period_caption("month", ref),
        mode=mode,
        is_net=is_net,
        health=hm,
        waterfall=cf,
        trends=trends,
        shifts=shifts,
        goals=goals,
        insights=insights,
        ai_review=ai_rev,
        friends_card=friends_card,
    )


@bp.route("/refresh-ai", methods=["POST"])
def refresh_ai():
    try:
        ref = date.today()
        rev = generate_ai_review(ref)
        return jsonify({
            "success": True,
            "text": rev["text"],
            "model": rev.get("model", "AI"),
            "is_ai_live": rev["is_ai_live"],
            "error_hint": rev.get("error_hint"),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
