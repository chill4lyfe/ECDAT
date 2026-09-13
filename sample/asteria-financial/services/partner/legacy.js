const crypto = require('crypto');
function legacyDigest(v) { return crypto.createHash('md5').update(v).digest('hex'); }
module.exports = { legacyDigest };
