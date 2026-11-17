const assert = require('node:assert/strict');
const test = require('node:test');
const { defaults, matches, workMode } = require('../web/filters.js');
const sample = { title: 'Junior Python Developer', company_type: 'mnc', source: 'Employer', location: 'Noida, India', work_mode: 'hybrid', description: 'Python FastAPI', eligible: false, evidence: { years_required: 0, salary_inr: 600000, tracks: ['Stack match'] } };
test('user selections can include a job rejected by original rules', () => assert.equal(matches(sample, defaults), true));
test('remote is excluded by default and selectable', () => {
  const job = { ...sample, work_mode: 'remote' };
  assert.equal(matches(job, defaults), false);
  assert.equal(matches(job, { ...defaults, workModes: ['remote'] }), true);
});
test('excluded states are user controlled', () => {
  const job = { ...sample, location: 'Hyderabad, Telangana, India' };
  assert.equal(matches(job, defaults), false);
  assert.equal(matches(job, { ...defaults, excludeStates: false }), true);
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
