/**
 * @generate
 * behavior:
 *   strip(value)
 *   require value matches digits
 *   require 1 <= parseInt(value) <= 65535
 *   return parseInt(value)
 *
 * examples:
 *   parsePort("80") == 80
 *   parsePort("443") == 443
 *   parsePort("0") raises ValueError
 *
 * constraints:
 *   no_imports
 *   no_network
 *   no_filesystem
 */
export function parsePort(value: string): number {
  return 0;
}
