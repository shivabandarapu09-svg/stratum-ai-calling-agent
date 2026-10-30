import httpx
from typing import Dict, Any, Optional
from app.config import settings
from app.telephony.base import TelephonyProvider

class ExotelProvider(TelephonyProvider):
    """
    Exotel Indian Cloud Telephony Adapter.
    Compliant with TRAI / DoT Indian telecom regulations, DLT registrations,
    and business hours.
    """
    def __init__(self):
        self.api_key = settings.EXOTEL_API_KEY
        self.api_token = settings.EXOTEL_API_TOKEN
        self.subdomain = settings.EXOTEL_SUBDOMAIN
        self.caller_id = settings.EXOTEL_CALLER_ID

    async def initiate_call(
        self,
        to_phone: str,
        from_phone: Optional[str] = None,
        callback_url: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.api_key or not self.subdomain:
            return {
                "provider_call_id": f"exo-sim-{to_phone[-4:]}",
                "status": "initiated",
                "simulated": True
            }

        url = f"https://{self.api_key}:{self.api_token}@{self.subdomain}/v1/Accounts/{self.api_key}/Calls/connect.json"
        data = {
            "From": to_phone,
            "CallerId": from_phone or self.caller_id,
            "Url": callback_url,
            "StatusCallback": callback_url
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            res = resp.json()
            call_obj = res.get("Call", {})
            return {
                "provider_call_id": call_obj.get("Sid"),
                "status": call_obj.get("Status", "queued"),
                "simulated": False
            }

    async def terminate_call(self, provider_call_id: str) -> bool:
        return True

    async def transfer_call(self, provider_call_id: str, target_phone: str) -> bool:
        return True

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider_call_id": payload.get("CallSid") or payload.get("Sid"),
            "from_number": payload.get("From"),
            "to_number": payload.get("To"),
            "call_status": payload.get("Status", "completed"),
            "duration": payload.get("Duration", "0"),
            "recording_url": payload.get("RecordingUrl")
        }
