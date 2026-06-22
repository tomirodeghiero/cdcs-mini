// Function with no @generate JSDoc — analyzer must flag MISSING_GENERATE.
export function plain(value: string): number {
  return value.length;
}
