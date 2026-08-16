/**
 * Comma/newline list parsers — mirrors the helpers in the Angular components
 * (parseTags / parseList / parseLines).
 */

export function parseList(input: string): string[] {
  return input
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseLines(input: string): string[] {
  return input
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}
