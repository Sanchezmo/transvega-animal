"""Intake session management for Telegram dog intake flow."""
import time
import uuid
from typing import Dict, Optional

from app.core.privacy_router import privacy_router


class IntakeSession:
    """Session state for a single user/chat."""
    def __init__(self, session_id: str, user_id: int, chat_id: int):
        self.session_id = session_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.data: Dict = {}
        self.media_files: list = []  # list of dicts with file info
        self.privacy_scope = "ONLINE_ALLOWED"  # starts as allowed, may become LOCAL_ONLY

    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        return (time.time() - self.updated_at) > ttl_seconds

    def touch(self):
        self.updated_at = time.time()

    def update_privacy_scope(self):
        """Re-evaluate privacy based on accumulated data."""
        # Check collected data for sensitive info
        combined = {**self.data}
        # also check media filenames? we rely on purpose/origin later
        if privacy_router.contains_sensitive_data(combined):
            self.privacy_scope = "LOCAL_ONLY"
        else:
            # If any media is original/raw, still LOCAL_ONLY
            for m in self.media_files:
                if m.get('purpose') == 'original' or m.get('media_type') in ['photo', 'video']:
                    # media itself considered sensitive unless processed/social/listing
                    if m.get('purpose') in ['original']:
                        self.privacy_scope = "LOCAL_ONLY"
                        break
            else:
                self.privacy_scope = "ONLINE_ALLOWED"


class IntakeSessionStore:
    """In-memory store with basic TTL cleanup."""
    def __init__(self):
        self._sessions: Dict[str, IntakeSession] = {}

    def get_or_create(self, user_id: int, chat_id: int) -> IntakeSession:
        # Simple key: f"{user_id}:{chat_id}"
        key = f"{user_id}:{chat_id}"
        session = self._sessions.get(key)
        if session and not session.is_expired():
            session.touch()
            return session
        # create new
        session_id = str(uuid.uuid4())
        session = IntakeSession(session_id, user_id, chat_id)
        self._sessions[key] = session
        return session

    def get(self, user_id: int, chat_id: int) -> Optional[IntakeSession]:
        key = f"{user_id}:{chat_id}"
        session = self._sessions.get(key)
        if session and not session.is_expired():
            session.touch()
            return session
        # if expired, remove
        if session:
            del self._sessions[key]
        return None

    def delete(self, user_id: int, chat_id: int):
        key = f"{user_id}:{chat_id}"
        self._sessions.pop(key, None)

    def cleanup_expired(self):
        now = time.time()
        to_del = []
        for key, sess in self._sessions.items():
            if sess.is_expired():
                to_del.append(key)
        for key in to_del:
            del self._sessions[key]


# Global instance
intake_session_store = IntakeSessionStore()