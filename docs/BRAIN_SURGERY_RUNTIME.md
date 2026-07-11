# Brain Surgery Runtime

Surgery isolates a child module, keeps the Parent Kernel and fallback live, validates a candidate, observes it in shadow mode, and promotes only through reversible canaries. A failed preflight or health signal rolls back to the previous version/fallback.
