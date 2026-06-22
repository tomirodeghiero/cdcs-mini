// Stock @generate contracts the "load example" link drops into the editor.
// Kept here so the parent page can detect them and swap-on-language-toggle.

export const PYTHON_SAMPLE = `def parse_port(value: str) -> int:
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
`;

export const TS_SAMPLE = `/**
 * @generate
 * behavior:
 *   require value.length > 0
 *   require value.length <= 5
 *   return parseInt(value, 10)
 *
 * examples:
 *   parsePort("80") == 80
 *   parsePort("443") == 443
 *   parsePort("0") raises Error
 *
 * constraints:
 *   no_imports
 *   no_network
 *   no_filesystem
 */
export function parsePort(value: string): number {
  return 0;
}
`;
