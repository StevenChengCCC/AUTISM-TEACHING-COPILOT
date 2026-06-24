import { useState } from 'react';

export function useAsyncAction() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function run<T>(action: () => Promise<T>): Promise<T | null> {
    setLoading(true);
    setError('');
    try {
      return await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Operation failed');
      return null;
    } finally {
      setLoading(false);
    }
  }

  return { loading, error, setError, run };
}
