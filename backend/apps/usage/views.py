from asgiref.sync import async_to_sync
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import check_quota


class MyUsageView(APIView):
    def get(self, request):
        q = async_to_sync(check_quota)(request.user)
        return Response({
            "allowed": q.allowed,
            "reason": q.reason,
            "tokens_last_24h": q.tokens_today,
            "daily_token_limit": q.daily_token_limit,
            "cost_this_month_usd": str(q.cost_this_month),
            "monthly_cost_limit_usd": str(q.monthly_cost_limit),
        })
