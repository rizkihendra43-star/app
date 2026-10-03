import { QueryClient } from "@tanstack/react-query";

// Exported so session code can wipe it at session boundaries — cached data outlives logout.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});
