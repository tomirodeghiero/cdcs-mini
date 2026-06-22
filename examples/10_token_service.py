class TokenService:
    def issue(self, user_id: int, ttl_seconds: int) -> str:
        """@generate
        behavior:
          require ttl_seconds > 0
          return self._sign(str(user_id))

        examples:
          issue(42, 60) == "signed:42"
          issue(1, 0) raises ValueError

        calls:
          self._sign(payload: str) -> str
          self._now() -> int

        reads:
          self.secret_key: bytes

        constraints:
          no_network
          no_filesystem
        """
        ...
