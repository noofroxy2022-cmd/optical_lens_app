import axios from 'axios';

jest.mock('axios');
const client = { post: jest.fn() };
axios.create.mockReturnValue(client);
const { prescriptionAPI } = require('./api');

beforeEach(() => client.post.mockClear());

test.each(['none', 'high_impact_resistance', 'screens_blue_light'])(
  'seller request preserves customer need %s', (need) => {
    prescriptionAPI.search(19, { customer_need: need, use_mode: 'distance',
      technology_intent: 'blue_photo_gray' });
    expect(client.post).toHaveBeenCalledWith('/prescriptions/19/search',
      expect.objectContaining({ customer_need: need, use_mode: 'distance',
        technology_intent: 'blue_photo_gray' }));
  });

test('legacy search does not opt into seller workflow implicitly', () => {
  prescriptionAPI.search(19);
  expect(client.post.mock.calls[0][1]).not.toHaveProperty('customer_need');
});

test.each([['photo_gray'], ['impact_resistant']])(
  'seller request forwards plural customer_needs %j in the POST body', (need) => {
    prescriptionAPI.search(19, { customer_needs: [need], use_mode: 'distance' });
    expect(client.post).toHaveBeenCalledWith('/prescriptions/19/search',
      expect.objectContaining({ customer_needs: [need], use_mode: 'distance' }));
  });
