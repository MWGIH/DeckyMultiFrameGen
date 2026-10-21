import type { ReactNode } from "react";
import { Dropdown, Field, type DropdownProps } from "@decky/ui";

// A dropdown on its own full-width line under its label (Steam's DropdownItem keeps it on the label's line, which
// cuts long game names and choices short)
export function BelowDropdown({
  label,
  description,
  ...dropdown
}: DropdownProps & { label: ReactNode; description?: ReactNode }) {
  return (
    <Field
      label={label}
      description={description}
      childrenLayout="below"
      childrenContainerWidth="max"
    >
      <Dropdown {...dropdown} />
    </Field>
  );
}
