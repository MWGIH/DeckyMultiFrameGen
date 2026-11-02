import type { ReactNode } from "react";
import { Dropdown, Field, type DropdownProps } from "@decky/ui";

// Where a dropdown's menu opens. The SteamOS beta client opens it beside the dropdown by default, which in the
// Quick Access Menu puts it off the right edge of the screen; this keeps it over the dropdown and on screen.
export const MENU_POSITION: DropdownProps["contextMenuPositionOptions"] = {
  bOverlapHorizontal: true,
  bMatchWidth: true,
  bShiftToFitWindow: true,
  bFitToWindow: true,
};

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
      <Dropdown contextMenuPositionOptions={MENU_POSITION} {...dropdown} />
    </Field>
  );
}
