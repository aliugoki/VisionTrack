import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Person, PersonDetail } from '@/shared/types/api';

const PERSONS_KEY = ['persons'] as const;

export interface PersonsListParams {
  limit?: number;
  offset?: number;
}

export function usePersons(params?: PersonsListParams) {
  return useQuery({
    queryKey: [...PERSONS_KEY, params],
    queryFn: async () => {
      const { data } = await api.get<Person[]>('/persons', { params });
      return data;
    },
    // Persons accumulate slowly. 30s refetch keeps the list current
    // without hammering the API.
    refetchInterval: 30_000,
  });
}

export function usePerson(id: string | undefined) {
  return useQuery({
    queryKey: [...PERSONS_KEY, id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await api.get<PersonDetail>(`/persons/${id}`);
      return data;
    },
    refetchInterval: 15_000, // detail view watches timeline grow in near-real-time
  });
}
