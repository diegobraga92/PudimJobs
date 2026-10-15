import { apiClient } from '@/api/client';
import { setSourceAvoided } from '@/api/sources';

jest.mock('@/api/client', () => ({
  apiClient: { post: jest.fn() },
}));

const post = apiClient.post as jest.Mock;

describe('setSourceAvoided', () => {
  beforeEach(() => {
    post.mockReset();
    post.mockResolvedValue({ data: { id: 's1', avoided: true } });
  });

  it('flags the source through the avoid endpoint', async () => {
    await expect(setSourceAvoided('s1', true)).resolves.toEqual({ id: 's1', avoided: true });
    expect(post).toHaveBeenCalledWith('/api/sources/s1/avoid', { avoided: true });
  });

  it('omits the reason when none is given so the stored one is kept', async () => {
    await setSourceAvoided('s1', true);
    expect(post.mock.calls[0][1]).not.toHaveProperty('reason');
  });

  it('sends the reason when provided', async () => {
    await setSourceAvoided('s1', true, 'no remote roles');
    expect(post).toHaveBeenCalledWith('/api/sources/s1/avoid', {
      avoided: true,
      reason: 'no remote roles',
    });
  });

  it('sends an empty reason to clear it explicitly', async () => {
    await setSourceAvoided('s1', true, '');
    expect(post).toHaveBeenCalledWith('/api/sources/s1/avoid', { avoided: true, reason: '' });
  });

  it('restores the source with avoided false', async () => {
    await setSourceAvoided('s1', false);
    expect(post).toHaveBeenCalledWith('/api/sources/s1/avoid', { avoided: false });
  });
});
