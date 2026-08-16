import { parseLines, parseList } from '@/utils/lists';

describe('parseList', () => {
  it('splits on commas and trims whitespace', () => {
    expect(parseList(' python, fastapi ,  postgres ')).toEqual(['python', 'fastapi', 'postgres']);
  });

  it('drops empty entries', () => {
    expect(parseList('a,,b, ,c')).toEqual(['a', 'b', 'c']);
  });

  it('returns an empty array for blank input', () => {
    expect(parseList('')).toEqual([]);
    expect(parseList('   ')).toEqual([]);
  });
});

describe('parseLines', () => {
  it('splits on newlines and trims whitespace', () => {
    expect(parseLines('First bullet\n  Second bullet \nThird')).toEqual([
      'First bullet',
      'Second bullet',
      'Third',
    ]);
  });

  it('drops blank lines', () => {
    expect(parseLines('a\n\nb\n')).toEqual(['a', 'b']);
  });
});
