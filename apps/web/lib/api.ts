export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/graphql";

export type LastOperation = {
  name: string;
  query: string;
  variables: Record<string, unknown>;
  response: unknown;
  at: string;
};

type Listener = (operation: LastOperation) => void;

const listeners = new Set<Listener>();
let last: LastOperation | null = null;

export function subscribeToOperations(listener: Listener): () => void {
  listeners.add(listener);
  if (last) listener(last);
  return () => {
    listeners.delete(listener);
  };
}

export function recordOperation(operation: LastOperation): void {
  last = operation;
  listeners.forEach((listener) => listener(operation));
}

export type GraphQLResult<T> = {
  data: T | null;
  errors?: { message: string }[];
  operation: LastOperation;
};

export async function graphql<T>(
  name: string,
  query: string,
  variables: Record<string, unknown> = {},
): Promise<GraphQLResult<T>> {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  const body = (await response.json()) as { data: T | null; errors?: { message: string }[] };
  return {
    data: body.data,
    errors: body.errors,
    operation: { name, query, variables, response: body, at: new Date().toISOString() },
  };
}
