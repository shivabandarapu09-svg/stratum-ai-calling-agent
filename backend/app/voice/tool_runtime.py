"""
Trajectory2Task (ACL 2026) — Reliable Tool Runtime, DAG Preconditions & Infeasibility Gatekeeper
==================================================================================================
Implements verified tool calling with:
1. Clear Pydantic tool input schemas and output validation.
2. API Dependency DAG Preconditions (diagnostic read tools execute before state-mutating write tools).
3. Policy-Infeasible vs. Tool-Infeasible gatekeeping:
   - Policy-Infeasible: Prohibited by business/domain rules (e.g., medical prescriptions over phone,
     discounts >10%, unverified caller modifications).
   - Tool-Infeasible: Blocked by backend/environment state (e.g., cancelling an already shipped/delivered
     order, booking a clinic visit on Sunday or outside operating hours, requesting unavailable 1 BHK inventory,
     or shipping to an unserviceable pincode).
4. Safe Retries, Timeouts & Idempotency deduplication.
5. Persistent Audit Logging in `ToolExecutionLog` (SQLite) and truthful multilingual response synthesis
   (never claiming an action succeeded unless `status == "success"`).
"""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.models import Appointment, Call, ToolExecutionLog
from app.voice.belief_state import SessionBeliefState


# ==============================================================================
# 1. Pydantic Tool Input Schemas
# ==============================================================================

class GetOrderStatusInput(BaseModel):
    order_id: str = Field(..., min_length=4, description="Canonical order identifier such as COD-4421")


class ConfirmCodOrderInput(BaseModel):
    order_id: str = Field(..., min_length=4)
    delivery_slot: str = Field(..., min_length=3)


class CancelCodOrderInput(BaseModel):
    order_id: str = Field(..., min_length=4)
    cancellation_reason: str = Field(..., min_length=3)


class ModifyOrderAddressInput(BaseModel):
    order_id: str = Field(..., min_length=4)
    new_address: str = Field(..., min_length=5)
    pincode: str = Field(..., pattern=r"^[1-9]\d{5}$")


class CheckSlotAvailabilityInput(BaseModel):
    template_domain: str = Field(..., min_length=2)
    visit_date: str = Field(..., min_length=3)
    visit_time: str = Field(..., min_length=3)
    resource_type: str = Field(default="general", min_length=2)


class BookAppointmentInput(BaseModel):
    template_domain: str = Field(..., min_length=2)
    visit_date: str = Field(..., min_length=3)
    visit_time: str = Field(..., min_length=3)
    resource_type: str = Field(..., min_length=2)
    customer_phone: str = Field(default="+919876543210")


class RescheduleAppointmentInput(BaseModel):
    appointment_id: str = Field(..., min_length=4)
    visit_date: str = Field(..., min_length=3)
    visit_time: str = Field(..., min_length=3)
    resource_type: str = Field(default="general")


class CancelAppointmentInput(BaseModel):
    appointment_id: str = Field(..., min_length=4)
    cancellation_reason: str = Field(..., min_length=3)


class CalculateEmiInput(BaseModel):
    loan_amount_lakhs: float = Field(..., gt=0)
    interest_rate_pct: float = Field(default=8.55, gt=0)
    tenure_years: int = Field(default=20, gt=0)


class DispatchWhatsappInput(BaseModel):
    customer_phone: str = Field(..., min_length=8)
    collateral_type: str = Field(default="brochure_and_floor_plan")


class ToolCallResult(BaseModel):
    tool_name: str
    status: str  # "success", "policy_infeasible", "tool_infeasible", "backend_error", "validation_error"
    input_args: Dict[str, Any]
    output: Dict[str, Any]
    retry_count: int = 0
    latency_ms: float = 0.0
    idempotent_replay: bool = False
    error_reason: Optional[str] = None

    def to_telemetry_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool_name,
            "status": "executed" if self.status == "success" else self.status,
            "verified_status": self.status,
            "input": self.input_args,
            "output": self.output,
            "retry_count": self.retry_count,
            "latency_ms": round(self.latency_ms, 2),
            "idempotent_replay": self.idempotent_replay,
            "error_reason": self.error_reason,
            "detail": self._build_summary_detail(),
        }

    def _build_summary_detail(self) -> str:
        if self.status == "success":
            return self.output.get("summary", f"{self.tool_name} succeeded")
        return f"[{self.status.upper()}] {self.error_reason or self.output.get('message', 'Action blocked')}"


# ==============================================================================
# 2. Synthetic Backend State Store (Orders, Inventory, Serviceable Pincodes)
# ==============================================================================

MOCK_ORDER_CATALOG: Dict[str, Dict[str, Any]] = {
    "COD-4421": {
        "order_id": "COD-4421",
        "item": "Noise-Cancelling Wireless Earbuds Pro",
        "amount_inr": 2499,
        "status": "pending_confirmation",
        "address": "Flat 402, Cyber Heights, Hitech City, Hyderabad",
        "pincode": "500081",
        "requires_verification_for_cancel": False,
    },
    "COD-5510": {
        "order_id": "COD-5510",
        "item": "Smart Fitness Watch Series 8",
        "amount_inr": 4999,
        "status": "pending_confirmation",
        "address": "14 MG Road, Indiranagar, Bengaluru",
        "pincode": "560038",
        "requires_verification_for_cancel": True,
    },
    "COD-9999": {
        "order_id": "COD-9999",
        "item": "Mechanical Gaming Keyboard RGB",
        "amount_inr": 3299,
        "status": "delivered",
        "address": "Plot 12, Anna Nagar, Chennai",
        "pincode": "600040",
        "requires_verification_for_cancel": False,
    },
    "COD-8888": {
        "order_id": "COD-8888",
        "item": "4K Action Camera Waterproof",
        "amount_inr": 6499,
        "status": "shipped_in_transit",
        "address": "22 Marine Drive, Kochi",
        "pincode": "682031",
        "requires_verification_for_cancel": False,
    },
}

UNSERVICEABLE_PINCODES = {"999999", "888888", "000000"}
REAL_ESTATE_AVAILABLE_CONFIGS = {"3 BHK", "4 BHK", "4 BHK Penthouse"}
CLINIC_OPERATING_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Tomorrow"}
CLINIC_CLOSED_DAYS = {"Sunday"}
CLINIC_INVALID_HOURS = {"10:00 PM", "11:00 PM", "11:30 PM", "5:00 AM", "6:00 AM"}


# ==============================================================================
# 3. ToolExecutor with DAG Preconditions, Retries, Idempotency & DB Logging
# ==============================================================================

class ToolExecutor:
    """
    Executes tools deterministically with schema validation, DAG precondition checks,
    policy/tool constraint enforcement, transient retry recovery, and SQLite audit logging.
    """

    def __init__(
        self,
        db: Session,
        call: Call,
        belief_state: SessionBeliefState,
        max_retries: int = 2,
        timeout_ms: float = 1500.0,
    ):
        self.db = db
        self.call = call
        self.belief = belief_state
        self.max_retries = max_retries
        self.timeout_ms = timeout_ms
        self._idempotency_cache: Dict[str, ToolCallResult] = {}
        # Session-local mutable copy of orders so tests don't pollute global state across calls
        self.orders_state: Dict[str, Dict[str, Any]] = {
            k: dict(v) for k, v in MOCK_ORDER_CATALOG.items()
        }
        # Fault injection controls for testing backend failures & retries
        self.fault_injection_mode: Optional[str] = None  # None, "transient_once", "persistent_outage"
        self._transient_fault_triggered: bool = False

    def _compute_idempotency_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        canonical = json.dumps(args, sort_keys=True, default=str)
        raw = f"{self.call.id}:{tool_name}:{canonical}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _persist_log(self, result: ToolCallResult, idempotency_key: str) -> None:
        try:
            log_row = ToolExecutionLog(
                call_id=self.call.id,
                turn_index=self.belief.turn_index,
                tool_name=result.tool_name,
                idempotency_key=idempotency_key,
                input_args=result.input_args,
                output_payload=result.output,
                status=result.status,
                retry_count=result.retry_count,
                latency_ms=result.latency_ms,
                error_message=result.error_reason,
            )
            self.db.add(log_row)
            self.db.commit()
        except Exception:
            self.db.rollback()

    def execute_with_retry(
        self,
        tool_name: str,
        args: Dict[str, Any],
        handler: Callable[[Dict[str, Any]], Tuple[str, Dict[str, Any], Optional[str]]],
    ) -> ToolCallResult:
        """
        Wraps a tool handler with idempotency deduplication, fault-injection hooks,
        retry on transient backend errors, and SQLite audit logging.
        """
        idem_key = self._compute_idempotency_key(tool_name, args)
        if idem_key in self._idempotency_cache:
            cached = self._idempotency_cache[idem_key].model_copy(deep=True)
            cached.idempotent_replay = True
            return cached

        start_t = time.perf_counter()
        attempts = 0
        last_err = None

        while attempts <= self.max_retries:
            try:
                # Check simulated backend fault injection
                if self.fault_injection_mode == "persistent_outage":
                    raise RuntimeError("Backend database/API gateway timeout (503 Service Unavailable)")
                if self.fault_injection_mode == "transient_once" and not self._transient_fault_triggered:
                    self._transient_fault_triggered = True
                    raise RuntimeError("Transient network socket timeout on attempt 1")

                status, output, err_reason = handler(args)
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                res = ToolCallResult(
                    tool_name=tool_name,
                    status=status,
                    input_args=args,
                    output=output,
                    retry_count=attempts,
                    latency_ms=elapsed_ms,
                    error_reason=err_reason,
                )
                self.belief.executed_tools_history.append(tool_name)
                if status == "success":
                    self._idempotency_cache[idem_key] = res
                self._persist_log(res, idem_key)
                return res

            except Exception as exc:
                last_err = str(exc)
                attempts += 1

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        fail_res = ToolCallResult(
            tool_name=tool_name,
            status="backend_error",
            input_args=args,
            output={"message": "Backend service temporarily unavailable after retries."},
            retry_count=attempts - 1,
            latency_ms=elapsed_ms,
            error_reason=last_err,
        )
        self._persist_log(fail_res, idem_key)
        return fail_res

    # --------------------------------------------------------------------------
    # High-Level Turn Orchestration for Active Belief State
    # --------------------------------------------------------------------------
    def evaluate_and_run_turn_tools(self, user_text: str) -> List[ToolCallResult]:
        """
        Evaluates the current `SessionBeliefState` after `update_from_utterance()`:
        1. Checks Policy-Infeasible triggers first (blocks prohibited actions).
        2. Checks if active intent has missing required slots (blocks premature tool calls).
        3. Enforces DAG diagnostic preconditions (`get_order_status` or `check_slot_availability`)
           before executing state-mutating write tools.
        """
        results: List[ToolCallResult] = []

        # 1. Policy-Infeasible Gatekeeper (actions_should_not_taken)
        if self.belief.policy_violation_flag:
            flag = self.belief.policy_violation_flag
            if flag == "medical_prescription_prohibited":
                res = ToolCallResult(
                    tool_name="prescribe_medication",
                    status="policy_infeasible",
                    input_args={"request": user_text[:80]},
                    output={
                        "policy_code": "HEALTHCARE_NO_TELE_PRESCRIPTION",
                        "message": "Clinical policy strictly prohibits AI agents from prescribing medication or antibiotic dosages without an in-person or certified doctor consultation.",
                    },
                    error_reason="Policy violation: AI cannot prescribe medications or dosages.",
                )
                self._persist_log(res, self._compute_idempotency_key("prescribe_medication", {"flag": flag}))
                results.append(res)
                return results

            elif flag == "excessive_discount_policy_violation":
                res = ToolCallResult(
                    tool_name="apply_custom_discount",
                    status="policy_infeasible",
                    input_args={"request": user_text[:80]},
                    output={
                        "policy_code": "PRICING_MAX_DISCOUNT_EXCEEDED",
                        "message": "Company pricing policy caps festive/spot benefits at 5% to 8%. Discounts of 20%-50% cannot be approved.",
                    },
                    error_reason="Policy violation: Requested discount exceeds authorized cap.",
                )
                self._persist_log(res, self._compute_idempotency_key("apply_custom_discount", {"flag": flag}))
                results.append(res)
                return results

            elif flag == "unverified_caller_modification_prohibited":
                res = ToolCallResult(
                    tool_name="verify_caller_identity",
                    status="policy_infeasible",
                    input_args={"caller_verification": "refused"},
                    output={
                        "policy_code": "SECURITY_VERIFICATION_REQUIRED",
                        "message": "Security policy requires caller verification (OTP or last 4 digits) before cancelling or changing a high-value order.",
                    },
                    error_reason="Policy violation: Caller refused mandatory identity verification.",
                )
                self._persist_log(res, self._compute_idempotency_key("verify_caller_identity", {"flag": flag}))
                results.append(res)
                return results

        # 2. Check Auxiliary Non-Blocking Tools (Brochure / EMI) if explicitly requested
        lower = user_text.lower()
        if self.belief.active_intent == "request_brochure" or (
            any(w in lower for w in ["whatsapp", "brochure", "floor plan", "pdf"])
            and "dispatch_whatsapp_collateral" not in self.belief.executed_tools_history
        ):
            results.append(self.run_dispatch_whatsapp())

        if self.belief.active_intent == "calculate_emi":
            missing = self.belief.get_missing_required_slots()
            if not missing:
                results.append(self.run_calculate_emi())
            return results

        # 3. If no primary intent or missing required slots, check if a tool-infeasible slot was already given
        #    (e.g., user asked "Do you have a 1 BHK for site visit?" or "Can I book Sunday at the clinic?")
        if self.belief.tool_infeasible_flag:
            if self.belief.tool_infeasible_flag in [
                "unsupported_bhk_inventory",
                "clinic_closed_on_sunday",
                "clinic_outside_operating_hours",
            ]:
                diag_res = self.run_check_slot_availability()
                results.append(diag_res)
                return results
            elif self.belief.tool_infeasible_flag in [
                "order_already_shipped_or_delivered",
                "unserviceable_delivery_pincode",
            ]:
                oid = self.belief.collected_slots.get("order_id", "COD-9999")
                diag_res = self.run_get_order_status(oid)
                results.append(diag_res)
                if self.belief.tool_infeasible_flag == "unserviceable_delivery_pincode":
                    results.append(self.run_modify_order_address())
                else:
                    results.append(self.run_cancel_cod_order())
                return results

        # 4. If required slots are still missing, do NOT execute state-mutating tools!
        missing_slots = self.belief.get_missing_required_slots()
        if missing_slots or not self.belief.active_intent:
            return results

        # 5. All required slots are present -> Execute DAG-validated tool chain for active intent
        intent = self.belief.active_intent

        if intent in ["schedule_site_visit", "book_clinic_appointment", "reschedule_appointment"]:
            # Step 5a: Diagnostic precondition `check_slot_availability`
            avail_res = self.run_check_slot_availability()
            results.append(avail_res)
            if avail_res.status != "success":
                return results

            # Step 5b: If an appointment already exists in this session and slots were revised, reschedule in-place!
            if self.belief.active_appointment_id and self.belief.has_recent_revision():
                resched_res = self.run_reschedule_appointment()
                results.append(resched_res)
            elif not self.belief.active_appointment_id:
                book_res = self.run_book_appointment()
                results.append(book_res)

        elif intent == "cancel_appointment":
            if self.belief.active_appointment_id:
                results.append(self.run_cancel_appointment())

        elif intent == "confirm_cod_order":
            oid = self.belief.collected_slots["order_id"]
            status_res = self.run_get_order_status(oid)
            results.append(status_res)
            if status_res.status == "success":
                results.append(self.run_confirm_cod_order())

        elif intent == "cancel_cod_order":
            oid = self.belief.collected_slots["order_id"]
            status_res = self.run_get_order_status(oid)
            results.append(status_res)
            if status_res.status == "success":
                results.append(self.run_cancel_cod_order())

        elif intent == "modify_order_address":
            oid = self.belief.collected_slots["order_id"]
            status_res = self.run_get_order_status(oid)
            results.append(status_res)
            if status_res.status == "success":
                results.append(self.run_modify_order_address())

        return results

    # --------------------------------------------------------------------------
    # Individual Schema-Validated Tool Implementations
    # --------------------------------------------------------------------------

    def run_get_order_status(self, order_id: str) -> ToolCallResult:
        try:
            validated = GetOrderStatusInput(order_id=order_id)
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="get_order_status",
                status="validation_error",
                input_args={"order_id": order_id},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            oid = args["order_id"]
            order = self.orders_state.get(oid)
            if not order:
                # Default synthetic order if not in special catalog
                order = {
                    "order_id": oid,
                    "item": "Standard D2C Merchandise Pack",
                    "amount_inr": 1899,
                    "status": "pending_confirmation",
                    "address": "Customer Registered Address",
                    "pincode": "500081",
                    "requires_verification_for_cancel": False,
                }
                self.orders_state[oid] = order
            return (
                "success",
                {
                    "order": order,
                    "summary": f"Order {oid} ({order['item']}, ₹{order['amount_inr']}) status is '{order['status']}'.",
                },
                None,
            )

        return self.execute_with_retry("get_order_status", validated.model_dump(), _handler)

    def run_confirm_cod_order(self) -> ToolCallResult:
        oid = self.belief.collected_slots.get("order_id", "")
        slot = self.belief.collected_slots.get("delivery_slot", "")
        try:
            validated = ConfirmCodOrderInput(order_id=oid, delivery_slot=slot)
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="confirm_cod_order",
                status="validation_error",
                input_args={"order_id": oid, "delivery_slot": slot},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            order = self.orders_state.get(args["order_id"], {})
            if order.get("status") in ["delivered", "cancelled"]:
                return (
                    "tool_infeasible",
                    {"message": f"Order {args['order_id']} is already {order.get('status')} and cannot be re-confirmed."},
                    f"Order state '{order.get('status')}' blocks confirmation.",
                )
            order["status"] = "confirmed_for_dispatch"
            order["delivery_slot"] = args["delivery_slot"]
            return (
                "success",
                {
                    "order_id": args["order_id"],
                    "status": "confirmed_for_dispatch",
                    "delivery_slot": args["delivery_slot"],
                    "summary": f"Confirmed COD Order {args['order_id']} for {args['delivery_slot']}.",
                },
                None,
            )

        return self.execute_with_retry("confirm_cod_order", validated.model_dump(), _handler)

    def run_cancel_cod_order(self) -> ToolCallResult:
        oid = self.belief.collected_slots.get("order_id", "")
        reason = self.belief.collected_slots.get("cancellation_reason", "customer_requested")
        try:
            validated = CancelCodOrderInput(order_id=oid, cancellation_reason=reason)
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="cancel_cod_order",
                status="validation_error",
                input_args={"order_id": oid, "cancellation_reason": reason},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            # DAG Precondition check: `get_order_status` must have run first
            if "get_order_status" not in self.belief.executed_tools_history:
                return (
                    "tool_infeasible",
                    {"message": "Precondition failed: get_order_status must be called before cancel_cod_order."},
                    "DAG Precondition violation: missing get_order_status.",
                )

            order = self.orders_state.get(args["order_id"], {})
            current_status = order.get("status", "pending_confirmation")

            # Tool-Infeasible check: Already delivered or shipped in transit
            if current_status in ["delivered", "shipped_in_transit"]:
                return (
                    "tool_infeasible",
                    {
                        "order_id": args["order_id"],
                        "current_status": current_status,
                        "message": f"Order {args['order_id']} cannot be cancelled because its status is already '{current_status}'.",
                    },
                    f"Tool-Infeasible: Order {args['order_id']} is already {current_status}.",
                )

            # Policy-Infeasible check: High-value order requiring caller identity verification
            if order.get("requires_verification_for_cancel") and not self.belief.verified_caller:
                return (
                    "policy_infeasible",
                    {
                        "order_id": args["order_id"],
                        "policy_code": "HIGH_VALUE_ORDER_VERIFICATION_REQUIRED",
                        "message": f"Order {args['order_id']} (₹{order.get('amount_inr')}) requires caller OTP / last-4 phone digit verification before cancellation.",
                    },
                    "Policy-Infeasible: High-value order cancellation requires caller identity verification.",
                )

            order["status"] = "cancelled"
            order["cancellation_reason"] = args["cancellation_reason"]
            return (
                "success",
                {
                    "order_id": args["order_id"],
                    "status": "cancelled",
                    "reason": args["cancellation_reason"],
                    "summary": f"Cancelled Order {args['order_id']} (Reason: {args['cancellation_reason']}).",
                },
                None,
            )

        return self.execute_with_retry("cancel_cod_order", validated.model_dump(), _handler)

    def run_modify_order_address(self) -> ToolCallResult:
        oid = self.belief.collected_slots.get("order_id", "COD-4421")
        new_addr = self.belief.collected_slots.get("new_address", "Updated Street Address")
        pincode = self.belief.collected_slots.get("pincode", "500081")
        try:
            validated = ModifyOrderAddressInput(order_id=oid, new_address=new_addr, pincode=pincode)
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="modify_order_address",
                status="validation_error",
                input_args={"order_id": oid, "new_address": new_addr, "pincode": pincode},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            order = self.orders_state.get(args["order_id"], {})
            if order.get("status") in ["delivered", "shipped_in_transit"]:
                return (
                    "tool_infeasible",
                    {
                        "order_id": args["order_id"],
                        "current_status": order.get("status"),
                        "message": f"Cannot modify address for Order {args['order_id']} because it is already {order.get('status')}.",
                    },
                    f"Tool-Infeasible: Order is {order.get('status')}.",
                )
            if args["pincode"] in UNSERVICEABLE_PINCODES:
                return (
                    "tool_infeasible",
                    {
                        "order_id": args["order_id"],
                        "pincode": args["pincode"],
                        "message": f"Courier partner does not service pincode {args['pincode']}.",
                    },
                    f"Tool-Infeasible: Pincode {args['pincode']} is unserviceable.",
                )

            order["address"] = args["new_address"]
            order["pincode"] = args["pincode"]
            order["status"] = "confirmed_address_updated"
            return (
                "success",
                {
                    "order_id": args["order_id"],
                    "new_address": args["new_address"],
                    "pincode": args["pincode"],
                    "summary": f"Updated delivery address for {args['order_id']} to {args['new_address']} ({args['pincode']}).",
                },
                None,
            )

        return self.execute_with_retry("modify_order_address", validated.model_dump(), _handler)

    def run_check_slot_availability(self) -> ToolCallResult:
        domain = self.belief.template_domain
        v_date = self.belief.collected_slots.get("visit_date", "Saturday")
        v_time = self.belief.collected_slots.get("visit_time", "11:00 AM")
        resource = (
            self.belief.collected_slots.get("bhk_preference")
            or self.belief.collected_slots.get("department")
            or "general"
        )
        try:
            validated = CheckSlotAvailabilityInput(
                template_domain=domain,
                visit_date=v_date,
                visit_time=v_time,
                resource_type=resource,
            )
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="check_slot_availability",
                status="validation_error",
                input_args={"visit_date": v_date, "visit_time": v_time},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            dom = args["template_domain"]
            day = args["visit_date"]
            tm = args["visit_time"]
            res_type = args["resource_type"]

            # 1. Real Estate inventory check (Only 3 BHK & 4 BHK exist at Prestige Sky Meadows)
            if dom == "real_estate" and res_type in ["1 BHK", "2 BHK"]:
                return (
                    "tool_infeasible",
                    {
                        "requested_config": res_type,
                        "available_configs": sorted(list(REAL_ESTATE_AVAILABLE_CONFIGS)),
                        "message": f"Prestige Sky Meadows does not offer {res_type} units. Only 3 BHK and 4 BHK configurations are available.",
                    },
                    f"Tool-Infeasible: {res_type} configuration is not in project inventory.",
                )

            # 2. Clinic operating day check (Closed on Sundays)
            if dom == "clinic_healthcare" and day in CLINIC_CLOSED_DAYS:
                return (
                    "tool_infeasible",
                    {
                        "requested_day": day,
                        "operating_days": "Monday to Saturday (08:00 AM - 08:30 PM)",
                        "message": "Apollo Care Diagnostics & Clinic is closed on Sundays for regular OPD consultations.",
                    },
                    "Tool-Infeasible: Clinic is closed on Sunday.",
                )

            # 3. Clinic operating hours check
            if dom == "clinic_healthcare" and tm in CLINIC_INVALID_HOURS:
                return (
                    "tool_infeasible",
                    {
                        "requested_time": tm,
                        "operating_hours": "08:00 AM - 08:30 PM",
                        "message": f"Requested time {tm} is outside clinic OPD hours (08:00 AM to 08:30 PM).",
                    },
                    f"Tool-Infeasible: {tm} is outside clinic operating hours.",
                )

            return (
                "success",
                {
                    "available": True,
                    "visit_date": day,
                    "visit_time": tm,
                    "resource_type": res_type,
                    "summary": f"Slot verified available: {res_type} on {day} at {tm}.",
                },
                None,
            )

        return self.execute_with_retry("check_slot_availability", validated.model_dump(), _handler)

    def run_book_appointment(self) -> ToolCallResult:
        domain = self.belief.template_domain
        v_date = self.belief.collected_slots.get("visit_date", "")
        v_time = self.belief.collected_slots.get("visit_time", "")
        resource = (
            self.belief.collected_slots.get("bhk_preference")
            or self.belief.collected_slots.get("department")
            or "Consultation"
        )
        try:
            validated = BookAppointmentInput(
                template_domain=domain,
                visit_date=v_date,
                visit_time=v_time,
                resource_type=resource,
                customer_phone=self.call.customer_phone or "+919876543210",
            )
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="book_appointment_slot",
                status="validation_error",
                input_args={"visit_date": v_date, "visit_time": v_time, "resource_type": resource},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            if "check_slot_availability" not in self.belief.executed_tools_history:
                return (
                    "tool_infeasible",
                    {"message": "Precondition failed: check_slot_availability must precede book_appointment_slot."},
                    "DAG Precondition violation: missing check_slot_availability.",
                )

            appt = Appointment(
                organization_id=self.call.organization_id,
                customer_id=self.call.customer_id or "cust-default",
                agent_id=self.call.agent_id,
                call_id=self.call.id,
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                purpose=f"{args['resource_type']} ({args['visit_date']} at {args['visit_time']})",
                notes=f"Verified booking via Stratum ToolRuntime: {args['resource_type']} on {args['visit_date']} at {args['visit_time']}",
                status="confirmed",
            )
            self.db.add(appt)
            self.db.commit()
            self.db.refresh(appt)
            self.belief.active_appointment_id = appt.id

            return (
                "success",
                {
                    "appointment_id": appt.id,
                    "resource_type": args["resource_type"],
                    "visit_date": args["visit_date"],
                    "visit_time": args["visit_time"],
                    "status": "confirmed",
                    "summary": f"Booked {args['resource_type']} on {args['visit_date']} at {args['visit_time']} (ID: {appt.id[:8]}).",
                },
                None,
            )

        return self.execute_with_retry("book_appointment_slot", validated.model_dump(), _handler)

    def run_reschedule_appointment(self) -> ToolCallResult:
        appt_id = self.belief.active_appointment_id or ""
        v_date = self.belief.collected_slots.get("visit_date", "")
        v_time = self.belief.collected_slots.get("visit_time", "")
        resource = (
            self.belief.collected_slots.get("bhk_preference")
            or self.belief.collected_slots.get("department")
            or "Consultation"
        )
        try:
            validated = RescheduleAppointmentInput(
                appointment_id=appt_id,
                visit_date=v_date,
                visit_time=v_time,
                resource_type=resource,
            )
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="reschedule_appointment_slot",
                status="validation_error",
                input_args={"appointment_id": appt_id, "visit_date": v_date, "visit_time": v_time},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            appt = self.db.query(Appointment).filter(Appointment.id == args["appointment_id"]).first()
            if not appt:
                return (
                    "tool_infeasible",
                    {"message": f"Appointment {args['appointment_id']} not found."},
                    "Appointment record not found.",
                )
            appt.purpose = f"{args['resource_type']} ({args['visit_date']} at {args['visit_time']})"
            appt.notes = f"Rescheduled in-place via Stratum ToolRuntime to {args['resource_type']} on {args['visit_date']} at {args['visit_time']}"
            appt.status = "confirmed"
            self.db.commit()

            return (
                "success",
                {
                    "appointment_id": appt.id,
                    "resource_type": args["resource_type"],
                    "visit_date": args["visit_date"],
                    "visit_time": args["visit_time"],
                    "status": "rescheduled",
                    "summary": f"Updated appointment {appt.id[:8]} in-place to {args['resource_type']} on {args['visit_date']} at {args['visit_time']}.",
                },
                None,
            )

        return self.execute_with_retry("reschedule_appointment_slot", validated.model_dump(), _handler)

    def run_cancel_appointment(self) -> ToolCallResult:
        appt_id = self.belief.active_appointment_id or ""
        reason = self.belief.collected_slots.get("cancellation_reason", "customer_requested")
        try:
            validated = CancelAppointmentInput(appointment_id=appt_id, cancellation_reason=reason)
        except ValidationError as ve:
            return ToolCallResult(
                tool_name="cancel_appointment_slot",
                status="validation_error",
                input_args={"appointment_id": appt_id, "cancellation_reason": reason},
                output={},
                error_reason=str(ve),
            )

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            appt = self.db.query(Appointment).filter(Appointment.id == args["appointment_id"]).first()
            if not appt:
                return (
                    "tool_infeasible",
                    {"message": "No active appointment found to cancel."},
                    "Appointment not found.",
                )
            appt.status = "cancelled"
            appt.notes = f"Cancelled by caller: {args['cancellation_reason']}"
            self.db.commit()
            return (
                "success",
                {
                    "appointment_id": appt.id,
                    "status": "cancelled",
                    "summary": f"Cancelled appointment {appt.id[:8]} ({args['cancellation_reason']}).",
                },
                None,
            )

        return self.execute_with_retry("cancel_appointment_slot", validated.model_dump(), _handler)

    def run_calculate_emi(self) -> ToolCallResult:
        raw_loan = self.belief.collected_slots.get("loan_amount", "80.0 Lakhs")
        lakhs = float(raw_loan.split()[0]) if raw_loan else 80.0
        validated = CalculateEmiInput(loan_amount_lakhs=lakhs)

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            principal = args["loan_amount_lakhs"] * 100000.0
            r = (args["interest_rate_pct"] / 12.0) / 100.0
            n = args["tenure_years"] * 12
            emi = (principal * r * ((1 + r) ** n)) / (((1 + r) ** n) - 1)
            emi_inr = int(round(emi))
            return (
                "success",
                {
                    "loan_amount_lakhs": args["loan_amount_lakhs"],
                    "interest_rate_pct": args["interest_rate_pct"],
                    "tenure_years": args["tenure_years"],
                    "monthly_emi_inr": emi_inr,
                    "summary": f"EMI for ₹{args['loan_amount_lakhs']} Lakhs at {args['interest_rate_pct']}% for {args['tenure_years']} yrs is ₹{emi_inr:,}/month.",
                },
                None,
            )

        return self.execute_with_retry("calculate_emi_schedule", validated.model_dump(), _handler)

    def run_dispatch_whatsapp(self) -> ToolCallResult:
        phone = self.call.customer_phone or "+919876543210"
        validated = DispatchWhatsappInput(customer_phone=phone)

        def _handler(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
            return (
                "success",
                {
                    "customer_phone": args["customer_phone"],
                    "collateral_type": args["collateral_type"],
                    "delivery_status": "sent",
                    "summary": f"Dispatched WhatsApp brochure & floor plan to {args['customer_phone']}.",
                },
                None,
            )

        return self.execute_with_retry("dispatch_whatsapp_collateral", validated.model_dump(), _handler)

    # --------------------------------------------------------------------------
    # Multilingual Grounded Response Composer (Never Hallucinates Tool Success)
    # --------------------------------------------------------------------------
    def compose_grounded_response(
        self, tool_results: List[ToolCallResult], language: str = "en"
    ) -> Optional[str]:
        """
        Synthesizes a deterministic, truthful response in `en`, `hi`, `te`, `ta`, `ml`, or `kn`
        grounded strictly in the verified `tool_results` or `belief_state` clarification needs.
        Returns `None` only when no tool/clarification/policy event occurred on this turn.
        """
        lang = language if language in ["en", "hi", "te", "ta", "ml", "kn"] else "en"

        # Case 1: Policy-Infeasible or Tool-Infeasible or Backend Error occurred
        for res in tool_results:
            if res.status == "policy_infeasible":
                return self._format_policy_refusal(res, lang)
            if res.status == "tool_infeasible":
                return self._format_tool_infeasible(res, lang)
            if res.status == "backend_error":
                return self._format_backend_error(res, lang)

        # Case 2: Active intent has missing or ambiguous required slots -> Ask concise clarification!
        missing = self.belief.get_missing_required_slots()
        if self.belief.active_intent and missing:
            return self.belief.build_clarification_question(lang)

        # Case 3: Verified Successful Tool Execution
        primary_success = [
            r
            for r in tool_results
            if r.status == "success"
            and r.tool_name
            in [
                "book_appointment_slot",
                "reschedule_appointment_slot",
                "cancel_appointment_slot",
                "confirm_cod_order",
                "cancel_cod_order",
                "modify_order_address",
                "calculate_emi_schedule",
                "dispatch_whatsapp_collateral",
            ]
        ]
        if primary_success:
            return self._format_verified_success(primary_success[-1], lang)

        return None

    def _format_policy_refusal(self, res: ToolCallResult, lang: str) -> str:
        code = res.output.get("policy_code", "")
        if code == "HEALTHCARE_NO_TELE_PRESCRIPTION":
            msgs = {
                "en": "I understand your concern, but under clinical safety policy I cannot prescribe medications or antibiotic dosages over the phone. I can immediately book an urgent consultation with our physician or connect you to our duty doctor.",
                "hi": "मैं आपकी चिंता समझता हूँ, लेकिन क्लिनिकल सुरक्षा नीति के अनुसार मैं फोन पर दवाइयाँ या एंटीबायोटिक खुराक निर्धारित नहीं कर सकता। मैं तुरंत डॉक्टर के साथ आपकी अपॉइंटमेंट बुक कर सकता हूँ या ड्यूटी डॉक्टर से बात करा सकता हूँ।",
                "te": "మీ పరిస్థితి నాకు అర్థమైంది, కానీ క్లినికల్ భద్రతా నిబంధనల ప్రకారం ఫోన్‌లో మందులు లేదా యాంటీబయాటిక్ డోసేజ్ సూచించడానికి అనుమతి లేదు. నేను వెంటనే డాక్టర్‌తో అపాయింట్‌మెంట్ బుక్ చేయగలను లేదా డ్యూటీ డాక్టర్‌కి కనెక్ట్ చేయగలను.",
                "ta": "உங்கள் கவலை புரிகிறது, ஆனால் மருத்துவ பாதுகாப்பு விதிகளின்படி தொலைபேசியில் மருந்துகள் அல்லது மாத்திரை அளவுகளை என்னால் பரிந்துரைக்க முடியாது. உடனடியாக மருத்துவரிடம் அப்பாயின்ட்மென்ட் பதிவு செய்யட்டுமா?",
                "ml": "നിങ്ങളുടെ ബുദ്ധിമുട്ട് ഞാൻ മനസ്സിലാക്കുന്നു, എന്നാൽ ക്ലിനിക്കൽ സുരക്ഷാ നയമനുസരിച്ച് ഫോണിലൂടെ മരുന്നുകളോ ഡോസേജോ നിർദ്ദേശിക്കാൻ എനിക്ക് അനുവാദമില്ല. ഡോക്ടറുമായി ഉടൻ ഒരു കൺസൾട്ടേഷൻ ബുക്ക് ചെയ്യാൻ ഞാൻ സഹായിക്കട്ടെ?",
                "kn": "ನಿಮ್ಮ ಕಾಳಜಿ ನನಗೆ ಅರ್ಥವಾಗುತ್ತದೆ, ಆದರೆ ವೈದ್ಯಕೀಯ ಸುರಕ್ಷತಾ ನಿಯಮಗಳ ಪ್ರಕಾರ ಫೋನ್‌ನಲ್ಲಿ ಔಷಧಿಗಳನ್ನು ಅಥವಾ ಡೋಸೇಜ್ ಅನ್ನು ಶಿಫಾರಸು ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ನಾನು ತಕ್ಷಣ ವೈದ್ಯರೊಂದಿಗೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲೇ?",
            }
            return msgs[lang]

        if code == "PRICING_MAX_DISCOUNT_EXCEEDED":
            msgs = {
                "en": "I checked our pricing policy—while I cannot approve a 30% discount as company policy caps spot benefits at 5% to 8%, I can arrange a callback with our Senior Sales Director during your site visit to discuss corporate payment flexibility.",
                "hi": "मैंने हमारी मूल्य नीति की जाँच की है—कंपनी नीति के तहत अधिकतम 5% से 8% तक की छूट ही अनुमन्य है, इसलिए मैं 30% छूट स्वीकृत नहीं कर सकता। हालांकि, मैं सीनियर सेल्स डायरेक्टर के साथ आपकी बात करा सकता हूँ।",
                "te": "మా ప్రైసింగ్ పాలసీ ప్రకారం 5% నుండి 8% వరకు మాత్రమే ఆఫర్ ఇవ్వడానికి అనుమతి ఉంది, కాబట్టి 30% డిస్కౌంట్ ఆమోదించడం సాధ్యం కాదు. అయితే సైట్ విజిట్ సమయంలో మా సీనియర్ సేల్స్ డైరెక్టర్‌తో మాట్లాడించగలను.",
                "ta": "எங்கள் நிறுவன கொள்கையின்படி 5% முதல் 8% வரை மட்டுமே சலுகை வழங்க முடியும், எனவே 30% தள்ளுபடி அளிக்க இயலாது. இருப்பினும் எங்கள் மூத்த விற்பனை இயக்குநரிடம் பேச ஏற்பாடு செய்யலாம்.",
                "ml": "ഞങ്ങളുടെ പ്രൈസിംഗ് പോളിസി അനുസരിച്ച് 5% മുതൽ 8% വരെ മാത്രമേ ഇളവ് അനുവദിക്കാൻ കഴിയൂ, അതിനാൽ 30% ഡിസ്കൗണ്ട് നൽകാൻ കഴിയില്ല. എങ്കിലും സീനിയർ സെയിൽസ് ഡയറക്ടറുമായി സംസാരിക്കാൻ അവസരമൊരുക്കാം.",
                "kn": "ನಮ್ಮ ಕಂಪನಿಯ ನಿಯಮದ ಪ್ರಕಾರ 5% ರಿಂದ 8% ವರೆಗೆ ಮಾತ್ರ ರಿಯಾಯಿತಿ ನೀಡಲು ಸಾಧ್ಯ, ಆದ್ದರಿಂದ 30% ಡಿಸ್ಕೌಂಟ್ ಅನುಮೋದಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ. ಆದರೆ ನಮ್ಮ ಹಿರಿಯ ಸೇಲ್ಸ್ ಡೈರೆಕ್ಟರ್ ಜೊತೆ ಮಾತನಾಡಲು ವ್ಯವಸ್ಥೆ ಮಾಡಬಹುದು.",
            }
            return msgs[lang]

        # Default verification policy refusal
        msgs = {
            "en": "For your account security, company policy requires verifying your 4-digit OTP or the last 4 digits of your phone number before I can cancel or modify this order. Could you please share the verification code?",
            "hi": "आपकी सुरक्षा नीति के अनुसार, इस ऑर्डर को रद्द या संशोधित करने से पहले 4-अंकों का ओटीपी या फोन नंबर के अंतिम 4 अंक सत्यापित करना आवश्यक है। कृपया कोड साझा करें।",
            "te": "మీ ఖాతా భద్రత కోసం, ఈ ఆర్డర్‌ను రద్దు చేయడానికి లేదా మార్చడానికి ముందు 4-అంకెల OTP లేదా ఫోన్ నంబర్ చివరి 4 అంకెలు వెరిఫై చేయడం తప్పనిసరి. దయచేసి ఆ కోడ్ చెప్తారా?",
            "ta": "உங்கள் கணக்கு பாதுகாப்பிற்காக, ஆர்டரை ரத்து செய்ய அல்லது மாற்ற 4 இலக்க ஓடிபி அல்லது தொலைபேசி எண்ணின் கடைசி 4 இலக்கங்களை உறுதிப்படுத்த வேண்டும்.",
            "ml": "സുരക്ഷാ നയമനുസരിച്ച്, ഓർഡർ റദ്ദാക്കുന്നതിനോ മാറ്റുന്നതിനോ മുൻപ് 4 അക്ക ഒടിപി അല്ലെങ്കിൽ ഫോൺ നമ്പറിന്റെ അവസാന 4 അക്കങ്ങൾ സ്ഥിരീകരിക്കേണ്ടതുണ്ട്.",
            "kn": "ನಿಮ್ಮ ಖಾತೆಯ സുരക്ഷತೆಗಾಗಿ, ಆರ್ಡರ್ ರದ್ದುಗೊಳಿಸಲು ಅಥವಾ ಬದಲಾಯಿಸಲು 4 ಅಂಕಿಯ OTP ಅಥವಾ ಫೋನ್ ಸಂಖ್ಯೆಯ ಕೊನೆಯ 4 ಅಂಕಿಗಳನ್ನು ದೃಢೀಕರಿಸುವುದು ಕಡ್ಡಾಯವಾಗಿದೆ.",
        }
        return msgs[lang]

    def _format_tool_infeasible(self, res: ToolCallResult, lang: str) -> str:
        err = res.error_reason or ""
        if "configuration is not in project inventory" in err:
            req = res.output.get("requested_config", "1 BHK")
            msgs = {
                "en": f"I checked our live inventory—Prestige Sky Meadows only offers spacious 3 BHK and 4 BHK residences, so {req} units are not available in this project. Would you like to explore our 3 BHK configuration starting at ₹1.45 Cr instead?",
                "hi": f"मैंने हमारी लाइव इन्वेंट्री चेक की है—Prestige Sky Meadows में केवल 3 BHK और 4 BHK अपार्टमेंट्स उपलब्ध हैं, इसलिए इस प्रोजेक्ट में {req} उपलब्ध नहीं है। क्या आप ₹1.45 करोड़ से शुरू होने वाले 3 BHK का विवरण देखना चाहेंगे?",
                "te": f"నేను మా లైవ్ ఇన్వెంటరీని పరిశీలించాను—Prestige Sky Meadows లో కేవలం 3 BHK మరియు 4 BHK ఫ్లాట్లు మాత్రమే ఉన్నాయి, కాబట్టి {req} అందుబాటులో లేదు. మీరు ₹1.45 Cr నుండి ప్రారంభమయ్యే 3 BHK చూడాలనుకుంటున్నారా?",
                "ta": f"நான் எங்கள் பட்டியலை சரிபார்த்தேன்—Prestige Sky Meadows-ல் 3 BHK மற்றும் 4 BHK வீடுகள் மட்டுமே உள்ளன, {req} उपलब्धमில்லை. அதற்கு பதிலாக 3 BHK வீட்டைப் பார்க்க விரும்புகிறீர்களா?",
                "ml": f"ഞാൻ ഞങ്ങളുടെ ലൈവ് ഇൻവെന്ററി പരിശോധിച്ചു—Prestige Sky Meadows-ൽ 3 BHK, 4 BHK ഫ്ലാറ്റുകൾ മാത്രമേ ലഭ്യമാകൂ, അതിനാൽ {req} ലഭ്യമല്ല. പകരം 3 BHK കാണാൻ താല്പര്യമുണ്ടോ?",
                "kn": f"ನಾನು ನಮ್ಮ ಲೈವ್ ಇನ್ವೆಂಟರಿಯನ್ನು ಪರಿಶೀಲಿಸಿದ್ದೇನೆ—Prestige Sky Meadows ನಲ್ಲಿ ಕೇವಲ 3 BHK ಮತ್ತು 4 BHK ಫ್ಲಾಟ್‌ಗಳು ಮಾತ್ರ ಲಭ್ಯವಿವೆ, ಆದ್ದರಿಂದ {req} ಲಭ್ಯವಿಲ್ಲ. ಬದಲಿಗೆ 3 BHK ನೋಡಲು ಬಯಸುತ್ತೀರಾ?",
            }
            return msgs[lang]

        if "closed on Sunday" in err or "outside clinic operating hours" in err:
            msgs = {
                "en": "I checked our clinic schedule, and Apollo Care Diagnostics operates Monday through Saturday from 8:00 AM to 8:30 PM (closed on Sundays and late nights). Could we schedule your appointment for Monday at 10:30 AM or Saturday instead?",
                "hi": "मैंने क्लिनिक का शेड्यूल चेक किया है—हमारा क्लिनिक सोमवार से शनिवार सुबह 8:00 बजे से रात 8:30 बजे तक खुला रहता है (रविवार को बंद रहता है)। क्या मैं आपकी अपॉइंटमेंट सोमवार सुबह 10:30 बजे या शनिवार के लिए बुक कर दूँ?",
                "te": "నేను క్లినిక్ షెడ్యూల్ చెక్ చేశాను—మా క్లినిక్ సోమవారం నుండి శనివారం వరకు ఉదయం 8:00 నుండి రాత్రి 8:30 వరకు మాత్రమే తెరిచి ఉంటుంది (ఆదివారం సెలవు). మీ అపాయింట్‌మెంట్‌ని సోమవారం లేదా శనివారం బుక్ చేయమంటారా?",
                "ta": "கிளினிக் நேரத்தை சரிபார்த்தேன்—திங்கள் முதல் சனி வரை காலை 8:00 முதல் இரவு 8:30 வரை மட்டுமே செயல்படும் (ஞாயிறு விடுமுறை). திங்கட்கிழமை அல்லது சனிக்கிழமை மாற்றிக்கொள்ளலாமா?",
                "ml": "ഞാൻ ക്ലിനിക്ക് ഷെഡ്യൂൾ പരിശോധിച്ചു—തിങ്കൾ മുതൽ ശനി വരെ രാവിലെ 8:00 മുതൽ രാത്രി 8:30 വരെയാണ് പ്രവർത്തന സമയം (ഞായറാഴ്ച അവധിയാണ്). തിങ്കളാഴ്ചത്തേക്ക് അപ്പോയിന്റ്മെന്റ് മാറ്റട്ടെ?",
                "kn": "ನಾನು ಕ್ಲಿನಿಕ್ ವೇಳಾಪಟ್ಟಿಯನ್ನು ಪರಿಶೀಲಿಸಿದ್ದೇನೆ—ಸೋಮವಾರದಿಂದ ಶನಿವಾರದವರೆಗೆ ಬೆಳಿಗ್ಗೆ 8:00 ರಿಂದ ರಾತ್ರಿ 8:30 ರವರೆಗೆ ಮಾತ್ರ ತೆರೆದಿರುತ್ತದೆ (ಭಾನುವಾರ ರಜೆ). ಸೋಮವಾರ ಅಥವಾ ಶನಿವಾರ ಬುಕ್ ಮಾಡಲೇ?",
            }
            return msgs[lang]

        if "unserviceable" in err:
            pin = res.output.get("pincode", "999999")
            msgs = {
                "en": f"I checked with our logistics system, and unfortunately pincode {pin} is currently non-serviceable for COD delivery. Could you provide an alternate serviceable pincode or keep the original address?",
                "hi": f"मैंने हमारे लॉजिस्टिक्स सिस्टम में जाँच की है, और दुर्भाग्यवश पिनकोड {pin} पर वर्तमान में डिलीवरी सेवा उपलब्ध नहीं है। क्या आप कोई दूसरा पिनकोड दे सकते हैं?",
                "te": f"మా లాజిస్టిక్స్ సిస్టమ్‌లో చెక్ చేశాను, దురదృష్టవశాత్తు పిన్‌కోడ్ {pin} కి ప్రస్తుతం డెలివరీ సదుపాయం లేదు. మీరు వేరే పిన్‌కోడ్ ఇవ్వగలరా?",
                "ta": f"எங்கள் டெலிவரி சிஸ்டத்தில் சரிபார்த்தேன், பின்கோடு {pin}-க்கு தற்போது சேவை இல்லை. மாற்று பின்கோடு தர முடியுமா?",
                "ml": f"ഞങ്ങളുടെ ലോജിസ്റ്റിക്സ് സിസ്റ്റത്തിൽ പരിശോധിച്ചപ്പോൾ പിൻകോഡ് {pin}-ലേക്ക് നിലവിൽ സർവീസ് ലഭ്യമല്ല. മറ്റൊരു പിൻകോഡ് നൽകാമോ?",
                "kn": f"ನಮ್ಮ ಲಾಜಿಸ್ಟಿಕ್ಸ್ ಸಿಸ್ಟಮ್‌ನಲ್ಲಿ ಪರಿಶೀಲಿಸಿದಾಗ ಪಿನ್‌ಕೋಡ್ {pin} ಗೆ ಪ್ರಸ್ತುತ ಡೆಲಿವರಿ ಸೇವೆ ಲಭ್ಯವಿಲ್ಲ. ಬೇರೆ ಪಿನ್‌ಕೋಡ್ ನೀಡಬಹುದೇ?",
            }
            return msgs[lang]

        # Already shipped / delivered order
        oid = res.output.get("order_id", "COD-9999")
        st = res.output.get("current_status", "shipped")
        msgs = {
            "en": f"I checked the live status of order {oid} first, and because it is already marked as '{st}', our system cannot cancel or modify it at this stage. You can initiate a return or doorstep refusal once it arrives.",
            "hi": f"मैंने पहले ऑर्डर {oid} का लाइव स्टेटस चेक किया—चूंकि यह पहले से ही '{st}' स्थिति में है, इसलिए सिस्टम इसे अभी रद्द या संशोधित नहीं कर सकता। डिलीवरी के समय आप इसे रिटर्न कर सकते हैं।",
            "te": f"నేను ముందుగా ఆర్డర్ {oid} స్టేటస్ చెక్ చేశాను—అది ఇప్పటికే '{st}' స్టేటస్‌లో ఉన్నందున ఇప్పుడు రద్దు చేయడం లేదా మార్చడం సాధ్యం కాదు. డెలివరీ వచ్చినప్పుడు మీరు రిటర్న్ చేయవచ్చు.",
            "ta": f"ஆர்டர் {oid}-ன் நிலையை சரிபார்த்தேன்—அது ஏற்கனவே '{st}' நிலையில் உள்ளதால் இப்போது ரத்து செய்யவோ மாற்றவோ முடியாது.",
            "ml": f"ഓർഡർ {oid}-ന്റെ സ്റ്റാറ്റസ് ഞാൻ പരിശോധിച്ചു—അത് ഇതിനകം '{st}' ആയതിനാൽ ഇപ്പോൾ റദ്ദാക്കാനോ മാറ്റാനോ കഴിയില്ല.",
            "kn": f"ಆರ್ಡರ್ {oid} ಸ್ಟೇಟಸ್ ಪರಿಶೀಲಿಸಿದ್ದೇನೆ—ಅದು ಈಗಾಗಲೇ '{st}' ಆಗಿರುವುದರಿಂದ ಈಗ ರದ್ದುಗೊಳಿಸಲು ಅಥವಾ ಬದಲಾಯಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        }
        return msgs[lang]

    def _format_backend_error(self, res: ToolCallResult, lang: str) -> str:
        msgs = {
            "en": f"I attempted to execute `{res.tool_name}` (with {res.retry_count} automatic retries), but our backend scheduling service is experiencing a temporary outage. I have NOT confirmed this action yet—may I log a priority callback or connect you to our live support desk so your request isn't lost?",
            "hi": f"मैंने `{res.tool_name}` को पूरा करने का प्रयास किया ({res.retry_count} रीट्राई के साथ), लेकिन बैकएंड सिस्टम में तकनीकी समस्या के कारण यह अभी पूरा नहीं हो सका। मैंने इसे झूठा कन्फर्म नहीं किया है—क्या मैं आपकी कॉल सीनियर टीम को ट्रांसफर कर दूँ?",
            "te": f"నేను `{res.tool_name}` పూర్తి చేయడానికి ప్రయత్నించాను ({res.retry_count} రీట్రైలతో), కానీ బ్యాకెండ్ సర్వర్ సమస్య వల్ల అది ఇంకా కన్ఫర్మ్ కాలేదు. నేను మీకు వెంటనే మా సపోర్ట్ టీమ్‌ని కనెక్ట్ చేయమంటారా?",
            "ta": f"`{res.tool_name}` செயல்படுத்த முயற்சித்தேன், ஆனால் தொழில்நுட்ப கோளாறு காரணமாக அது இன்னும் உறுதியாகவில்லை. நான் உடனே எங்கள் பிரதிநிதியிடம் இணைக்கட்டுமா?",
            "ml": f"`{res.tool_name}` പൂർത്തിയാക്കാൻ ശ്രമിച്ചുവെങ്കിലും സെർവർ തകരാർ മൂലം അത് സ്ഥിരീകരിക്കാൻ കഴിഞ്ഞിട്ടില്ല. ഞാൻ ഉടൻ തന്നെ കസ്റ്റമർ സപ്പോർട്ട് ടീമുമായി കണക്റ്റ് ചെയ്യട്ടെ?",
            "kn": f"`{res.tool_name}` ಪೂರ್ಣಗೊಳಿಸಲು ಪ್ರಯತ್ನಿಸಿದೆ, ಆದರೆ ತಾಂತ್ರಿಕ ಸಮಸ್ಯೆಯಿಂದಾಗಿ ಅದು ಇನ್ನೂ ದೃಢೀಕರಿಸಲ್ಪಟ್ಟಿಲ್ಲ. ನಾನು ತಕ್ಷಣ ನಮ್ಮ ಸಪೋರ್ಟ್ ತಂಡಕ್ಕೆ ಕರೆ ವರ್ಗಾಯಿಸಲೇ?",
        }
        return msgs[lang]

    def _format_verified_success(self, res: ToolCallResult, lang: str) -> str:
        tname = res.tool_name
        out = res.output
        if tname in ["book_appointment_slot", "reschedule_appointment_slot"]:
            res_type = out.get("resource_type", "Visit")
            day = out.get("visit_date", "Saturday")
            tm = out.get("visit_time", "11:00 AM")
            is_resched = tname == "reschedule_appointment_slot"
            if lang == "hi":
                verb = "अपडेट और री-शेड्यूल" if is_resched else "सफलतापूर्वक बुक"
                return f"धन्यवाद! हमारी सिस्टम जांच के बाद आपकी {res_type} अपॉइंटमेंट {day} को {tm} बजे के लिए {verb} कर दी गई है। आपको व्हाट्सएप पर कन्फर्मेशन मिल जाएगा।"
            elif lang == "te":
                verb = "మార్చి రీ-షెడ్యూల్" if is_resched else "విజయవంతంగా బుక్"
                return f"ధన్యవాదాలు! సిస్టమ్‌లో పరిశీలించిన తర్వాత మీ {res_type} అపాయింట్‌మెంట్ {day} రోజున {tm} కి {verb} చేయబడింది."
            elif lang == "ta":
                verb = "மாற்றி அமைக்கப்பட்டது" if is_resched else "உறுதி செய்யப்பட்டது"
                return f"நன்றி! உங்கள் {res_type} அப்பாயின்ட்மென்ட் {day} அன்று {tm} மணிக்கு வெற்றிகரமாக {verb}."
            elif lang == "ml":
                verb = "പുതുക്കി നിശ്ചയിച്ചിട്ടുണ്ട്" if is_resched else "ബുക്ക് ചെയ്തിട്ടുണ്ട്"
                return f"നന്ദി! നിങ്ങളുടെ {res_type} അപ്പോയിന്റ്മെന്റ് {day} {tm}-ന് വിജയകരമായി {verb}."
            elif lang == "kn":
                verb = "ಬದಲಾಯಿಸಿ ಮರು-ನಿಗದಿಪಡಿಸಲಾಗಿದೆ" if is_resched else "ಯಶಸ್ವಿಯಾಗಿ ಬುಕ್ ಮಾಡಲಾಗಿದೆ"
                return f"ಧನ್ಯವಾದಗಳು! ನಿಮ್ಮ {res_type} ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಅನ್ನು {day} ರಂದು {tm} ಗೆ {verb}."
            else:
                verb = "updated and rescheduled in-place" if is_resched else "confirmed and booked"
                return f"Wonderful! After verifying slot availability, I have {verb} your {res_type} appointment for {day} at {tm}."

        if tname == "confirm_cod_order":
            oid = out.get("order_id", "COD-4421")
            slot = out.get("delivery_slot", "Morning")
            msgs = {
                "en": f"Thank you! I have verified and confirmed your order {oid} for dispatch in the {slot} window.",
                "hi": f"धन्यवाद! मैंने आपके ऑर्डर {oid} को {slot} डिलीवरी स्लॉट के लिए सफलतापूर्वक कन्फर्म कर दिया है।",
                "te": f"ధన్యవాదాలు! మీ ఆర్డర్ {oid} ని {slot} డెలివరీ కోసం విజయవంతంగా కన్ఫర్మ్ చేశాను.",
                "ta": f"நன்றி! உங்கள் ஆர்டர் {oid}, {slot} டெலிவரிக்காக உறுதி செய்யப்பட்டுள்ளது.",
                "ml": f"നന്ദി! നിങ്ങളുടെ ഓർഡർ {oid}, {slot} ഡെലിവറിക്കായി സ്ഥിരീകരിച്ചിട്ടുണ്ട്.",
                "kn": f"ಧನ್ಯವಾದಗಳು! ನಿಮ್ಮ ಆರ್ಡರ್ {oid} ಅನ್ನು {slot} ಡೆಲಿವರಿಗಾಗಿ ದೃಢೀಕರಿಸಲಾಗಿದೆ.",
            }
            return msgs[lang]

        if tname == "cancel_cod_order":
            oid = out.get("order_id", "COD-4421")
            reason = out.get("reason", "customer request")
            msgs = {
                "en": f"I have checked your order status and confirmed the cancellation of order {oid} (Reason: {reason}). You will receive an SMS confirmation shortly.",
                "hi": f"मैंने ऑर्डर स्टेटस की जाँच के बाद आपका ऑर्डर {oid} सफलतापूर्वक रद्द कर दिया है (कारण: {reason})।",
                "te": f"మీ ఆర్డర్ స్టేటస్ తనిఖీ చేసిన తర్వాత ఆర్డర్ {oid} ని రద్దు చేశాను (కారణం: {reason}).",
                "ta": f"உங்கள் ஆர்டர் {oid} வெற்றிகரமாக ரத்து செய்யப்பட்டது (காரணம்: {reason}).",
                "ml": f"നിങ്ങളുടെ ഓർഡർ {oid} വിജയകരമായി റദ്ദാക്കിയിട്ടുണ്ട് (കാരണം: {reason}).",
                "kn": f"ನಿಮ್ಮ ಆರ್ಡರ್ {oid} ಅನ್ನು ಯಶಸ್ವಿಯಾಗಿ ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ (ಕಾರಣ: {reason}).",
            }
            return msgs[lang]

        if tname == "modify_order_address":
            oid = out.get("order_id", "COD-4421")
            addr = out.get("new_address", "")
            pin = out.get("pincode", "")
            msgs = {
                "en": f"I have verified serviceability and updated the delivery address for order {oid} to {addr} (Pincode: {pin}).",
                "hi": f"मैंने पिनकोड सेवा की जाँच कर ली है और ऑर्डर {oid} का डिलीवरी पता अपडेट करके {addr} ({pin}) कर दिया है।",
                "te": f"పిన్‌కోడ్ సర్వీస్ తనిఖీ చేసి, ఆర్డర్ {oid} డెలివరీ చిరునామాను {addr} ({pin}) కి అప్‌డేట్ చేశాను.",
                "ta": f"ஆர்டர் {oid}-ன் டெலிவரி முகவரி {addr} ({pin}) என வெற்றிகரமாக மாற்றப்பட்டுள்ளது.",
                "ml": f"ഓർഡർ {oid}-ന്റെ ഡെലിവറി വിലാസം {addr} ({pin}) എന്നതിലേക്ക് അപ്ഡേറ്റ് ചെയ്തിട്ടുണ്ട്.",
                "kn": f"ಆರ್ಡರ್ {oid} ರ ಡೆಲಿವರಿ ವಿಳಾಸವನ್ನು {addr} ({pin}) ಗೆ ಯಶಸ್ವಿಯಾಗಿ ಅಪ್‌ಡೇಟ್ ಮಾಡಲಾಗಿದೆ.",
            }
            return msgs[lang]

        if tname == "calculate_emi_schedule":
            emi = out.get("monthly_emi_inr", 69000)
            lakhs = out.get("loan_amount_lakhs", 80.0)
            msgs = {
                "en": f"Based on our EMI calculator tool, for a loan of ₹{lakhs} Lakhs at 8.55% over 20 years, your estimated monthly EMI is ₹{emi:,}.",
                "hi": f"हमारे ईएमआई कैलकुलेटर के अनुसार, ₹{lakhs} लाख के लोन पर 8.55% ब्याज दर से 20 वर्षों के लिए आपकी मासिक ईएमआई लगभग ₹{emi:,} होगी।",
                "te": f"మా EMI క్యాలిక్యులేటర్ ప్రకారం, ₹{lakhs} లక్షల లోన్‌పై 8.55% వడ్డీతో 20 ఏళ్లకు మీ నెలవారీ EMI సుమారు ₹{emi:,} అవుతుంది.",
                "ta": f"எங்கள் இஎம்ஐ கால்குலேட்டரின்படி, ₹{lakhs} லட்சம் கடனுக்கு 8.55% வட்டியில் 20 ஆண்டுகளுக்கு மாத இஎம்ஐ ₹{emi:,} ஆகும்.",
                "ml": f"ഞങ്ങളുടെ ഇഎംഐ കാൽക്കുലേറ്റർ പ്രകാരം ₹{lakhs} ലക്ഷം ലോണിന് 8.55% പലിശ നിരക്കിൽ 20 വർഷത്തേക്ക് പ്രതിമാസ ഇഎംഐ ₹{emi:,} ആണ്.",
                "kn": f"ನಮ್ಮ ಇಎಂಐ ಕ್ಯಾಲ್ಕುಲೇಟರ್ ಪ್ರಕಾರ, ₹{lakhs} ಲಕ್ಷ ಸಾಲಕ್ಕೆ 8.55% ಬಡ್ಡಿದರದಲ್ಲಿ 20 ವರ್ಷಗಳಿಗೆ ನಿಮ್ಮ ಮಾಸಿಕ ಇಎಂಐ ₹{emi:,} ಆಗಿರುತ್ತದೆ.",
            }
            return msgs[lang]

        return out.get("summary", "Action completed successfully.")
