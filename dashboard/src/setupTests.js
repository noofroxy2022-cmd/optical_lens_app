// react-router v7 uses TextEncoder/TextDecoder internally. CRA 5's bundled
// jsdom test environment predates when jsdom exposed these globally, so they
// are polyfilled here from Node's own util module (browsers always have
// them natively - this only affects the Jest test environment).
if (typeof global.TextEncoder === 'undefined') {
  const { TextEncoder, TextDecoder } = require('util');
  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder;
}
