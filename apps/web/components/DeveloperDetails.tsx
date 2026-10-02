"use client";

import { useEffect, useState } from "react";
import { subscribeToOperations, type LastOperation } from "@/lib/api";

export function DeveloperDetails() {
  const [operation, setOperation] = useState<LastOperation | null>(null);
  useEffect(() => subscribeToOperations(setOperation), []);

  return (
    <details className="dev">
      <summary>Developer details</summary>
      {operation ? (
        <div>
          <p className="muted">
            Last GraphQL operation: <strong>{operation.name}</strong>
          </p>
          <pre aria-label="Query">{operation.query.trim()}</pre>
          <pre aria-label="Variables">{JSON.stringify(operation.variables, null, 2)}</pre>
          <pre aria-label="Response">{JSON.stringify(operation.response, null, 2)}</pre>
        </div>
      ) : (
        <p className="muted">No operation yet.</p>
      )}
    </details>
  );
}
