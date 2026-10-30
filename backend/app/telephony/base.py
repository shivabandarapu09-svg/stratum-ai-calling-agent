from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class TelephonyProvider(ABC):
    """
    Vendor-agnostic telephony interface for outbound calls, inbound handling,
    call transfers, termination, and audio stream routing.
    """

    @abstractmethod
    async def initiate_call(
        self,
        to_phone: str,
        from_phone: str,
        callback_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Trigger an outbound call through the telephony carrier."""
        pass

    @abstractmethod
    async def terminate_call(self, provider_call_id: str) -> bool:
        """Hang up / terminate an ongoing call."""
        pass

    @abstractmethod
    async def transfer_call(self, provider_call_id: str, target_phone: str) -> bool:
        """Transfer call to a live human agent."""
        pass

    @abstractmethod
    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize carrier-specific webhook payloads into standard event format."""
        pass
