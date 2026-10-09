import { describe, expect, it } from 'vitest';
import {
  ENUM, NUMERIC, TEXT, YEAR,
  applyFilters, describeFilter, formatFilters, hidingLabel, matchesFilter,
  parseFilter, parseFilters, parseNumeric, presentValues,
} from './gridFilter.js';

const SPECS = {
  employee_id: { key: 'employee_id', label: 'Employee', type: TEXT, read: (r) => r.employee_id },
  hours: { key: 'hours', label: 'Hours', type: NUMERIC, read: (r) => r.hours },
  status: {
    key: 'status', label: 'Reading', type: ENUM, read: (r) => r.status,
    format: (v) => v.replace(/_/g, ' '),
  },
  tax_year: {
    key: 'tax_year', label: 'Tax year', type: YEAR, read: (r) => r.tax_year,
    format: (v) => `TY${v}`,
  },
};

const rows = [
  { employee_id: 'E001', hours: 40, status: 'qualified', tax_year: 2023 },
  { employee_id: 'E002', hours: 34.29, status: 'below_minimum', tax_year: 2023 },
  { employee_id: 'A103', hours: 12, status: 'below_minimum', tax_year: 2024 },
];

describe('the numeric half of the grammar', () => {
  it('reads a comparator, longest operator first', () => {
    expect(parseNumeric('>=35')).toEqual({ op: '>=', value: 35 });
    expect(parseNumeric('>35')).toEqual({ op: '>', value: 35 });
    expect(parseNumeric('<=35')).toEqual({ op: '<=', value: 35 });
  });

  it('reads a range, and orders the bounds however they arrive', () => {
    expect(parseNumeric('10..52')).toEqual({ op: '..', min: 10, max: 52 });
    expect(parseNumeric('52..10')).toEqual({ op: '..', min: 10, max: 52 });
  });

  it('reads a bare number as "at least", which is what every column here asks', () => {
    expect(parseNumeric('35')).toEqual({ op: '>=', value: 35 });
  });

  it('refuses what it cannot read rather than guessing', () => {
    expect(parseNumeric('banana')).toBeNull();
    expect(parseNumeric('>=banana')).toBeNull();
    expect(parseNumeric('')).toBeNull();
  });
});

describe('an unparseable term is dropped, never passed through', () => {
  // A predicate that silently matches everything is worse than no filter: the
  // page says it is filtering and the total says otherwise.
  it('drops it at parse, so it never becomes an active chip', () => {
    expect(parseFilters(SPECS, 'hours:banana')).toEqual({});
    expect(describeFilter(SPECS.hours, 'banana')).toBeNull();
  });

  it('drops a column the grid does not know', () => {
    expect(parseFilters(SPECS, 'salary:>=100;hours:>=35')).toEqual({ hours: '>=35' });
  });

  it('drops an empty enum selection rather than matching nothing', () => {
    expect(parseFilter(SPECS.status, '||')).toBeNull();
  });
});

describe('each type filters the way its column reads', () => {
  it('text contains, case-insensitively', () => {
    expect(applyFilters(rows, SPECS, { employee_id: '~e00' }).map((r) => r.employee_id))
      .toEqual(['E001', 'E002']);
  });

  it('numeric compares', () => {
    expect(applyFilters(rows, SPECS, { hours: '>=35' }).map((r) => r.employee_id))
      .toEqual(['E001']);
    expect(applyFilters(rows, SPECS, { hours: '12..35' }).map((r) => r.employee_id))
      .toEqual(['E002', 'A103']);
  });

  it('enum multi-selects', () => {
    expect(applyFilters(rows, SPECS, { status: 'qualified|below_minimum' })).toHaveLength(3);
    expect(applyFilters(rows, SPECS, { status: 'qualified' }).map((r) => r.employee_id))
      .toEqual(['E001']);
  });

  it('year multi-selects', () => {
    expect(applyFilters(rows, SPECS, { tax_year: '2024' }).map((r) => r.employee_id))
      .toEqual(['A103']);
  });

  it('combines filters with AND, so each one narrows the last', () => {
    expect(applyFilters(rows, SPECS, { status: 'below_minimum', hours: '>=20' })
      .map((r) => r.employee_id)).toEqual(['E002']);
  });

  it('excludes a row whose numeric value is absent rather than treating it as zero', () => {
    expect(matchesFilter({ hours: null }, SPECS.hours, parseFilter(SPECS.hours, '<=5')))
      .toBe(false);
  });
});

describe('an enum offers what is present, never a hardcoded list', () => {
  // A hardcoded list goes stale the first time a status is renamed, and then
  // offers a filter that matches nothing -- which reads as "no rows".
  it('reads the distinct values out of the data', () => {
    expect(presentValues(rows, SPECS.status.read)).toEqual(['below_minimum', 'qualified']);
  });

  it('skips blanks, which are not a value anyone can choose', () => {
    expect(presentValues([{ s: 'a' }, { s: '' }, { s: null }], (r) => r.s)).toEqual(['a']);
  });

  it('sorts years numerically rather than as strings', () => {
    const years = [{ y: 2020 }, { y: 2024 }, { y: 2021 }];
    expect(presentValues(years, (r) => r.y)).toEqual(['2020', '2021', '2024']);
  });
});

describe('a column whose cell holds several values', () => {
  // A client operates in more than one state, and the map filters the book by
  // one. Expressed as a property of the COLUMN rather than a new operator, so
  // the written grammar stays `col:a|b` wherever it appears — including in
  // `tools/grid_filter.py`, which is unchanged by this.
  const STATE = { key: 'state', label: 'State', type: ENUM, multi: true, read: (r) => r.states };
  const book = [
    { name: 'Cascade', states: ['GA', 'NC', 'SC'] },
    { name: 'Northwind', states: ['GA', 'TN'] },
    { name: 'Ironbridge', states: ['GA'] },
  ];

  it('matches a row that holds the value among others', () => {
    const shown = applyFilters(book, { state: STATE }, { state: 'NC' });
    expect(shown.map((r) => r.name)).toEqual(['Cascade']);
  });

  it('still honours the or-grammar across several selections', () => {
    const shown = applyFilters(book, { state: STATE }, { state: 'NC|TN' });
    expect(shown.map((r) => r.name)).toEqual(['Cascade', 'Northwind']);
  });

  it('offers each distinct value once, not the combinations', () => {
    expect(presentValues(book, STATE.read)).toEqual(['GA', 'NC', 'SC', 'TN']);
  });
});

describe('the wire form round-trips, so a URL survives a refresh', () => {
  it('formats and parses back to the same filters', () => {
    const active = { hours: '>=35', status: 'qualified' };
    const wire = formatFilters(active);
    expect(wire).toBe('hours:>=35;status:qualified');
    expect(parseFilters(SPECS, wire)).toEqual(active);
  });

  it('keeps a colon inside the expression, which a range and a comparator both need', () => {
    expect(parseFilters(SPECS, 'hours:10..52')).toEqual({ hours: '10..52' });
  });
});

describe('a filtered grid says what it is hiding', () => {
  it('names both numbers when they differ', () => {
    expect(hidingLabel(12, 37)).toBe('12 of 37');
  });

  it('says one number when nothing is hidden', () => {
    expect(hidingLabel(37, 37)).toBe('37');
  });

  it('describes a filter in the column\u2019s own words', () => {
    expect(describeFilter(SPECS.hours, '>=35')).toBe('Hours >= 35');
    expect(describeFilter(SPECS.hours, '10..52')).toBe('Hours 10\u201352');
    expect(describeFilter(SPECS.status, 'below_minimum')).toBe('Reading: below minimum');
    expect(describeFilter(SPECS.tax_year, '2023|2024')).toBe('Tax year: TY2023, TY2024');
  });
});
