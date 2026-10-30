import httpx
from typing import Dict, Any, Optional
from app.config import settings
from app.telephony.base import TelephonyProvider

class TwilioProvider(TelephonyProvider):
    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_phone: Optional[str] = None
    ):
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.default_from_phone = from_phone or settings.TWILIO_PHONE_NUMBER
        self.api_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json" if self.account_sid else ""

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.default_from_phone)

    TRIAL_DEMO_VOICE_URL = "http://demo.twilio.com/docs/voice.xml"

    async def initiate_call(
        self,
        to_phone: str,
        from_phone: Optional[str] = None,
        callback_url: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise ValueError(
                "Twilio is not configured. Please provide your Twilio Account SID, Auth Token, "
                "and Twilio Phone Number in the Settings or Real Phone Call setup dialog."
            )

        # Always prioritize the configured Twilio caller number over agent transfer numbers
        caller = self.default_from_phone or from_phone
        meta = metadata or {}
        trial_mode = bool(meta.get("twilio_trial_mode", False))
        status_callback_url = str(meta.get("status_callback_url", "") or "").strip()

        if trial_mode:
            target_url = self.TRIAL_DEMO_VOICE_URL
        elif callback_url and (callback_url.startswith("http://") or callback_url.startswith("https://")):
            target_url = callback_url
        else:
            raise ValueError(
                "A Public Webhook URL / PUBLIC_BASE_URL (https://...) is required for two-way PSTN AI conversations so Twilio can "
                "connect answered calls to the Stratum AI voice engine (/api/telephony/twilio/twiml/{call_id}). "
                "Please configure PUBLIC_BASE_URL or PUBLIC_WEBHOOK_URL in Settings or Integrations (e.g. via ngrok or Cloudflare Tunnel), "
                "or explicitly select 'Twilio Trial-Compatible Test Call' if you only want to test static trial ringing."
            )

        data: Dict[str, Any] = {
            "To": to_phone,
            "From": caller,
            "Url": target_url,
        }
        if not trial_mode and status_callback_url.startswith(("http://", "https://")):
            data["StatusCallback"] = status_callback_url

        async with httpx.AsyncClient(auth=(self.account_sid, self.auth_token)) as client:
            resp = await client.post(self.api_url, data=data)
            if resp.status_code >= 400:
                error_msg = resp.text
                error_code = None
                more_info = None
                try:
                    error_json = resp.json()
                    error_msg = error_json.get("message", error_msg)
                    error_code = error_json.get("code")
                    more_info = error_json.get("more_info")
                except Exception:
                    pass

                param_keys = list(data.keys())
                code_str = f" [Code {error_code}]" if error_code else ""
                info_str = f" (More info: {more_info})" if more_info else ""
                trial_hint = ""
                if "trial" in error_msg.lower() or error_code in (21215, 21219, 10002, 21606):
                    trial_hint = (
                        " | Trial Account Note: Verify that 'To' is in your Twilio Verified Caller IDs, "
                        "'From' is your assigned Twilio trial number, and use Trial-Compatible Test Call "
                        "(or upgrade your Twilio account for live bidirectional AI WebSocket streaming)."
                    )
                raise RuntimeError(
                    f"Twilio API Error ({resp.status_code}){code_str}: {error_msg}{info_str} "
                    f"[Params sent: {param_keys}]{trial_hint}"
                )

            res = resp.json()
            return {
                "provider_call_id": res.get("sid"),
                "status": res.get("status", "queued"),
                "simulated": False,
                "trial_compatible_url_used": target_url == self.TRIAL_DEMO_VOICE_URL,
            }

    async def terminate_call(self, provider_call_id: str) -> bool:
        if not self.is_configured() or "sim" in provider_call_id:
            return True

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls/{provider_call_id}.json"
        async with httpx.AsyncClient(auth=(self.account_sid, self.auth_token)) as client:
            resp = await client.post(url, data={"Status": "completed"})
            return resp.status_code == 200

    async def transfer_call(self, provider_call_id: str, target_phone: str) -> bool:
        if not self.is_configured() or "sim" in provider_call_id:
            return True

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls/{provider_call_id}.json"
        twiml = f"<Response><Dial>{target_phone}</Dial></Response>"
        async with httpx.AsyncClient(auth=(self.account_sid, self.auth_token)) as client:
            resp = await client.post(url, data={"Twiml": twiml})
            return resp.status_code == 200

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider_call_id": payload.get("CallSid"),
            "from_number": payload.get("From"),
            "to_number": payload.get("To"),
            "call_status": payload.get("CallStatus", "in-progress"),
            "duration": payload.get("CallDuration", "0"),
            "recording_url": payload.get("RecordingUrl")
        }
