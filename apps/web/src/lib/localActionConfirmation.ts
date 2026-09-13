/** A single proposal can be confirmed once, and only for the reviewed target. */
export function createLocalActionConfirmation() {
  let reviewedTarget: string | undefined;
  let consumed = false;
  return {
    isConsumed: () => consumed,
    preview(target: string) {
      if (!consumed) reviewedTarget = target;
    },
    cancel() {
      consumed = true;
    },
    confirm(target: string, apply: () => void) {
      if (consumed) return false;
      if (reviewedTarget === undefined || reviewedTarget !== target) return false;
      // Lock before invoking the callback, including when it throws or re-enters.
      consumed = true;
      apply();
      return true;
    },
  };
}
