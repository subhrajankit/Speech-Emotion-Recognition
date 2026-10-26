"""
Tamper-Evident Audit Logging (Phase 18).
Records security-critical events (authentication successes/failures, command executions)
to an append-only, SHA256 hash-chained ledger in logs/audit.log.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, List


class AuditLogger:
    """
    Append-only tamper-evident audit logger with cryptographic hash chaining.
    Stored independently from normal application logs in logs/audit.log.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, log_path: str = "logs/audit.log"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._last_hash, self._last_index = self._get_last_entry()

    def _get_last_entry(self) -> Tuple[str, int]:
        """Reads the last line of the audit log to retrieve the previous hash and index."""
        if not os.path.exists(self.log_path) or os.path.getsize(self.log_path) == 0:
            return self.GENESIS_HASH, -1

        last_line = ""
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line

        if not last_line:
            return self.GENESIS_HASH, -1

        try:
            entry = json.loads(last_line)
            return entry.get("hash", self.GENESIS_HASH), entry.get("index", -1)
        except Exception:
            return self.GENESIS_HASH, -1

    def _compute_hash(self, index: int, timestamp: str, event_type: str, details: Dict[str, Any], prev_hash: str) -> str:
        """Computes SHA256 digest over entry components."""
        canonical_details = json.dumps(details, sort_keys=True)
        payload = f"{index}|{timestamp}|{event_type}|{canonical_details}|{prev_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log_event(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Appends a hash-chained audit event to the ledger.
        """
        details = details or {}
        timestamp = datetime.now(timezone.utc).isoformat()
        index = self._last_index + 1
        prev_hash = self._last_hash

        entry_hash = self._compute_hash(index, timestamp, event_type, details, prev_hash)

        entry = {
            "index": index,
            "timestamp": timestamp,
            "event_type": event_type,
            "details": details,
            "prev_hash": prev_hash,
            "hash": entry_hash
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        self._last_hash = entry_hash
        self._last_index = index
        return entry

    def verify_chain(self, log_path: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Cryptographically verifies the hash chain integrity from genesis to head.
        Returns (is_valid, error_description).
        """
        target = log_path or self.log_path
        if not os.path.exists(target) or os.path.getsize(target) == 0:
            return True, None

        expected_prev_hash = self.GENESIS_HASH
        expected_index = 0

        with open(target, "r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, 1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    return False, f"Line {line_no}: Corrupted JSON format."

                # Verify index
                if record.get("index") != expected_index:
                    return False, f"Line {line_no}: Index mismatch. Expected {expected_index}, got {record.get('index')}."

                # Verify prev_hash
                if record.get("prev_hash") != expected_prev_hash:
                    return False, f"Line {line_no}: Hash chain broken. Expected prev_hash {expected_prev_hash}, got {record.get('prev_hash')}."

                # Recompute digest
                computed_hash = self._compute_hash(
                    record["index"],
                    record["timestamp"],
                    record["event_type"],
                    record["details"],
                    record["prev_hash"]
                )

                if record.get("hash") != computed_hash:
                    return False, f"Line {line_no}: Tampered record hash. Expected {computed_hash}, got {record.get('hash')}."

                expected_prev_hash = record["hash"]
                expected_index += 1

        return True, None


# Global singleton
audit_logger = AuditLogger()
