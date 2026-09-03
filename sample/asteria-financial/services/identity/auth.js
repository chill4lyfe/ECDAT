const { createHash } = require("node:crypto");
export function legacySessionFingerprint(value) {
  return createHash("sha1").update(value).digest("hex");
}
