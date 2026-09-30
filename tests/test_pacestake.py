import pytest
import json
from .conftest import sim_installMocks


def _to_hex(addr) -> str:
    """Helper to convert test address to lowercase hex."""
    if hasattr(addr, "as_hex"):
        return addr.as_hex.lower()
    if isinstance(addr, bytes):
        return "0x" + addr.hex().lower()
    return str(addr).lower()


def setup_post_message_hook(direct_vm):
    """Intercept cross-contract calls / emit_transfer to track recipient balances in tests."""
    def post_message_hook(vm, request):
        if "PostMessage" in request:
            pm = request["PostMessage"]
            dest_addr = pm["address"]
            value = int(pm.get("value", 0))
            dest_bytes = vm._to_bytes(dest_addr)
            vm._balances[dest_bytes] = vm._balances.get(dest_bytes, 0) + value
            return {"ok": None}
        return None

    direct_vm._gl_call_hook = post_message_hook


def test_init_and_default_views(direct_vm, direct_deploy, direct_owner, direct_bob):
    """Verify deployment state initialization and default public views with zero-arg constructor."""
    setup_post_message_hook(direct_vm)
    direct_vm.sender = direct_owner

    contract = direct_deploy("contracts/contract.py")

    assert contract.get_owner().lower() == _to_hex(direct_owner)
    assert contract.get_min_stake() == 500
    assert contract.get_challenge_count() == 0
    assert contract.get_treasury_balance() == 0
    assert contract.get_total_active_staked() == 0

    stats = json.loads(contract.get_stats())
    assert stats["owner"].lower() == _to_hex(direct_owner)
    assert stats["min_stake"] == 500
    assert stats["total_challenges"] == 0
    assert stats["treasury_balance"] == 0
    assert stats["total_active_staked"] == 0

    # Test set_min_stake
    # Non-owner cannot change min stake
    direct_vm.sender = direct_bob
    with pytest.raises(Exception) as excinfo:
        contract.set_min_stake(1000)
    assert "Only owner can set min stake" in str(excinfo.value)

    # Owner updates min stake
    direct_vm.sender = direct_owner
    contract.set_min_stake(1000)
    assert contract.get_min_stake() == 1000


def test_create_challenge_validation_and_success(direct_vm, direct_deploy, direct_owner, direct_alice):
    """Verify creation constraints: minimum stake, string lengths, and deadline timestamp."""
    setup_post_message_hook(direct_vm)
    contract = direct_deploy("contracts/contract.py")

    direct_vm.sender = direct_alice

    # 1. Stake below min_stake
    direct_vm.value = 200
    with pytest.raises(Exception) as excinfo:
        contract.create_challenge("Alice Runner", "RUNNING", "Sub-4 Marathon (42.195 km)", 1893456000)
    assert "Stake amount must be at least 500 wei" in str(excinfo.value)

    # 2. Athlete name too short
    direct_vm.value = 1000
    with pytest.raises(Exception) as excinfo:
        contract.create_challenge("A", "RUNNING", "Sub-4 Marathon (42.195 km)", 1893456000)
    assert "Athlete name must be at least 2 characters" in str(excinfo.value)

    # 3. Target metric description too short
    with pytest.raises(Exception) as excinfo:
        contract.create_challenge("Alice Runner", "RUNNING", "1k", 1893456000)
    assert "Target metric description is too short" in str(excinfo.value)

    # 4. Non-positive deadline timestamp
    with pytest.raises(Exception) as excinfo:
        contract.create_challenge("Alice Runner", "RUNNING", "Sub-4 Marathon (42.195 km)", 0)
    assert "Deadline timestamp must be positive" in str(excinfo.value)

    # 5. Successful challenge creation
    cid = contract.create_challenge("Alice Runner", "RUNNING", "Sub-4 Marathon (42.195 km)", 1893456000)
    assert cid == "1"
    assert contract.get_challenge_count() == 1
    assert contract.get_total_active_staked() == 1000

    c_info = json.loads(contract.get_challenge(cid))
    assert c_info["id"] == "1"
    assert c_info["creator"].lower() == _to_hex(direct_alice)
    assert c_info["athlete_name"] == "Alice Runner"
    assert c_info["activity_type"] == "RUNNING"
    assert c_info["target_metric"] == "Sub-4 Marathon (42.195 km)"
    assert c_info["stake_amount"] == "1000"
    assert c_info["evidence_url"] == ""
    assert c_info["status"] == "ACTIVE"
    assert c_info["verdict"] == "PENDING"


def test_submit_proof_validation(direct_vm, direct_deploy, direct_alice, direct_bob):
    """Verify proof submission security checks and status update."""
    setup_post_message_hook(direct_vm)
    contract = direct_deploy("contracts/contract.py")

    # Alice creates challenge
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    cid = contract.create_challenge("Alice Runner", "RUNNING", "Run 10 km under 50 mins", 1893456000)
    direct_vm.value = 0

    # 1. Non-existent challenge
    with pytest.raises(Exception) as excinfo:
        contract.submit_proof("999", "https://strava.com/activities/12345")
    assert "Challenge not found" in str(excinfo.value)

    # 2. Non-creator attempts to submit proof
    direct_vm.sender = direct_bob
    with pytest.raises(Exception) as excinfo:
        contract.submit_proof(cid, "https://strava.com/activities/12345")
    assert "Only the challenge creator can submit proof" in str(excinfo.value)

    # 3. Invalid URL schema (not http or https)
    direct_vm.sender = direct_alice
    with pytest.raises(Exception) as excinfo:
        contract.submit_proof(cid, "ftp://strava.com/activities/12345")
    assert "evidence_url must start with http:// or https://" in str(excinfo.value)

    # 4. Successful submission
    contract.submit_proof(cid, "https://strava.com/activities/12345")
    c_info = json.loads(contract.get_challenge(cid))
    assert c_info["status"] == "EVIDENCE_SUBMITTED"
    assert c_info["evidence_url"] == "https://strava.com/activities/12345"

    # 5. Cannot resubmit proof once status is no longer ACTIVE
    with pytest.raises(Exception) as excinfo:
        contract.submit_proof(cid, "https://strava.com/activities/99999")
    assert "Cannot submit proof for challenge with status 'EVIDENCE_SUBMITTED'" in str(excinfo.value)


def test_case_1_adjudicate_challenge_achieved_full_refund(direct_vm, direct_deploy, direct_alice):
    """
    Test Case 1: Target metric achieved on legitimate activity URL.
    Consensus verdict: ACHIEVED -> 100% stake refunded to athlete via emit_transfer.
    """
    setup_post_message_hook(direct_vm)
    contract = direct_deploy("contracts/contract.py")

    # Alice creates a marathon challenge with 5,000 wei stake
    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    cid = contract.create_challenge("Alice Runner", "RUNNING", "Marathon 42.195 km under 4 hours", 1893456000)
    direct_vm.value = 0

    evidence_url = "https://strava.com/activities/marathon-sub4-proof"
    contract.submit_proof(cid, evidence_url)

    # Install bare dict mocks via sim_installMocks
    sim_installMocks(
        {
            "web_mocks": {
                r".*strava\.com/activities/marathon-sub4-proof.*": (
                    "Strava Activity: Berlin Marathon Official Run. Athlete: Alice Runner. "
                    "Sport: Running. Distance: 42.25 km. Elapsed Time: 3h 48m 12s. "
                    "Elevation: 45m. Date: 2026-09-15. Status: Verified GPS tracking."
                )
            },
            "llm_mocks": {
                "verdict": "ACHIEVED",
                "confidence": 96,
                "reason": "Alice Runner completed 42.25 km in 3h 48m 12s, fulfilling the sub-4 marathon requirement.",
            },
        },
        vm=direct_vm,
    )

    # Verify initial balances before adjudication
    alice_bytes = direct_vm._to_bytes(direct_alice)
    direct_vm.deal(direct_alice, 0)
    assert direct_vm._balances.get(alice_bytes, 0) == 0

    # Execute autonomous AI adjudication
    contract.adjudicate_challenge(cid)

    # Verify status, verdict, and 100% refund to Alice
    c_info = json.loads(contract.get_challenge(cid))
    assert c_info["status"] == "COMPLETED"
    assert c_info["verdict"] == "ACHIEVED"
    assert c_info["confidence"] == 96
    assert "Alice Runner completed 42.25 km" in c_info["reason"]

    # 100% Stake refunded to Alice
    assert direct_vm._balances.get(alice_bytes, 0) == 5000
    assert contract.get_total_active_staked() == 0
    assert contract.get_treasury_balance() == 0


def test_case_2_adjudicate_challenge_failed_slashed_to_treasury(direct_vm, direct_deploy, direct_bob):
    """
    Test Case 2: Incomplete metric or fraudulent data.
    Consensus verdict: FAILED -> 100% stake slashed into treasury_balance.
    """
    setup_post_message_hook(direct_vm)
    contract = direct_deploy("contracts/contract.py")

    # Bob creates a cycling challenge with 2,500 wei stake
    direct_vm.sender = direct_bob
    direct_vm.value = 2500
    cid = contract.create_challenge("Bob Cyclist", "CYCLING", "Century Ride: 100 km cycling", 1893456000)
    direct_vm.value = 0

    evidence_url = "https://garmin.connect/activity/bob-ride-short"
    contract.submit_proof(cid, evidence_url)

    # Install bare dict mocks via sim_installMocks
    sim_installMocks(
        {
            "web_mocks": {
                r".*garmin\.connect/activity/bob-ride-short.*": (
                    "Garmin Connect Ride. Athlete: Bob Cyclist. Activity: Cycling. "
                    "Distance: 34.2 km. Time: 1h 15m. Workout completed."
                )
            },
            "llm_mocks": {
                "verdict": "FAILED",
                "confidence": 92,
                "reason": "Bob only completed 34.2 km out of the required 100 km century ride.",
            },
        },
        vm=direct_vm,
    )

    bob_bytes = direct_vm._to_bytes(direct_bob)
    direct_vm.deal(direct_bob, 0)

    contract.adjudicate_challenge(cid)

    c_info = json.loads(contract.get_challenge(cid))
    assert c_info["status"] == "FORFEITED"
    assert c_info["verdict"] == "FAILED"
    assert c_info["confidence"] == 92

    # Bob does NOT get refund; 2,500 wei is slashed into treasury
    assert direct_vm._balances.get(bob_bytes, 0) == 0
    assert contract.get_treasury_balance() == 2500
    assert contract.get_total_active_staked() == 0


def test_case_3_adjudicate_challenge_web_404_broken_link(direct_vm, direct_deploy, direct_bob):
    """
    Test Case 3: URL 404 / broken link edge case.
    Web scraper detects 404 and consensus safely forfeits stake.
    """
    setup_post_message_hook(direct_vm)
    contract = direct_deploy("contracts/contract.py")

    direct_vm.sender = direct_bob
    direct_vm.value = 1000
    cid = contract.create_challenge("Bob Cyclist", "CYCLING", "Ride 50 km", 1893456000)
    direct_vm.value = 0

    evidence_url = "https://strava.com/activities/deleted-activity-404"
    contract.submit_proof(cid, evidence_url)

    # Install 404 mock via sim_installMocks
    sim_installMocks(
        {
            "web_mocks": {
                r".*strava\.com/activities/deleted-activity-404.*": {
                    "status": 404,
                    "body": "404 Not Found - The requested activity could not be found or has been deleted.",
                }
            }
        },
        vm=direct_vm,
    )

    contract.adjudicate_challenge(cid)

    c_info = json.loads(contract.get_challenge(cid))
    assert c_info["status"] == "FORFEITED"
    assert c_info["verdict"] == "FAILED"
    assert "404" in c_info["reason"]
    assert contract.get_treasury_balance() == 1000


def test_case_4_low_confidence_fallback(direct_vm, direct_deploy, direct_alice):
    """
    Test Case 4: Low confidence (< 60%) failsafe.
    Even if LLM claims ACHIEVED, confidence < 60 overrides verdict to FAILED.
    """
    setup_post_message_hook(direct_vm)
    contract = direct_deploy("contracts/contract.py")

    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    cid = contract.create_challenge("Alice Runner", "RUNNING", "Run 10 km", 1893456000)
    direct_vm.value = 0

    evidence_url = "https://strava.com/activities/unclear-run"
    contract.submit_proof(cid, evidence_url)

    # Mock ambiguous web content and low confidence LLM response
    sim_installMocks(
        {
            "web_mocks": {
                r".*strava\.com/activities/unclear-run.*": (
                    "Activity: Morning exercise. Athlete: Unknown User. Distance: 10 km."
                )
            },
            "llm_mocks": {
                "verdict": "ACHIEVED",
                "confidence": 45,  # Low confidence below 60 threshold
                "reason": "Distance matches but user identity is unclear.",
            },
        },
        vm=direct_vm,
    )

    contract.adjudicate_challenge(cid)

    c_info = json.loads(contract.get_challenge(cid))
    assert c_info["status"] == "FORFEITED"
    assert c_info["verdict"] == "FAILED"
    assert "low_confidence" in c_info["reason"]


def test_cannot_adjudicate_unready_or_already_resolved(direct_vm, direct_deploy, direct_alice):
    """Verify state machine integrity: cannot adjudicate active or already finalized challenges."""
    setup_post_message_hook(direct_vm)
    contract = direct_deploy("contracts/contract.py")

    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    cid = contract.create_challenge("Alice Runner", "RUNNING", "Run 10 km", 1893456000)
    direct_vm.value = 0

    # 1. Adjudicating when status is ACTIVE (no proof submitted yet)
    with pytest.raises(Exception) as excinfo:
        contract.adjudicate_challenge(cid)
    assert "Challenge must be in 'EVIDENCE_SUBMITTED' status before adjudication" in str(excinfo.value)


def test_withdraw_treasury(direct_vm, direct_deploy, direct_owner, direct_bob, direct_charlie):
    """Verify owner treasury withdrawal rights and balance integrity."""
    setup_post_message_hook(direct_vm)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/contract.py")

    # Bob creates challenge and forfeits
    direct_vm.sender = direct_bob
    direct_vm.value = 3000
    cid = contract.create_challenge("Bob Cyclist", "CYCLING", "Ride 100 km", 1893456000)
    direct_vm.value = 0

    contract.submit_proof(cid, "https://strava.com/activities/failed-ride")
    sim_installMocks(
        {
            "web_mocks": {
                r".*strava\.com/activities/failed-ride.*": {
                    "status": 404,
                    "body": "404 Not Found",
                }
            }
        },
        vm=direct_vm,
    )
    contract.adjudicate_challenge(cid)
    assert contract.get_treasury_balance() == 3000

    # 1. Non-owner tries to withdraw
    direct_vm.sender = direct_bob
    with pytest.raises(Exception) as excinfo:
        contract.withdraw_treasury(_to_hex(direct_bob), 1000)
    assert "Only owner can withdraw treasury funds" in str(excinfo.value)

    # 2. Owner tries to withdraw zero
    direct_vm.sender = direct_owner
    with pytest.raises(Exception) as excinfo:
        contract.withdraw_treasury(_to_hex(direct_charlie), 0)
    assert "Withdrawal amount must be greater than 0" in str(excinfo.value)

    # 3. Owner tries to withdraw more than treasury balance
    with pytest.raises(Exception) as excinfo:
        contract.withdraw_treasury(_to_hex(direct_charlie), 5000)
    assert "Insufficient treasury balance" in str(excinfo.value)

    # 4. Successful withdrawal to charity/community recipient Charlie
    charlie_bytes = direct_vm._to_bytes(direct_charlie)
    direct_vm.deal(direct_charlie, 0)

    contract.withdraw_treasury(_to_hex(direct_charlie), 2000)
    assert contract.get_treasury_balance() == 1000
    assert direct_vm._balances.get(charlie_bytes, 0) == 2000


def test_create_challenge_past_deadline_reverts(direct_vm, direct_deploy, direct_owner, direct_bob):
    """Verify challenge cannot be created with a deadline in the past or present."""
    setup_post_message_hook(direct_vm)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/contract.py")

    # Set virtual block datetime to 2026-06-01T12:00:00Z (timestamp 1780315200)
    direct_vm.warp("2026-06-01T12:00:00Z")
    current_ts = contract.get_current_time()
    assert current_ts > 0

    direct_vm.sender = direct_bob
    direct_vm.value = 1000

    # Attempt to create with deadline equal to or earlier than current timestamp
    with pytest.raises(Exception) as excinfo:
        contract.create_challenge("Bob", "RUNNING", "10k run", current_ts - 100)
    assert "Deadline must be strictly in the future" in str(excinfo.value)

    with pytest.raises(Exception) as excinfo:
        contract.create_challenge("Bob", "RUNNING", "10k run", current_ts)
    assert "Deadline must be strictly in the future" in str(excinfo.value)


def test_submit_proof_after_deadline_reverts(direct_vm, direct_deploy, direct_owner, direct_bob):
    """Verify proof cannot be submitted after the stored deadline has passed."""
    setup_post_message_hook(direct_vm)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/contract.py")

    # Start at 2026-06-01T10:00:00Z
    direct_vm.warp("2026-06-01T10:00:00Z")
    now_ts = contract.get_current_time()
    deadline = now_ts + 3600  # 1 hour deadline

    direct_vm.sender = direct_bob
    direct_vm.value = 2000
    cid = contract.create_challenge("Bob", "RUNNING", "Half Marathon", deadline)
    direct_vm.value = 0

    # Warp past deadline (1 hour + 5 minutes later)
    direct_vm.warp("2026-06-01T11:05:00Z")
    assert contract.get_current_time() > deadline

    # Attempt to submit proof after deadline
    with pytest.raises(Exception) as excinfo:
        contract.submit_proof(cid, "https://strava.com/activities/late-submission")
    assert "Challenge deadline has passed" in str(excinfo.value)


def test_expire_challenge_before_deadline_reverts(direct_vm, direct_deploy, direct_owner, direct_bob, direct_charlie):
    """Verify expire_challenge cannot be invoked before the deadline has elapsed."""
    setup_post_message_hook(direct_vm)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/contract.py")

    direct_vm.warp("2026-06-01T10:00:00Z")
    now_ts = contract.get_current_time()
    deadline = now_ts + 7200  # 2 hours deadline

    direct_vm.sender = direct_bob
    direct_vm.value = 1500
    cid = contract.create_challenge("Bob", "RUNNING", "15k run", deadline)
    direct_vm.value = 0

    # Advance time, but still before deadline (1 hour later)
    direct_vm.warp("2026-06-01T11:00:00Z")

    # Charlie (or anyone) attempts to expire before deadline
    direct_vm.sender = direct_charlie
    with pytest.raises(Exception) as excinfo:
        contract.expire_challenge(cid)
    assert "Challenge deadline has not passed yet" in str(excinfo.value)


def test_expire_challenge_success_and_accounting_exactly_once(direct_vm, direct_deploy, direct_owner, direct_bob, direct_charlie):
    """Verify bounded terminal path settles abandoned stake and updates accounting exactly once."""
    setup_post_message_hook(direct_vm)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/contract.py")

    direct_vm.warp("2026-06-01T10:00:00Z")
    now_ts = contract.get_current_time()
    deadline = now_ts + 3600  # 1 hour deadline

    initial_treasury = contract.get_treasury_balance()
    initial_active = contract.get_total_active_staked()

    # Bob creates challenge pledging 4,000 wei
    direct_vm.sender = direct_bob
    direct_vm.value = 4000
    cid = contract.create_challenge("Bob", "CYCLING", "Century 100km", deadline)
    direct_vm.value = 0

    assert contract.get_total_active_staked() == initial_active + 4000
    assert contract.get_treasury_balance() == initial_treasury

    # Bob NEVER submits proof. Deadline passes. Warp 2 hours into future.
    direct_vm.warp("2026-06-01T12:00:00Z")
    assert contract.get_current_time() > deadline

    # Charlie (or any keeper/user) triggers bounded terminal path
    direct_vm.sender = direct_charlie
    contract.expire_challenge(cid)

    # Verify state and single accounting update
    challenge_data = json.loads(contract.get_challenge(cid))
    assert challenge_data["status"] == "EXPIRED_FORFEITED"
    assert challenge_data["verdict"] == "EXPIRED"
    assert challenge_data["confidence"] == 100
    assert int(challenge_data["stake_amount"]) == 0
    assert "Challenge expired without proof submission" in challenge_data["reason"]

    # Accounting assertions: active stake decreased, treasury increased by exactly 4,000 wei
    assert contract.get_total_active_staked() == initial_active
    assert contract.get_treasury_balance() == initial_treasury + 4000

    # Verify IDEMPOTENCY / EXACTLY ONCE: Attempting to expire again must fail
    with pytest.raises(Exception) as excinfo:
        contract.expire_challenge(cid)
    assert "Cannot expire challenge with status 'EXPIRED_FORFEITED'" in str(excinfo.value)

