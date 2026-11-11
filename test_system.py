import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("=" * 60)
    print("RUNNING AUTOMATED UNIT & INTEGRATION TESTS")
    print("=" * 60)

    # Test 1: User Profile & Initial Balance
    res = requests.get(f"{BASE_URL}/api/user/profile")
    assert res.status_code == 200, f"Failed profile fetch: {res.text}"
    profile = res.json()
    print(f"[PASS] User Profile Loaded: {profile['full_name']} | Balance: ₹{profile['balance']}")

    # Test 2: Start ATM Cardless Session
    res = requests.post(f"{BASE_URL}/api/atm/session/start", json={
        "atm_code": "ATM_CAMPUS_01",
        "amount": 500
    })
    assert res.status_code == 200, f"Failed to start ATM session: {res.text}"
    session = res.json()
    session_id = session["session_id"]
    print(f"[PASS] Dynamic QR Created: Session={session_id} | TTL={session['validity_seconds']}s | Attempt={session['attempts_count']}/3")

    # Test 3: Test Security Constraint - Refresh QR up to max 3 attempts
    # Attempt 2
    res2 = requests.post(f"{BASE_URL}/api/atm/session/refresh-qr", json={"session_id": session_id})
    assert res2.status_code == 200 and res2.json()["attempts_count"] == 2
    print("[PASS] Refreshed QR: Attempt 2 of 3 accepted.")

    # Attempt 3
    res3 = requests.post(f"{BASE_URL}/api/atm/session/refresh-qr", json={"session_id": session_id})
    assert res3.status_code == 200 and res3.json()["attempts_count"] == 3
    print("[PASS] Refreshed QR: Attempt 3 of 3 accepted.")

    # Attempt 4: Should be blocked by Security Rate Limiter (HTTP 429)
    res4 = requests.post(f"{BASE_URL}/api/atm/session/refresh-qr", json={"session_id": session_id})
    assert res4.status_code == 429, f"Expected 429 rate limit error, got {res4.status_code}"
    print(f"[PASS] Security Constraint Enforced: Attempt 4 rejected with HTTP 429: '{res4.json()['detail']}'")

    # Test 4: Fresh Session for Mobile Authorization Flow
    res_fresh = requests.post(f"{BASE_URL}/api/atm/session/start", json={
        "atm_code": "ATM_CAMPUS_01",
        "amount": 1000
    })
    fresh_session_id = res_fresh.json()["session_id"]
    print(f"[PASS] Fresh ATM Session Created for Withdrawal Test: {fresh_session_id}")

    # Test 5: Verify Session from Mobile App
    res_verify = requests.post(f"{BASE_URL}/api/mobile/verify-session?session_id={fresh_session_id}")
    assert res_verify.status_code == 200
    print("[PASS] Mobile Scanner successfully verified QR session details.")

    # Test 6: Wrong MPIN Test (should be rejected with 401)
    res_wrong_pin = requests.post(f"{BASE_URL}/api/mobile/authorize-withdrawal", json={
        "session_id": fresh_session_id,
        "pin": "9999",
        "live_face_b64": "SAME_AS_PROFILE"
    })
    assert res_wrong_pin.status_code == 401
    print("[PASS] Incorrect MPIN blocked with HTTP 401.")

    # Test 7: Correct MPIN + 2FA Face Auth (should succeed)
    res_auth = requests.post(f"{BASE_URL}/api/mobile/authorize-withdrawal", json={
        "session_id": fresh_session_id,
        "pin": "1234",
        "live_face_b64": "SAME_AS_PROFILE"
    })
    assert res_auth.status_code == 200, f"Auth failed: {res_auth.text}"
    auth_data = res_auth.json()
    print(f"[PASS] Withdrawal Authorized! Txn: {auth_data['transaction_id']} | Dispensed: ₹{auth_data['amount']} | Remaining: ₹{auth_data['remaining_balance']}")

    # Test 8: Verify Transaction Ledger Audit
    res_tx = requests.get(f"{BASE_URL}/api/transactions")
    assert res_tx.status_code == 200 and len(res_tx.json()) > 0
    print(f"[PASS] Transaction Ledger Audit successfully recorded {len(res_tx.json())} transaction(s).")

    print("\nALL SYSTEM TESTS PASSED SUCCESSFULLY! (8/8)")

if __name__ == "__main__":
    run_tests()

