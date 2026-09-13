import test from "node:test";
import assert from "node:assert/strict";
import { createLocalActionConfirmation } from "../localActionConfirmation.ts";

test("preview never applies and confirmation is required", () => {
  const action = createLocalActionConfirmation();
  let calls = 0;
  assert.equal(action.confirm("Sheet1:A1", () => calls++), false);
  action.preview("Sheet1:A1");
  assert.equal(calls, 0);
  assert.equal(action.confirm("Sheet1:A1", () => calls++), true);
  assert.equal(calls, 1);
  assert.equal(action.confirm("Sheet1:A1", () => calls++), false);
  assert.equal(calls, 1);
});

test("cancel permanently prevents application of the proposal", () => {
  const action = createLocalActionConfirmation();
  action.preview("A1");
  action.cancel();
  action.preview("A1");
  assert.equal(action.confirm("A1", () => assert.fail("cancelled action ran")), false);
});

test("changing the target requires a fresh preview", () => {
  const action = createLocalActionConfirmation();
  action.preview("Sheet1:A1");
  assert.equal(action.confirm("Sheet2:A1", () => assert.fail("stale target ran")), false);
  action.preview("Sheet2:A1");
  assert.equal(action.confirm("Sheet2:A1", () => {}), true);
});

test("throwing or reentrant callbacks cannot be applied again", () => {
  const action = createLocalActionConfirmation();
  action.preview("A1");
  assert.throws(() => action.confirm("A1", () => {
    assert.equal(action.confirm("A1", () => assert.fail("reentrant action ran")), false);
    throw new Error("local apply failed");
  }), /local apply failed/);
  assert.equal(action.confirm("A1", () => assert.fail("ambiguous retry ran")), false);
});
