def parse_port(value: str) -> int:
    """@generate
    behavior:
      strip(value)
      require value matches digits
      require 1 <= int(value) <= 65535
      return int(value)
    examples:
      parse_port("80") == 80
      parse_port("443") == 443
      parse_port("0") raises ValueError
    constraints:
      no_imports
      no_network
      no_filesystem
    """
    ...
