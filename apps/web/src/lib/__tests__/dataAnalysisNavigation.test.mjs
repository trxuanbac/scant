import test from 'node:test';
import assert from 'node:assert/strict';
import { readAnalysisMode, analysisModeUrl, dataAnalysisUrl, readDatasetId } from '../dataAnalysisNavigation.js';

test('selection is explicit and unknown modes return to selection', () => {
  for (const query of ['', 'analysis=unknown']) assert.equal(readAnalysisMode(new URLSearchParams(query)), null);
  for (const mode of ['direct-analysis', 'docx-report']) {
    const url = analysisModeUrl('mode=auto&type=data_analysis&prompt=hello', mode);
    const params = new URL(url, 'http://localhost').searchParams;
    assert.equal(readAnalysisMode(params), mode);
    assert.equal(params.get('prompt'), 'hello');
  }
});

test('returning to selection removes only analysis mode and preserves context', () => {
  const url = analysisModeUrl('mode=auto&type=data_analysis&workflow=data&analysis=docx-report', null);
  const params = new URL(url, 'http://localhost').searchParams;
  assert.equal(readAnalysisMode(params), null);
  assert.equal(params.get('workflow'), 'data');
  assert.equal(params.get('type'), 'data_analysis');
});

test('saved dataset navigation preserves workflow context', () => {
  const url = dataAnalysisUrl('mode=auto&type=data_analysis&workflow=data', {
    analysis: 'direct-analysis',
    dataset: 'file-123',
  });
  const params = new URL(url, 'http://localhost').searchParams;
  assert.equal(readAnalysisMode(params), 'direct-analysis');
  assert.equal(readDatasetId(params), 'file-123');
  assert.equal(params.get('workflow'), 'data');
  assert.equal(params.get('type'), 'data_analysis');
});

test('invalid dataset identifiers are ignored', () => {
  assert.equal(readDatasetId(new URLSearchParams('dataset=../secret')), null);
  assert.equal(readDatasetId(new URLSearchParams('dataset=')), null);
});
