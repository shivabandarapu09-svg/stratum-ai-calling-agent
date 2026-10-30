import uuid
from typing import Dict, Any, Optional
from app.telephony.base import TelephonyProvider

class WebSimulatorTelephonyProvider(TelephonyProvider):
    """
    Browser-based simulated telephony provider.
    Allows testing full voice calls directly inside the web dashboard.
    """

    async def initiate_call(
        self,
        to_phone: str,
        from_phone: str = "+910000000000",
        callback_url: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return {
            "provider_call_id": f"sim-{uuid.uuid4().hex[:8]}",
            "status": "ringing",
            "simulated": True,
            "to_phone": to_phone,
            "from_phone": from_phone
        }

    async def terminate_call(self, provider_call_id: str) -> bool:
        return True

    async def transfer_call(self, provider_call_id: str, target_phone: str) -> bool:
        return True

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload

def get_telephony_provider(name: Optional[str] = None) -> TelephonyProvider:
    if name == "twilio":
        from app.telephony.twilio_provider import TwilioProvider
        return TwilioProvider()
    if name == "exotel":
        from app.telephony.exotel_provider import ExotelProvider
        return ExotelProvider()
    return WebSimulatorTelephonyProvider()
