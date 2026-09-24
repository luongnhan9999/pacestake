# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json

try:
    UserError = UserError
except NameError:
    try:
        from genlayer.gl.vm import UserError
    except ImportError:
        class UserError(Exception):
            pass


def _addr_str(addr: Address) -> str:
    """Helper to convert Address safely to lowercase hex string."""
    try:
        return addr.as_hex.lower()
    except Exception:
        return str(addr).lower()


def _clean_llm_json(text) -> dict:
    """Safely parse LLM output, stripping markdown code fences if present."""
    if isinstance(text, dict):
        return text
    if hasattr(text, "content") and isinstance(text.content, dict):
        return text.content
    raw_str = text.content if hasattr(text, "content") else str(text)
    try:
        cleaned = str(raw_str).strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())
    except Exception as e:
        return {"verdict": "FAILED", "confidence": 0, "reason": f"JSON parse error: {str(e)[:100]}"}


@allow_storage
@dataclass
class FitnessChallenge:
    id: str
    creator: Address
    athlete_name: str
    activity_type: str
    target_metric: str
    stake_amount: bigint
    evidence_url: str
    deadline_timestamp: bigint
    status: str
    verdict: str
    confidence: bigint
    reason: str
    created_at: bigint


class Contract(gl.Contract):
    owner: Address
    challenges: TreeMap[str, FitnessChallenge]
    next_challenge_id: bigint
    min_stake: bigint
    treasury_balance: bigint
    total_active_staked: bigint

    def __init__(self):
        """Initialize PaceStake with standard no-arg constructor."""
        self.owner = gl.message.sender_address
        self.next_challenge_id = bigint(1)
        self.min_stake = bigint(500)
        self.treasury_balance = bigint(0)
        self.total_active_staked = bigint(0)

    @gl.public.write.payable
    def create_challenge(
        self,
        athlete_name: str,
        activity_type: str,
        target_metric: str,
        deadline_timestamp: int,
    ) -> str:
        """Create a new sports discipline commitment challenge with a staked pledge in GEN."""
        stake = bigint(gl.message.value)
        if stake < self.min_stake:
            raise UserError(f"Stake amount must be at least {self.min_stake} wei")

        athlete_name = athlete_name.strip()
        if len(athlete_name) < 2:
            raise UserError("Athlete name must be at least 2 characters")

        activity_type = activity_type.strip().upper()
        if not activity_type:
            raise UserError("Activity type cannot be empty")

        target_metric = target_metric.strip()
        if len(target_metric) < 3:
            raise UserError("Target metric description is too short")

        if deadline_timestamp <= 0:
            raise UserError("Deadline timestamp must be positive")

        cid = str(self.next_challenge_id)
        self.next_challenge_id += bigint(1)
        self.total_active_staked += stake

        challenge = FitnessChallenge(
            id=cid,
            creator=gl.message.sender_address,
            athlete_name=athlete_name,
            activity_type=activity_type,
            target_metric=target_metric,
            stake_amount=stake,
            evidence_url="",
            deadline_timestamp=bigint(deadline_timestamp),
            status="ACTIVE",
            verdict="PENDING",
            confidence=bigint(0),
            reason="Challenge created. Awaiting activity completion and proof submission.",
            created_at=bigint(1),
        )

        self.challenges[cid] = challenge
        return cid

    @gl.public.write
    def submit_proof(self, challenge_id: str, evidence_url: str) -> None:
        """Submit a public activity URL (Strava, Garmin, Race result) as proof of achievement."""
        if challenge_id not in self.challenges:
            raise UserError("Challenge not found")

        challenge = self.challenges[challenge_id]
        sender_hex = _addr_str(gl.message.sender_address)
        creator_hex = _addr_str(challenge.creator)

        if sender_hex != creator_hex:
            raise UserError("Only the challenge creator can submit proof")

        if challenge.status != "ACTIVE":
            raise UserError(f"Cannot submit proof for challenge with status '{challenge.status}'")

        url = evidence_url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise UserError("evidence_url must start with http:// or https://")

        challenge.evidence_url = url
        challenge.status = "EVIDENCE_SUBMITTED"
        challenge.reason = "Proof submitted. Ready for autonomous AI adjudication."
        self.challenges[challenge_id] = challenge

    @gl.public.write
    def adjudicate_challenge(self, challenge_id: str) -> None:
        """Trigger autonomous decentralized AI consensus to audit proof and settle escrow."""
        if challenge_id not in self.challenges:
            raise UserError("Challenge not found")

        challenge = self.challenges[challenge_id]

        if challenge.status != "EVIDENCE_SUBMITTED":
            raise UserError(
                f"Challenge must be in 'EVIDENCE_SUBMITTED' status before adjudication, currently '{challenge.status}'"
            )

        if not challenge.evidence_url:
            raise UserError("Evidence URL is missing")

        # Capture storage state into local variables before nondeterministic closure
        evidence_url_local = str(challenge.evidence_url)
        athlete_name_local = str(challenge.athlete_name)
        activity_type_local = str(challenge.activity_type)
        target_metric_local = str(challenge.target_metric)
        deadline_timestamp_local = int(str(challenge.deadline_timestamp))

        def leader_fn() -> dict:
            try:
                res_web = gl.nondet.web.render(evidence_url_local, mode="text")
                page_text = res_web.content if hasattr(res_web, "content") else str(res_web)
                if not page_text or len(page_text.strip()) < 30:
                    return {
                        "verdict": "FAILED",
                        "confidence": 95,
                        "reason": "Evidence URL returned empty or inaccessible content",
                    }
                lower_sample = page_text[:500].lower()
                if any(err in lower_sample for err in ["404 not found", "error 404", "page not found", "activity not found"]):
                    return {
                        "verdict": "FAILED",
                        "confidence": 95,
                        "reason": "Evidence URL returned 404/Activity Not Found",
                    }
            except Exception as e:
                return {
                    "verdict": "FAILED",
                    "confidence": 95,
                    "reason": f"Web fetch failed: {str(e)[:100]}",
                }

            prompt = f"""SYSTEM: You are an impartial Autonomous Sports Discipline & Marathon Adjudicator.
Adjudicate whether the athlete achieved their fitness commitment based strictly on the web evidence.

ATHLETE COMMITMENT:
- Athlete Name: {athlete_name_local}
- Activity Type: {activity_type_local}
- Target Metric: {target_metric_local}
- Deadline Timestamp: {deadline_timestamp_local}

EVIDENCE CONTENT:
{page_text[:3500]}

VERIFICATION PROTOCOL:
1. Verify legitimate sports activity data (Strava, Garmin, Race boards).
2. Athlete Identity Match: Does the athlete name match '{athlete_name_local}'?
3. Sport & Metric: Did distance, time, or pace meet or exceed '{target_metric_local}'?
4. Timeline: Did the activity occur before deadline {deadline_timestamp_local}?

DECISION RULES:
- If all criteria satisfied: verdict = "ACHIEVED".
- If target metric not met, identity mismatch, or link invalid: verdict = "FAILED".

Output strict JSON only:
{{"verdict": "ACHIEVED"|"FAILED", "confidence": <0-100>, "reason": "<concise reason max 200 chars>"}}"""

            try:
                raw_res = gl.nondet.exec_prompt(prompt, response_format="json")
                parsed = _clean_llm_json(raw_res)
                verdict = str(parsed.get("verdict", "FAILED")).strip().upper()
                if verdict not in ("ACHIEVED", "FAILED"):
                    verdict = "FAILED"

                try:
                    conf = int(parsed.get("confidence", 0))
                except Exception:
                    conf = 50

                reason = str(parsed.get("reason", "Evaluated by AI Council"))[:200]
                if conf < 60 and verdict == "ACHIEVED":
                    verdict = "FAILED"
                    reason = f"[low_confidence: {conf}%] Inconclusive proof: " + reason

                return {"verdict": verdict, "confidence": conf, "reason": reason}
            except Exception as e:
                return {"verdict": "FAILED", "confidence": 0, "reason": f"LLM error: {str(e)[:100]}"}

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False

            leader_data = leader_res.calldata if hasattr(leader_res, "calldata") else leader_res
            if not isinstance(leader_data, dict):
                leader_data = _clean_llm_json(leader_data)

            leader_verdict = str(leader_data.get("verdict", "")).strip().upper()
            if leader_verdict not in ("ACHIEVED", "FAILED"):
                return False

            my_data = leader_fn()
            my_verdict = str(my_data.get("verdict", "")).strip().upper()

            # Compare core semantic verdict only
            return leader_verdict == my_verdict

        result_raw = gl.vm.run_nondet(leader_fn, validator_fn)
        result = _clean_llm_json(result_raw)

        verdict = str(result.get("verdict", "FAILED")).strip().upper()
        if verdict not in ("ACHIEVED", "FAILED"):
            verdict = "FAILED"

        try:
            confidence = int(result.get("confidence", 0))
        except Exception:
            confidence = 0

        reason = str(result.get("reason", "Consensus adjudication completed"))

        challenge.verdict = verdict
        challenge.confidence = bigint(confidence)
        challenge.reason = reason

        stake_amt = challenge.stake_amount
        creator_addr = challenge.creator

        if self.total_active_staked >= stake_amt:
            self.total_active_staked -= stake_amt
        else:
            self.total_active_staked = bigint(0)

        if verdict == "ACHIEVED":
            challenge.status = "COMPLETED"
            self.challenges[challenge_id] = challenge
            gl.get_contract_at(creator_addr).emit_transfer(value=u256(stake_amt))
        else:
            challenge.status = "FORFEITED"
            self.treasury_balance += stake_amt
            self.challenges[challenge_id] = challenge

    @gl.public.write
    def withdraw_treasury(self, recipient: str, amount: int) -> None:
        """Allow contract owner to withdraw forfeited stakes for sports charities / community rewards."""
        sender_hex = _addr_str(gl.message.sender_address)
        owner_hex = _addr_str(self.owner)
        if sender_hex != owner_hex:
            raise UserError("Only owner can withdraw treasury funds")

        if amount <= 0:
            raise UserError("Withdrawal amount must be greater than 0")

        amt = bigint(amount)
        if amt > self.treasury_balance:
            raise UserError("Insufficient treasury balance")

        recipient_addr = Address(recipient)
        self.treasury_balance -= amt
        gl.get_contract_at(recipient_addr).emit_transfer(value=u256(amt))

    @gl.public.write
    def set_min_stake(self, new_min_stake: int) -> None:
        """Allow contract owner to update the minimum required stake."""
        sender_hex = _addr_str(gl.message.sender_address)
        owner_hex = _addr_str(self.owner)
        if sender_hex != owner_hex:
            raise UserError("Only owner can set min stake")
        if new_min_stake <= 0:
            raise UserError("Min stake must be positive")
        self.min_stake = bigint(new_min_stake)

    @gl.public.view
    def get_challenge(self, challenge_id: str) -> str:
        """Retrieve full details of a fitness challenge as a JSON string."""
        if challenge_id not in self.challenges:
            raise UserError("Challenge not found")

        c = self.challenges[challenge_id]
        data = {
            "id": str(c.id),
            "creator": _addr_str(c.creator),
            "athlete_name": str(c.athlete_name),
            "activity_type": str(c.activity_type),
            "target_metric": str(c.target_metric),
            "stake_amount": str(c.stake_amount),
            "evidence_url": str(c.evidence_url),
            "deadline_timestamp": str(c.deadline_timestamp),
            "status": str(c.status),
            "verdict": str(c.verdict),
            "confidence": int(str(c.confidence)),
            "reason": str(c.reason),
            "created_at": str(c.created_at),
        }
        return json.dumps(data)

    @gl.public.view
    def get_stats(self) -> str:
        """Get high-level protocol statistics as a JSON string."""
        stats = {
            "owner": _addr_str(self.owner),
            "total_challenges": int(str(self.next_challenge_id)) - 1,
            "min_stake": int(str(self.min_stake)),
            "treasury_balance": int(str(self.treasury_balance)),
            "total_active_staked": int(str(self.total_active_staked)),
        }
        return json.dumps(stats)

    @gl.public.view
    def get_challenge_count(self) -> int:
        return int(str(self.next_challenge_id)) - 1

    @gl.public.view
    def get_treasury_balance(self) -> int:
        return int(str(self.treasury_balance))

    @gl.public.view
    def get_total_active_staked(self) -> int:
        return int(str(self.total_active_staked))

    @gl.public.view
    def get_min_stake(self) -> int:
        return int(str(self.min_stake))

    @gl.public.view
    def get_owner(self) -> str:
        return _addr_str(self.owner)
