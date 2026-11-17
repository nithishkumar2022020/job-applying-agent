const assert = require('node:assert/strict');
const test = require('node:test');
const { defaults, matches, workMode, states, locationStates, normalize } = require('../web/filters.js');
const sample = { title: 'Junior Python Developer', company_type: 'mnc', source: 'Employer', location: 'Noida, India', work_mode: 'hybrid', description: 'Python FastAPI', eligible: false, evidence: { years_required: 0, salary_inr: 600000, tracks: ['Stack match'] } };
test('user selections can include a job rejected by original rules', () => assert.equal(matches(sample, defaults), true));
test('remote is excluded by default and selectable', () => {
  const job = { ...sample, work_mode: 'remote' };
  assert.equal(matches(job, defaults), false);
  assert.equal(matches(job, { ...defaults, workModes: ['remote'] }), true);
});
test('select all allows a state and individual deselection excludes it', () => {
  const job = { ...sample, location: 'Hyderabad, Telangana, India' };
  assert.equal(matches(job, defaults), false);
  assert.equal(matches(job, { ...defaults, states: [...states] }), true);
  assert.equal(matches(job, { ...defaults, states: states.filter(state => state !== 'Telangana') }), false);
});
test('28 states and 8 union territories plus unknown are selectable', () => {
  assert.equal(states.length, 37);
  assert.equal(new Set(states).size, 37);
});
test('empty selection matches nothing', () => assert.equal(matches(sample, { ...defaults, states: [] }), false));
test('city names and state abbreviations resolve to states', () => {
  assert.deepEqual(locationStates('Noida, India'), ['Uttar Pradesh']);
  assert.deepEqual(locationStates('Gurgaon'), ['Haryana']);
  assert.deepEqual(locationStates('Bengaluru, KA, India'), ['Karnataka']);
  assert.deepEqual(locationStates('DL, India'), ['Delhi']);
});
test('multi-location jobs match any selected state', () => {
  const job = { ...sample, location: 'Bengaluru / Mumbai, India' };
  assert.equal(matches(job, { ...defaults, states: ['Maharashtra'] }), true);
  assert.equal(matches(job, { ...defaults, states: ['Delhi'] }), false);
});
test('unknown locations require their own selection', () => {
  const job = { ...sample, location: 'India' };
  assert.equal(matches(job, { ...defaults, states: ['Delhi'] }), false);
  assert.equal(matches(job, { ...defaults, states: ['Unknown / not specified'] }), true);
});
test('legacy saved geography migrates and empty selections stay empty', () => {
  const migrated = normalize({ region: 'north', excludeStates: true });
  assert.equal(migrated.states.includes('Delhi'), true);
  assert.equal(migrated.states.includes('Karnataka'), false);
  assert.deepEqual(normalize({ states: [] }).states, []);
});
test('salary and unknown-pay controls are independent', () => {
  assert.equal(matches(sample, { ...defaults, minSalary: 700000 }), false);
  const job = { ...sample, evidence: { ...sample.evidence, salary_inr: null } };
  assert.equal(matches(job, defaults), true);
  assert.equal(matches(job, { ...defaults, includeUnknownSalary: false }), false);
});
test('experience, seniority, source, skills and tracks are selectable', () => {
  assert.equal(matches({ ...sample, evidence: { ...sample.evidence, years_required: 3 } }, defaults), false);
  assert.equal(matches({ ...sample, title: 'Senior Python Developer' }, defaults), false);
  assert.equal(matches(sample, { ...defaults, source: 'Other' }), false);
  assert.equal(matches(sample, { ...defaults, skill: 'Python, FastAPI', track: 'Stack match' }), true);
  assert.equal(matches(sample, { ...defaults, skill: 'Java' }), false);
});
test('office-only location is not falsely labeled confirmed onsite', () => assert.equal(workMode({ location: 'Noida, India' }), 'unknown'));
