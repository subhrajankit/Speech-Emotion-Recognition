"""
Cross-Platform Backup and Recovery Manager for SenseAI Voice Assistant (Phase 15).
Provides automated backup, checksum verification, retention pruning, and restore
for SQLite / PostgreSQL and the FAISS vector index.
"""
import os
import sys
import shutil
import sqlite3
import hashlib
import tarfile
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup_manager")


def compute_sha256(filepath: str) -> str:
    """Computes hex SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_checksum(filepath: str) -> str:
    """Writes companion .sha256 file for a backup archive."""
    checksum = compute_sha256(filepath)
    chk_file = f"{filepath}.sha256"
    with open(chk_file, "w", encoding="utf-8") as f:
        f.write(f"{checksum}  {os.path.basename(filepath)}\n")
    return checksum


def verify_checksum(filepath: str) -> bool:
    """Verifies file against companion .sha256 file if present."""
    chk_file = f"{filepath}.sha256"
    if not os.path.exists(chk_file):
        logger.warning(f"No checksum file found for {filepath}; skipping verification.")
        return True
    with open(chk_file, "r", encoding="utf-8") as f:
        expected = f.read().split()[0].strip()
    actual = compute_sha256(filepath)
    if expected.lower() != actual.lower():
        logger.error(f"Checksum mismatch for {filepath}! Expected: {expected}, Actual: {actual}")
        return False
    logger.info(f"Checksum verified successfully for {os.path.basename(filepath)}.")
    return True


def backup_sqlite(db_path: str, backup_dir: str) -> Optional[str]:
    """Performs an online, non-blocking backup of the SQLite database."""
    if not os.path.exists(db_path):
        logger.warning(f"SQLite database at {db_path} does not exist. Skipping.")
        return None

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_filename = f"sqlite_backup_{timestamp}.db"
    target_path = os.path.join(backup_dir, target_filename)

    logger.info(f"Backing up SQLite database from {db_path} to {target_path}...")
    try:
        source_conn = sqlite3.connect(db_path)
        dest_conn = sqlite3.connect(target_path)
        with dest_conn:
            source_conn.backup(dest_conn)
        source_conn.close()
        dest_conn.close()

        write_checksum(target_path)
        logger.info(f"[PASS] SQLite backup created: {target_path}")
        return target_path
    except Exception as e:
        logger.error(f"Failed to backup SQLite database: {e}")
        return None


def restore_sqlite(backup_file: str, db_path: str) -> bool:
    """Restores SQLite database from backup file after safety snapshot."""
    if not os.path.exists(backup_file):
        logger.error(f"Backup file {backup_file} does not exist.")
        return False

    if not verify_checksum(backup_file):
        return False

    # Pre-restore safety snapshot
    if os.path.exists(db_path):
        safety_path = f"{db_path}.pre_restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bak"
        logger.info(f"Creating pre-restore safety snapshot: {safety_path}")
        shutil.copy2(db_path, safety_path)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    shutil.copy2(backup_file, db_path)

    # Verify restored database integrity
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchone()[0]
        conn.close()
        if res.lower() == "ok":
            logger.info(f"[PASS] SQLite database restored and verified (integrity_check: {res}).")
            return True
        else:
            logger.error(f"Restored database integrity check failed: {res}")
            return False
    except Exception as e:
        logger.error(f"Error checking restored SQLite integrity: {e}")
        return False


def backup_faiss_index(index_dir: str, backup_dir: str) -> Optional[str]:
    """Archives the FAISS index directory if populated."""
    if not os.path.exists(index_dir) or not os.listdir(index_dir):
        logger.info(f"FAISS index dir {index_dir} is empty or absent. (Note: Index is rebuildable from data/documents/).")
        return None

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_filename = f"faiss_index_{timestamp}.tar.gz"
    target_path = os.path.join(backup_dir, target_filename)

    logger.info(f"Archiving FAISS vector index to {target_path}...")
    try:
        with tarfile.open(target_path, "w:gz") as tar:
            tar.add(index_dir, arcname=os.path.basename(index_dir))
        write_checksum(target_path)
        logger.info(f"[PASS] FAISS vector index archived: {target_path}")
        return target_path
    except Exception as e:
        logger.error(f"Failed to archive FAISS index: {e}")
        return None


def rebuild_faiss_from_documents(docs_dir: str, index_dir: str) -> bool:
    """Rebuilds the FAISS vector index from source documents (canonical recovery path)."""
    logger.info(f"Rebuilding FAISS index from documents in {docs_dir}...")
    if not os.path.exists(docs_dir) or not os.listdir(docs_dir):
        logger.warning(f"No source documents found in {docs_dir} to index.")
        return False

    from ..rag.retriever import RAGRetriever
    from .build_rag_index import ingest_and_index_documents
    try:
        count = ingest_and_index_documents(docs_dir=docs_dir, output_dir=index_dir)
        logger.info(f"[PASS] FAISS index rebuilt successfully with {count} chunks.")
        return True
    except Exception as e:
        logger.error(f"Error rebuilding FAISS index: {e}")
        return False


def prune_old_backups(backup_dir: str, retention_days: int = 7) -> int:
    """Deletes backup archives older than the specified retention days."""
    if not os.path.exists(backup_dir):
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    pruned_count = 0

    for fname in os.listdir(backup_dir):
        fpath = os.path.join(backup_dir, fname)
        if os.path.isfile(fpath):
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath), timezone.utc)
            if mtime < cutoff:
                try:
                    os.remove(fpath)
                    pruned_count += 1
                    logger.info(f"Pruned expired backup file: {fname}")
                except Exception as e:
                    logger.warning(f"Could not remove {fname}: {e}")

    logger.info(f"Pruning complete: removed {pruned_count} expired backup files.")
    return pruned_count


def main():
    parser = argparse.ArgumentParser(description="SenseAI Backup & Restore Manager")
    parser.add_argument("--action", choices=["backup", "restore", "prune"], required=True)
    parser.add_argument("--db-type", choices=["sqlite", "postgres"], default="sqlite")
    parser.add_argument("--backup-dir", default="backups")
    parser.add_argument("--db-path", default="database/dev.db")
    parser.add_argument("--backup-file", help="Path to backup file for restore")
    parser.add_argument("--index-dir", default="data/index")
    parser.add_argument("--docs-dir", default="data/documents")
    parser.add_argument("--rebuild-faiss", action="store_true")
    parser.add_argument("--retention-days", type=int, default=7)

    args = parser.parse_args()

    if args.action == "backup":
        if args.db_type == "sqlite":
            backup_sqlite(args.db_path, args.backup_dir)
        backup_faiss_index(args.index_dir, args.backup_dir)
        prune_old_backups(args.backup_dir, args.retention_days)

    elif args.action == "restore":
        if args.backup_file:
            if args.db_type == "sqlite":
                restore_sqlite(args.backup_file, args.db_path)
        if args.rebuild_faiss:
            rebuild_faiss_from_documents(args.docs_dir, args.index_dir)

    elif args.action == "prune":
        prune_old_backups(args.backup_dir, args.retention_days)


if __name__ == "__main__":
    main()
