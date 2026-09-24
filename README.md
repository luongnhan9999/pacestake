# 🏃‍♂️ PaceStake: Autonomous Fitness Commitment & Discipline Escrow

> **Track:** Future of Work / Subjective Consensus / Onchain Justice  
> **Network Target:** GenLayer Studionet (`https://studio.genlayer.com`)  
> **Consensus Engine:** Optimistic Democracy with Semantic Verdict AI Consensus (`gl.vm.run_nondet`)  

---

## 🌟 Executive Summary

**PaceStake** is a decentralized, autonomous discipline escrow protocol built on **GenLayer**. It transforms fitness commitments (such as marathon training, distance targets, and personal athletic challenges) into financially backed, self-enforcing smart contracts.

### Why PaceStake Dies Without GenLayer (The Fit)
- **Traditional Web2 Fitness Apps:** Centralized, vulnerable to platform manipulation, lack trustless monetary escrow, or extract heavy commission cuts.
- **Traditional Web3 Smart Contracts (Solidity / EVM):** Blind to off-chain athletic achievements. They cannot fetch or inspect Strava activities, Garmin Connect links, or marathon timing leaderboards without relying on centralized, expensive, and fragile oracles.
- **The GenLayer Breakthrough:** PaceStake leverages GenVM's native on-chain web scraping (`gl.nondet.web.render`) combined with decentralized AI consensus (`gl.nondet.exec_prompt` wrapped in `gl.vm.run_nondet`). An autonomous AI jury independently audits the athlete's name, sport type, distance, elapsed time, and GPS timestamp integrity directly from public web proof, reaching consensus on the **true semantic verdict**.

---

## 🏗️ Architecture & Mechanism

```
                   +-----------------------------------------------+
                   |                ATHLETE / USER                 |
                   +-----------------------------------------------+
                                          |
                      1. create_challenge (pledge stake in GEN)
                                          v
                   +-----------------------------------------------+
                   |        PaceStake Intelligent Contract         |
                   |           (Status: ACTIVE, Escrowed)          |
                   +-----------------------------------------------+
                                          |
                      2. submit_proof (public Strava/Garmin URL)
                                          v
                   +-----------------------------------------------+
                   |        PaceStake Intelligent Contract         |
                   |          (Status: EVIDENCE_SUBMITTED)         |
                   +-----------------------------------------------+
                                          |
                      3. adjudicate_challenge()
                                          v
      +-----------------------------------------------------------------------+
      |               Decentralized AI Jury Consensus (GenVM)                 |
      |                                                                       |
      |  Leader & Validators run independently:                               |
      |  - gl.nondet.web.render(url, mode="text")                             |
      |  - Strict LLM Security & Metric Audit prompt                          |
      |  - Compare SEMANTIC VERDICT: ACHIEVED vs FAILED                       |
      +-----------------------------------------------------------------------+
                     /                                         \
        VERDICT: "ACHIEVED"                               VERDICT: "FAILED"
                    /                                           \
                   v                                             v
  +---------------------------------+           +---------------------------------+
  |        Status: COMPLETED        |           |        Status: FORFEITED        |
  | 100% Stake Refunded to Creator  |           | 100% Stake Slashed to Community |
  | (via emit_transfer)             |           | Treasury Fund                   |
  +---------------------------------+           +---------------------------------+
```

### Core Workflow:
1. **Create Fitness Challenge:**
   - Athlete initiates a discipline commitment by providing:
     - `athlete_name`: Name registered on athlete's profile / bib.
     - `activity_type`: Sport category (e.g., `RUNNING`, `CYCLING`, `MARATHON`).
     - `target_metric`: Measurable target (e.g., `"Sub-4 Marathon (42.195 km)"`, `"10km under 50 mins"`).
     - `deadline_timestamp`: Unix timestamp limit.
   - Pledges stake in native GEN (must be $\ge$ `min_stake`).
   - Contract sets challenge status to `ACTIVE`.

2. **Submit Proof:**
   - Once the activity is completed, the athlete submits the public activity URL (`evidence_url`, e.g., Strava activity, Garmin Connect link, or official race results page).
   - Status updates to `EVIDENCE_SUBMITTED`.

3. **Autonomous AI Adjudication & Semantic Consensus:**
   - Anyone or the athlete triggers `adjudicate_challenge(challenge_id)`.
   - The consensus leader and validators execute:
     - Direct webpage scraping via `gl.nondet.web.render(evidence_url, mode="text")`.
     - Inspection of HTTP errors, 404s, empty responses, or deleted pages.
     - LLM Prompting with strict forensic analysis (name matching, metric verification, deadline checking).
     - `validator_fn` compares the **core semantic meaning** (`verdict == "ACHIEVED"` vs `"FAILED"`), ensuring validator consensus converges without failing on stylistic text variations in the reasoning field.
     - Fail-safe rule: If confidence is below 60%, the verdict automatically falls back to `FAILED`.

4. **Autonomous Settlement:**
   - **`ACHIEVED`**: Status transitions to `COMPLETED`. 100% of the staked GEN is refunded to the athlete via `gl.get_contract_at(creator).emit_transfer(value=u256(stake_amt))`.
   - **`FAILED`**: Status transitions to `FORFEITED`. Staked GEN is permanently slashed into `treasury_balance` (reserved for community incentives, charity, or platform development).

---

## 🛡️ Technical Compliance & GenVM Best Practices

This contract is engineered to satisfy the strict requirements of GenVM and GenLayer Studio:

| Technical Rule | Implementation in PaceStake |
|---|---|
| **Pragma Line 1 & 2** | Exact `# v0.2.16` and `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` without empty lines. |
| **Module Imports** | Star-import `from genlayer import *`. Zero alias imports. Top-level imports limited to standard dataclasses and json. |
| **Class Definition** | Single contract class: `class Contract(gl.Contract):`. |
| **Storage Collections** | Strictly `TreeMap[str, FitnessChallenge]` and `bigint`. Zero `dict`, `list`, or bare `int` in storage. |
| **TreeMap Key Typing** | All keys are strings (`str(cid)`), complying with the GenVM calldata boundary specification. |
| **`__init__` Safety** | `TreeMap` collections are **not** reassigned in `__init__`, preventing `AssertionError: TreeMap <- TreeMap`. |
| **Closure Safety** | Storage values are extracted to local variables (`evidence_url_local`, `athlete_name_local`, etc.) prior to entering `leader_fn`. |
| **Native Transfer** | Uses `gl.get_contract_at(recipient).emit_transfer(value=u256(amount))` instead of deprecated or non-existent methods. |
| **Semantic Validator** | Validates `leader_verdict == my_verdict` inside `validator_fn(leader_res)` on `gl.vm.Return.calldata`. |

---

## 📁 Repository Structure

```
PaceStake/
├── contracts/
│   └── contract.py            # Main Intelligent Contract in Python
├── tests/
│   ├── __init__.py            # Test package marker
│   ├── conftest.py            # Simulator RPC mock utility & fixtures (sim_installMocks)
│   └── test_pacestake.py      # Comprehensive pytest/gltest test suite
├── gltest.config.yaml         # Configuration for gltest (studionet / localnet)
├── .env.example               # Template environment variables
├── requirements-dev.txt       # Development dependencies
└── README.md                  # Comprehensive architectural and deployment documentation
```

---

## 🧪 Testing & Verification

The test suite covers full happy paths, edge cases, permission boundaries, and fail-safes using `gltest`:

### Running Tests Locally:

```bash
# Run the test suite with pytest
pytest tests -v
```

### Test Scenarios Covered:
1. **Contract Initialization & Default Views:** Verifies initial owner, counters, stake thresholds, and JSON statistics.
2. **Challenge Creation Security Checks:** Validates minimum stake requirement, empty athlete name, short metric descriptions, and non-positive timestamps.
3. **Proof Submission Validation:** Enforces access control (only creator), valid HTTP/HTTPS URLs, and prevents double-submissions.
4. **Test Case 1 (Happy Path - Sub-4 Marathon Achieved):**
   - Web mock returns verified Strava activity (42.25 km, 3h 48m).
   - AI jury returns `ACHIEVED`.
   - Contract settles to `COMPLETED` and refunds 100% of the staked 5,000 wei back to the athlete.
5. **Test Case 2 (Metric Failure - Incomplete Century Ride):**
   - Web mock returns Garmin activity with only 34.2 km (target was 100 km).
   - AI jury returns `FAILED`.
   - Contract settles to `FORFEITED` and slashes 2,500 wei into `treasury_balance`.
6. **Test Case 3 (Web 404 / Broken Link Handling):**
   - Web mock returns 404 Not Found.
   - Intelligent scraper safely catches the error; AI consensus returns `FAILED`.
7. **Test Case 4 (Low-Confidence Failsafe):**
   - Even if raw verdict claims `ACHIEVED`, confidence < 60% triggers automatic fallback to `FAILED`.
8. **State Machine Integrity:** Enforces that unready or already finalized challenges cannot be re-adjudicated.
9. **Treasury Management:** Verifies that only the owner can withdraw slashed funds for community/charity purposes.

---

## 🌐 Live Deployment on GenLayer Studionet

PaceStake is deployed and operational on the official GenLayer Studionet environment:

| Property | Value |
|---|---|
| **Contract Address** | `0x1F4e4FcA9fb50Cd8294b837386436EF66Db0fe91` |
| **Network** | `studionet` |
| **Studio Sandbox URL** | [studio.genlayer.com](https://studio.genlayer.com) |
| **Compiler / Pragma** | `# v0.2.16` |
| **Package Dependency** | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` |

---

## 🔍 Illustrative Realistic Example Call & State Transition

Here is a step-by-step walkthrough of a real-world athletic commitment on PaceStake:

### Step 1: Creator Stakes on a Goal (`create_challenge`)
- **Caller (`msg.sender`):** `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`
- **Call:** `create_challenge("Alex Runner", "RUNNING", "Sub-4 Marathon (42.195 km)", 1750000000)`
- **Value Sent:** `5000` wei (staked in escrow)
- **Resulting State:**
  - `challenge_id`: `"1"`
  - `status`: `"ACTIVE"`
  - `stake_amount`: `5000`
  - `treasury_balance`: `0`

### Step 2: Athlete Submits Activity Proof (`submit_proof`)
- **Caller:** `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` (Only creator can submit)
- **Call:** `submit_proof("1", "https://www.strava.com/activities/1234567890")`
- **Resulting State:**
  - `evidence_url`: `"https://www.strava.com/activities/1234567890"`
  - `status`: `"EVIDENCE_SUBMITTED"`

### Step 3: Decentralized AI Adjudication (`adjudicate_challenge`)
- **Caller:** Anyone (permissionless settlement trigger)
- **Call:** `adjudicate_challenge("1")`
- **What happens under the hood:**
  1. **Web Scrape:** GenVM executes `gl.nondet.web.render("https://www.strava.com/activities/1234567890", mode="text")`.
     - *Simulated Render Output:* `"Activity: Sunday Morning Marathon. Athlete: Alex Runner. Sport: Run. Distance: 42.25 km. Elapsed Time: 3:48:12. Timestamp: 1749500000. Status: Completed."`
  2. **LLM Evaluation:** GenVM prompts the LLM to verify:
     - Is the athlete name matching `"Alex Runner"`? -> **Yes**
     - Does the sport match `"RUNNING"`? -> **Yes**
     - Is the distance $\ge 42.195$ km? -> **42.25 km >= 42.195 km (PASS)**
     - Was elapsed time under 4 hours? -> **3h 48m 12s <= 4h (PASS)**
     - Was it completed before timestamp `1750000000`? -> **1749500000 <= 1750000000 (PASS)**
  3. **AI Jury Verdict:**
     ```json
     {
       "verdict": "ACHIEVED",
       "confidence": 98,
       "reasoning": "Alex Runner completed a marathon run of 42.25 km in 3 hours 48 minutes 12 seconds prior to the deadline, satisfying the Sub-4 Marathon requirement.",
       "metrics_verified": {
         "distance_km": 42.25,
         "elapsed_time": "3:48:12",
         "target_met": true
       }
     }
     ```
  4. **State Transition:**
     - `status`: `"COMPLETED"`
     - `stake_amount`: `0`
     - **Refund:** `5000` wei transferred back to `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` via `emit_transfer`.

### Counter-Example (Failure / Forfeiture):
If the athlete submitted a Strava link where distance was only 32 km (DNF), or if the link returned HTTP 404:
- The AI jury issues verdict `"FAILED"`.
- `status` transitions to `"FORFEITED"`.
- The staked `5000` wei is permanently transferred into contract `treasury_balance` (slashed).

---

## 🧠 Consensus Deep Dive: Semantic Meaning vs. String Determinism

A central innovation of GenLayer is resolving non-deterministic real-world and AI observations into deterministic ledger state.

### Why Exact String Matching Fails in AI Oracles
In standard distributed computing, validators require byte-for-byte identical output. However, LLMs are fundamentally probabilistic:
- Leader Validator returns: `{"verdict": "ACHIEVED", "reasoning": "Distance 42.25km exceeds 42.195km."}`
- Validator 2 returns: `{"verdict": "ACHIEVED", "reasoning": "The runner achieved 42.25 km successfully."}`
- Validator 3 returns: `{"verdict":"ACHIEVED","reasoning":"Target met (42.25 km in 3h48m)"}`

If validators checked `leader_json == my_json` or compared strings, **consensus would never be reached**, causing liveness failure.

### The PaceStake Semantic Equivalence Validator
PaceStake implements a semantic validator function inside `gl.vm.run_nondet`:

```python
def validator_fn(leader_res: str) -> bool:
    my_res = evaluate_evidence_and_decide()
    try:
        leader_dict = json.loads(leader_res)
        my_dict = json.loads(my_res)
        leader_verdict = str(leader_dict.get("verdict", "")).strip().upper()
        my_verdict = str(my_dict.get("verdict", "")).strip().upper()
        # Semantic consensus: Both must agree on the core discrete verdict
        return leader_verdict == my_verdict and leader_verdict in ("ACHIEVED", "FAILED")
    except Exception:
        return False
```

1. **Discrete Outcome Convergence:** Validators agree on the subjective ground truth (`ACHIEVED` vs `FAILED`), discarding stylistic variance in `reasoning` and minor confidence score differences.
2. **Confidence Threshold Guard:** If any validator's confidence score drops below 60%, the verdict is automatically clamped to `FAILED`, preventing hallucinatory refunds.
3. **Deterministic State Execution:** Once consensus certifies the agreed JSON payload, the contract updates storage state and dispatches native coin transfers deterministically.

---

## ⚖️ License
MIT License. Built for the **GenLayer Builder Program**.
