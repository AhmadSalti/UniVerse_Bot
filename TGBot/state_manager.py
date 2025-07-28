from typing import Dict, Set

class StateManager:
    def __init__(self):
        self.locked_users: Set[int] = set()

    def lock_user(self, user_id: int) -> None:
        self.locked_users.add(user_id)

    def unlock_user(self, user_id: int) -> None:
        self.locked_users.discard(user_id)

    def is_user_locked(self, user_id: int) -> bool:
        return user_id in self.locked_users